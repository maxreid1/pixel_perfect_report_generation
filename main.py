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

# Setup logging in google cloud
client = google.cloud.logging.Client()
client.get_default_handler()
client.setup_logging()

# This function lists all the action from the action server
@app.route('/', methods=['POST'])
def action_list():
  logging.info('Inside the action_list: ')
  list_ = {
        "label": "My Action Hub",
        "integrations": [
            {
            "name": ACTION_NAME,
            "label": "Create Pixel Perfect Document",
            "supported_action_types": ["query"],
            "supported_formats": ["inline_json"],
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
  logging.info('Body: %s', request.get_data())

  #state_url is a special one-time-use URL that sets a user’s state for a given action.
  data = json.loads(request.data.decode())['data']
  state_url = data['state_url']
  state_json = json.loads(data['state_json'])

  # figure out if the user is authenticated, if the user is authenticated then return the form
  if 'access_token' in data['state_json']:
    logging.info('state token exist, returning form')
    logging.info('state json %s',repr(state_json))

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
        doc_type = str.split(file.get('mimeType'),".")[2].capitalize()
        filename = file.get('name') + ' (' + doc_type + ')'
        logging.info(filename)
        template_options.append({"name":file.get('id'), "label":filename})
        page_token = response.get('nextPageToken', None)
      if page_token is None:
          break

    #options = [{"name":"Invoice"}]
    #return form for user in the scheduler
    form = {"fields":[
      {"name": "template", "label": "Template", "default": template_options[0]["name"],"required": True,"type": "select", "options": template_options},
      {"name": "name", "label": "Name", "type": "text"}]}
    
    #send the access token back in the state
    form['state'] = {}
    form['state']['data']=json.dumps(state_json)
    form['state']['refresh_time']=600
   
    logging.info('form '+ repr(form))
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
  logging.info('Oauth return: %s',oauth_return)
  return json.dumps({"fields":[oauth_return]})

# This function builds the URL that redirects the user to an oauth consent screen
@app.route(f'/actions/{ACTION_NAME}/oauth',  methods=['GET','POST'])
def oauth():
  logging.info('Inside the oauth:')
  encrypted_state_url = request.args.get('state')

  #decrypt just to verify it hasn't been changed by a user
  try:
    plainState = decrypt(encrypted_state_url)
    logging.info('decrypter url '+plainState)
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
  logging.info('Body: %s', request.get_data())
  data = json.loads(request.data.decode())

  logging.info('data keys: %s',data.keys())
  template = data["form_params"]["template"]
  # to do: what happens if name is blank?
  name = data["form_params"]["name"]
  looker_data = data["data"]
  params = request.query_string.decode()
  logging.info('params: %s', params)
  filters = data["scheduled_plan"]["query"]["filters"]
  ######for some reason this is missing
  state_json = json.loads(data["state"]["data"])

  # params = request.query_string.decode()
  # request.json
  # logging.info('params: %s', params)
  # state_json = json.loads(request.args.get('state'))

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

  drive_service = build('drive', 'v3', credentials=credentials)

  copied_file = {'title': name}
  # pylint: disable=maybe-no-member
  new_document_response = drive_service.files().copy(
          fileId=template, body=copied_file).execute()
  
  user_permission = {
      'type': 'user',
      'role': 'writer',
      'emailAddress': 'reidjohn@google.com'
  }
  permission_response = drive_service.permissions().create(
          fileId=new_document_response["id"],
          body=user_permission,
          fields='id',
  ).execute()

  logging.info(permission_response)

  return 'Complete'

### helper functions ###

#gets the access token from the oauth client
def create_oauth_flow(redirect_uri):
  os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
  secret_json = json.loads(get_secret("oauth"))
  scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/script.deployments']
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





# script_service = discovery.build('script', 'v1', http=http)
#     request = {"function": "insertData", "devMode": True, "parameters": [
#         invoice_doc_id, invoice['number'], invoice['date'], invoice['noVAT'], invoice['client'], invoice['lines']]}
#     response = script_service.scripts().run(body=request, scriptId=SCRIPT_ID).execute()
#     print("Execution response: %s" % str(response))



#accessToken --> tells us if user is signed in
#checks for request.params.state_json, which caontains code and redirect if both are present then call getAccessTokenFromCode
#getAccessTokenFromCode ---> sets out access token by......

#then we call dropboxClientFromRequest using our request and accessToken
#we could use the access token to make an API call to google drive so the user can do select the name of the gdrive template or something like that

#if the access token exists we want to save that back into our form state, so we creae a new state object (with {access_token: accessToken} as state.data)
# then we reutn this along with our form object from the form function



  