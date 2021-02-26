import json
import os
import datetime
from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import urllib
import google.oauth2.credentials
import google_auth_oauthlib.flow
import requests
import logging
from flask import Flask, redirect, request, make_response
from google.cloud import secretmanager
import google.cloud.logging
from googleapiclient.discovery import build

app = Flask(__name__)
ACTION_HUB_BASE_URL='https://actionhub-server-dot-looker-private-demo.uc.r.appspot.com'
ACTION_NAME='pixel_perfect'
PROJECT_ID = "looker-private-demo"
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# Script Mapper (maps template documents to scripts that should be run)
script_mapper={'1nyG8wDznWjZpXDaPVxwwa4w2DITWzsA27cZ2j5WEHUY':'AKfycbwmZjVncqKg6k3sGZkch3p3soJxoJ8UQoxwiMPq3qBFn3UydUHK2ZV-raKgIc9Al1FFvA',
'1OBytDdCD0RujEms8cQorRJsxEHtZAazo15vWDl2hOBc':'AKfycbwmZjVncqKg6k3sGZkch3p3soJxoJ8UQoxwiMPq3qBFn3UydUHK2ZV-raKgIc9Al1FFvA'}

scopes = ['https://www.googleapis.com/auth/drive','https://www.googleapis.com/auth/drive.scripts', 'https://www.googleapis.com/auth/script.external_request', 
      'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/documents',
      'https://www.googleapis.com/auth/drive']


# Setup logging in google cloud
client = google.cloud.logging.Client()
client.get_default_handler()
client.setup_logging()




# This function lists all the action from the action server
@app.route('/', methods=['POST'])
def action_list():
  logging.info('Inside the action_list: ')
  # get data uri from logo
  image_uri = base64.b64encode(open("pixel_perfect.png", "rb").read()).decode()
  list_ = {
        "label": "My Action Hub",
        "integrations": [
            {
            "name": ACTION_NAME,
            "label": "Create Pixel Perfect Document",
            "icon_data_uri": "data:image/png;base64,"+image_uri,
            "supported_action_types": ["query"],
            "supported_formats": ["json"],
            "url": f'{ACTION_HUB_BASE_URL}/actions/{ACTION_NAME}/execute',
            "form_url": f'{ACTION_HUB_BASE_URL}/actions/{ACTION_NAME}/form',
            "uses_oauth": True
             }
        ]
        }
  return list_

# This function checks to see if a user is logged in using oauth, if they are then we reutn a form for the scheduler, otherwise return oauth_link 
@app.route(f'/actions/{ACTION_NAME}/form', methods=['POST'])
def oauth_form():
  logging.info('Inside the oauth_form')

  #state_url is a special one-time-use URL that sets a user’s state for a given action.
  data = json.loads(request.data.decode())['data']
  state_url = data['state_url']
  state_json = json.loads(data['state_json'])

  # figure out if the user is authenticated, if the user is authenticated then return the form
  if 'access_token' in state_json and state_json['expires_at'] > datetime.datetime.now().timestamp() and all(s in state_json['scope'] for s in scopes):
    logging.info('state token exist, returning form')

    #create credentials object
    secret = get_secret("oauth")
    web_secret = json.loads(secret)['web']
    credentials = credentials = google.oauth2.credentials.Credentials(
      state_json["access_token"],
      refresh_token = state_json["refresh_token"],
      id_token = state_json["id_token"],
      token_uri = web_secret["token_uri"],
      client_id = web_secret["client_id"],
      client_secret = web_secret["client_secret"],
      scopes = state_json["scope"])

    #get all the files in the template folder
    drive_service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
    template_options = []
    page_token = None
    while True:
      # pylint: disable=maybe-no-member
      response = drive_service.files().list(q="'13ErW1EI9nPnQdcEWhVGWYAO0T7uyNs6Y' in parents", spaces='drive',
          fields='nextPageToken, files(id, name, mimeType)', supportsAllDrives=True, pageToken=page_token).execute()
      for file in response.get('files', []):
        f_id = file.get('id')
        if f_id in script_mapper:
          doc_type = str.split(file.get('mimeType'),".")[2].capitalize()
          filename = file.get('name') + ' (' + doc_type + ')'
          template_options.append({"name":f_id, "label":filename})
        page_token = response.get('nextPageToken', None)
      if page_token is None:
          break

    user_info = get_user_info(credentials)
    name = user_info['name']
    
    #return form for user in the scheduler
    form = {"fields":[
      {"name": "template", "label": "Template", "default": template_options[0]["name"],"required": True,"type": "select", "options": template_options},
      {"name": "name", "label": "Name", "default": "Pixel Perfect Document for "+name,"required": True,"type": "text"},{"name": "comments", "label": "Comments", "type": "textarea"}]}
    
    #send the access token back in the state
    form['state'] = {}
    form['state']['data']=json.dumps(state_json)
    form['state']['refresh_time']=600
   
    return form
  
  # #otherwise return a form field oauth link so the user can login
  # else:
  logging.info('state tokens dont exist, returning oauth link')
  encrypted_state_url = encrypt(state_url)
  oauth_return = {
    "name": "login",
    "type": "oauth_link",
    "label": "Log in",
    "description": "OAuth Link",
    #this link will initialize an OAuth flow
    "oauth_url": f"{ACTION_HUB_BASE_URL}/actions/{ACTION_NAME}/oauth?state=" + encrypted_state_url
  }

  return json.dumps({"fields":[oauth_return]})

# This function builds the URL that redirects the user to an oauth consent screen
@app.route(f'/actions/{ACTION_NAME}/oauth',  methods=['GET','POST'])
def oauth():
  logging.info('Inside the oauth:')
  encrypted_state_url = request.args.get('state')

  #decrypt just to verify it hasn't been changed by a user
  try:
    plainState = decrypt(encrypted_state_url)
    if plainState.index('https://') < 0:
      raise Exception("Expected decrypted state to be a HTTPS URL")
  except Exception as error:
    logging.error('Caught this error: ' + repr(error))
    return {"status":400,"body":"Invalid state"}

  redirect_uri = f"{ACTION_HUB_BASE_URL}/actions/{ACTION_NAME}/oauth_redirect"

  #create the url
  #grab the secret json
  flow = create_oauth_flow(redirect_uri)
  authorization_url, state = flow.authorization_url(
    access_type='offline',
    state=encrypted_state_url,
    prompt='consent',
    include_granted_scopes='true')
  
  return redirect(authorization_url, code=302)
  
# This function is used after the oauth consent screen to extract the information received from the authentication server and send over to Looker
@app.route(f'/actions/{ACTION_NAME}/oauth_redirect',methods=['GET','POST'])
def oauth_redirect():
  logging.info('Inside the oauth_redirect:')

  encrypted_state_url = request.args.get('state')
  #if code doesnt exist in the url then there is an error, you can extract
  try:
    code = request.args.get('code')
  except:
    error = request.args.get('code')
    logging.error('Caught this error: ' + repr(error))
    return {"status":400,"body":"Authentication unsuccessful"}

  #decrypt the state url and uses it to POST state back to Looker 
  state_url = decrypt(encrypted_state_url)
  
  redirect_uri = f"{ACTION_HUB_BASE_URL}/actions/{ACTION_NAME}/oauth_redirect"
  flow = create_oauth_flow(redirect_uri)
  tokens = flow.fetch_token(code=code)
  logging.info('tokens: ' + repr(tokens))
  
  # response = requests.post(state_url, data={"code": code, "redirect": redirect_uri})
  headers = {'Content-Type': 'application/json'} 
  try:
    response = requests.post(state_url, json={**tokens, "redirect":redirect_uri, "code":code}, headers=headers)
  except requests.exceptions.RequestException as e: 
    logging.warning(e)
    
  # if response.status >= 400:
  #   logging.error(f'Looker state URL responded with {response.status_code}')
  # else:

  response = make_response('Login successful. Please close this window and return to Looker',200)
  response.mimetype = "text/plain"
  return response


#execute 
@app.route(f'/actions/{ACTION_NAME}/execute',methods=['POST'])
def action_execute():
  data = json.loads(request.data.decode())

  # to do: what happens if name is blank?
  name = data["form_params"]["name"]
  templateId = data["form_params"]["template"]
  comments = data["form_params"]["comments"]
  state_json = json.loads(data["data"]["state_json"])
  looker_data = json.loads(data["attachment"]["data"])
  filters = data["scheduled_plan"]["query"]["filters"]

  secret = get_secret("oauth")
  web_secret = json.loads(secret)['web']
  credentials = google.oauth2.credentials.Credentials(
    state_json["access_token"],
    refresh_token = state_json["refresh_token"],
    id_token = state_json["id_token"],
    token_uri = web_secret["token_uri"],
    client_id = web_secret["client_id"],
    client_secret = web_secret["client_secret"],
    scopes = state_json["scope"])

  #create a copy of the document
  drive_service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
  copied_file = {'name': name, 'parents': [ { "id" : "root" } ]}
  # pylint: disable=maybe-no-member
  new_document_response = drive_service.files().copy(
          supportsAllDrives=True, fileId=templateId, body=copied_file).execute()
  file_id = new_document_response['id']

  #get user info & email
  user_info = get_user_info(credentials)
  email = user_info['email']

  #run the apps script to populate the data
  script_service = build('script', 'v1', credentials=credentials)

  client_id = timeframe = ''
  if 'trans.transaction_date' in filters:
    timeframe = filters['trans.transaction_date'].title()
  if 'client.client_id' in filters:
    client_id = filters['client.client_id']

  if templateId in script_mapper:
    logging.info("calling script")
    script_request = {"function": "insertData", "parameters": [file_id, user_info['name'], email, timeframe, client_id, comments,looker_data]}
    logging.info(repr(script_request))
    script_response = script_service.scripts().run(body=script_request, scriptId=script_mapper[templateId]).execute()
    logging.info(repr(script_response))
  else:
    app.make_response(('Script for template not found', 404))

  #move to my drive root folder
  try:
    file = drive_service.files().get(fileId=file_id,
                                    fields='parents').execute()
    previous_parents = ",".join(file.get('parents'))
    file = drive_service.files().update(fileId=file_id,
                                        addParents='root',
                                        removeParents=previous_parents,
                                        fields='id, parents').execute()
  except:
    logging.warning('Not able to move template to root drive')

  #give the user write access
  user_permission = {
      'type': 'user',
      'role': 'reader',
      'emailAddress': email
  }

  try:
    permission_response = drive_service.permissions().create(
            fileId=new_document_response["id"],
            sendNotificationEmail=True,
            emailMessage="Your new pixel perfect report has been created from Looker", 
            body=user_permission,
            fields='id',
    ).execute()
  except:
    logging.warning('Not able to share new document')

  return app.make_response(('Successfully created and shared document',200))

### helper functions ###

#gets the access token from the oauth client
def create_oauth_flow(redirect_uri):
  os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
  secret_json = json.loads(get_secret("oauth"))
  flow = google_auth_oauthlib.flow.Flow.from_client_config(secret_json,scopes=scopes)
  flow.redirect_uri = redirect_uri
  return flow
  
#grabs a secret from the secret manager
def get_secret(secret_name):
  client = secretmanager.SecretManagerServiceClient()
  name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
  response = client.access_secret_version(request={"name": name})
  payload = response.payload.data.decode("UTF")
  return payload

#encrypts a string using the specified password 
def encrypt(string):
  key = get_secret("encryption_key")
  string = string.encode()
  f = Fernet(key.encode())
  token = f.encrypt(string)
  return token.decode()
  
#decrypts a string using the specified password
def decrypt(token):
  key = get_secret("encryption_key")
  token = token.encode()
  f = Fernet(key.encode())
  result= f.decrypt(token)
  return result.decode()

#get user info & email
def get_user_info(credentials): 
  oauth2_client = build('oauth2','v2',credentials=credentials)
  # pylint: disable=maybe-no-member
  user_info= oauth2_client.userinfo().get().execute()
  return user_info