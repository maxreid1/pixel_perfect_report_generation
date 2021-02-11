import json
from googleapiclient.discovery import build
import os
import datetime

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


def action_list(request):
	form = {
        "label": "My Action Hub",
        "integrations": [
            {
            "name": "schedule_to_pixel_perfect",
            "label": "Create Pixel Perfect Document",
            "supported_action_types": ["query"],
            "supported_formats": ["inline_json"],
            "url": "https://example.com/actions/my_action/execute",
            "form_url":"https://us-central1-sandbox-trials.cloudfunctions.net/max-form-pixel-perfect"
            }
        ]
        }

	return form

def action_form(request):
    return json.dumps({"fields":[
    #   {"name": "file_type", "label": "File Type", "type": "select", "options": [{"name":"PDF"}, {"name":"DOC"}, {"name":"XLS"}]},
      {"name": "comments", "label": "Comments", "type": "textarea"}
    #   {"name": "template", "label": "Template", "type": "select", "options": [{"name":"Invoice"}]}
    ]})


# def action_execute(request):
#     file_type = request["form_param"]["file_type"]
#     comments = request["form_param"]["comments"]
#     template = request["form_param"]["template"]
#     data = request["data"]




