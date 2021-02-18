import json
# from googleapiclient.discovery import build
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
# from requests_toolbelt.adapters import appengine

# s = requests.Session()
# s.mount('http://', appengine.AppEngineAdapter())
# s.mount('https://', appengine.AppEngineAdapter())


app = Flask(__name__)
ACTION_HUB_BASE_URL='https://actionhub-server-dot-looker-private-demo.uc.r.appspot.com'
ACTION_NAME='pixel_perfect'
PROJECT_ID = "looker-private-demo"

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
#   access_token
# expires_in
# refresh_token
# scope
# token_type
# id_token
# expires_at
# redirect

  logging.info('data %s',repr(data))
  logging.info('data keys %s',repr(data.keys()))
	  
  #figure out if the user is authenticated, if the user is authenticated then return the form
  if 'access_token' in data['state_json']:
    logging.info('state tokens exist, returning form')
    #make an API call back to GDrive to find all the templates in X folder
    options = [{"name":"Invoice"}]
    #return form for user in the scheduler
    form = json.dumps({"fields":[
      {"name": "name", "label": "Name", "type": "text"},
      # {"name": "comments", "label": "Comments", "type": "textarea"},
      {"name": "template", "label": "Template", "type": "select", "options": options}
    ]})
    return form
  
  #otherwise return a form field oauth link so the user can login
  else:
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
  secret_json = json.loads(get_secret("oauth"))
  scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/script.deployments']
  flow = google_auth_oauthlib.flow.Flow.from_client_config(secret_json,scopes=scopes)
  flow.redirect_uri = redirect_uri
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
  tokens = get_accesstoken(code, redirect_uri)
  logging.info('tokens: ' + repr(tokens))
  
  # response = requests.post(state_url, data={"code": code, "redirect": redirect_uri})
  headers = {'Content-Type': 'application/json'} 
  try:
    response = requests.post(state_url, json={**tokens, "redirect":redirect_uri}, headers=headers)
  except requests.exceptions.RequestException as e: 
    logging.warning(e)
    logging.info(repr(response))
  
  # if response.status >= 400:
  #   logging.error(f'Looker state URL responded with {response.status_code}')
  # else:
  response = make_response('Login successful. Please close this window and return to Looker',200)
  response.mimetype = "text/plain"
  return response

### helper functions ###

#gets the access token from the oauth client
def get_accesstoken(code, redirect_uri):
  os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
  secret_json = json.loads(get_secret("oauth"))
  scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/script.deployments']
  flow = google_auth_oauthlib.flow.Flow.from_client_config(secret_json,scopes=scopes)
  flow.redirect_uri = redirect_uri
  tokens = flow.fetch_token(code=code)
  return tokens
  

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

#grab the access token for making api calls 
#def get_accestoken():

# def action_execute(request):
#     file_type = request["form_param"]["file_type"]
#     comments = request["form_param"]["comments"]
#     template = request["form_param"]["template"]
#     data = request["data"]
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/reidjohn/Downloads/sandbox-trials-ab300809ea88.json"
# drive_service = build('drive', 'v3')

# #this is where we go and get the template files that the service acccount has access to
# #we can use q to create a query for searching like q=" '%s' in parents and name = '%s'" % (folder_id, file_name),
# page_token = ''
# response = drive_service.files().list(
#     spaces='drive',
#     fields='nextPageToken, files(id, name, properties)',
#     pageToken=page_token).execute()
# #files is going to contain a list of all files with name and id, lets just take the first one
# template_id = response['files'][0]["id"]
# name_input = "my_new_document"
# new_document_response = drive_service.files().copy(
#         fileId=template_id, body={'title': 'Invoice_'+name_input}).execute()
# user_permission = {
#     'type': 'user',
#     'role': 'writer',
#     'emailAddress': 'reidjohn@google.com'
# }
# permission_response = drive_service.permissions().create(
#         fileId=new_document_response["id"],
#         body=user_permission,
#         fields='id',
# ).execute()



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





