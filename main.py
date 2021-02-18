import json
from googleapiclient.discovery import build
import os
import datetime
import google.oauth2.credentials
import google_auth_oauthlib.flow
from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

app = Flask(__name__)

# This function lists all the action from the action server
@app.route('/')
def action_list(request):
	form = {
        "label": "My Action Hub",
        "integrations": [
            {
            "name": "pixel_perfect",
            "label": "Create Pixel Perfect Document",
            "supported_action_types": ["query"],
            "supported_formats": ["inline_json"],
            "url": "https://example.com/actions/my_action/execute",
            "form_url":"https://us-central1-sandbox-trials.cloudfunctions.net/max-form-pixel-perfect",
            "uses_oauth": True
            }
        ]
  }
	return form


# This function checks to see if a user is logged in using oauth, if they are then we reutn a form for the scheduler, otherwise return oauth_link 
@app.route('/pixel_perfect/form')
def oauth_form(request):
  print(request)
  access_token = ''
  #state_url is a special one-time-use URL that sets a user’s state for a given action.
  #state_url = request["state_url"]
  #try and extract the access token from here
  
  #figure out if the user is authenticated, if the user is authenticated then return the form
  if access_token.length() > 0:
    #make an API call back to GDrive to find all the templates in X folder
    #return form for user in the scheduler
    form = json.dumps({"fields":[
      {"name": "name", "label": "Name", "type": "text"},
      {"name": "comments", "label": "Comments", "type": "textarea"},
      {"name": "template", "label": "Template", "type": "select", "options": [{"name":"Invoice"}]}
    ]})
    return form
  
  #otherwise return oauth link so the user can login
  else:
    oauth_return = {
      "type": "oauth_link",
      ### This URL will redirect to oauth function
      "oauth_link": ""
    }
    return oauth_return

def oauth(request):



  ### This is getting all the files where the parent folder id is 13ErW1EI9nPnQdcEWhVGWYAO0T7uyNs6Y
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/reidjohn/Downloads/sandbox-trials-ab300809ea88.json"
drive_service = build('drive', 'v3')
response = drive_service.files().list(q="'13ErW1EI9nPnQdcEWhVGWYAO0T7uyNs6Y' in parents", spaces='drive',fields='nextPageToken, files(id, name, mimeType)',supportsAllDrives=True,pageToken=page_token).execute()
for file in response.get('files', []):
  doc_type = str.split(file.get('mimeType'),".")[2].capitalize()
  print(file.get('name') + ' (' + doc_type + ')')
page_token = response.get('nextPageToken', None)
if page_token is None:
    break



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





#use state json from request to see if we can grab accesstoken
#then initialize the client with the access token



#accessToken --> tells us if user is signed in
#checks for request.params.state_json, which caontains code and redirect if both are present then call getAccessTokenFromCode
#getAccessTokenFromCode ---> sets out access token by......

#then we call dropboxClientFromRequest using our request and accessToken
#we could use the access token to make an API call to google drive so the user can do select the name of the gdrive template or something like that

#if the access token exists we want to save that back into our form state, so we creae a new state object (with {access_token: accessToken} as state.data)
# then we reutn this along with our form object from the form function

#if no access token exists then the user is not logged in yet, and we need to return the login information like this
# form.state = new Hub.ActionState()
# form.fields.push({
#         name: "login",
#         type: "oauth_link",
#         label: "Log in",
#         description: "In order to send to a Dropbox file or folder now and in the future, you will need to log in" +
#           " once to your Dropbox account.",
#         oauth_url: `${process.env.ACTION_HUB_BASE_URL}/actions/dropbox/oauth?state=${ciphertextBlob}`,
#       })




### SAMPLE OAUTH CODE


# Use the client_secret.json file to identify the application requesting
# authorization. The client ID (from that file) and access scopes are required.
flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
    'client_secret.json',
    scopes=['https://www.googleapis.com/auth/drive.metadata.readonly'])

# Indicate where the API server will redirect the user after the user completes
# the authorization flow. The redirect URI is required. The value must exactly
# match one of the authorized redirect URIs for the OAuth 2.0 client, which you
# configured in the API Console. If this value doesn't match an authorized URI,
# you will get a 'redirect_uri_mismatch' error.
flow.redirect_uri = 'https://www.example.com/oauth2callback'

# Generate URL for request to Google's OAuth 2.0 server.
# Use kwargs to set optional request parameters.
authorization_url, state = flow.authorization_url(
    # Enable offline access so that you can refresh an access token without
    # re-prompting the user for permission. Recommended for web server apps.
    access_type='offline',
    # Enable incremental authorization. Recommended as a best practice.
    include_granted_scopes='true')




    #This function determines the form input
# def action_form(request):
#   print(request)
#   return json.dumps({"fields":[
#   #   {"name": "file_type", "label": "File Type", "type": "select", "options": [{"name":"PDF"}, {"name":"DOC"}, {"name":"XLS"}]},
#     {"name": "comments", "label": "Comments", "type": "textarea"}
#   #   {"name": "template", "label": "Template", "type": "select", "options": [{"name":"Invoice"}]}
#   ]})
