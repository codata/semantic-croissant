import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'convertors'))
from gdrive_utils import get_gdrive_service
from googleapiclient.discovery import build

service = get_gdrive_service()
docs_service = build('docs', 'v1', credentials=service._http.credentials)

# 1. Create a blank doc using Drive API in the shared folder
folder_id = "0AAObXJILB1CgUk9PVA"
file_metadata = {
    'name': 'Test Suggestion Mode',
    'mimeType': 'application/vnd.google-apps.document',
    'parents': [folder_id]
}
doc = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
doc_id = doc.get("id")
print(f"Created doc: {doc_id}")

# 2. Add text as suggestion
reqs = [
    {
        "insertText": {
            "location": {"index": 1},
            "text": "Hello, this is a suggested text!\n"
        }
    }
]

try:
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": reqs,
            "writeControl": {
                "writeMode": "SUGGEST"
            }
        }
    ).execute()
    print("Successfully inserted text as suggestion.")
except Exception as e:
    print(f"Failed: {e}")

