import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = os.environ.get('GDRIVE_CREDENTIALS_FILE', '/app/credentials.json')

def get_gdrive_service():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Warning: Google Drive credentials file not found at {CREDENTIALS_FILE}")
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Error initializing Google Drive service: {e}")
        return None

def get_or_create_folder(service, folder_name):
    try:
        # First, search specifically for a folder shared WITH the service account (which avoids the 0 quota issue)
        query_shared = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false and sharedWithMe=true"
        results = service.files().list(q=query_shared, spaces='drive', fields='files(id, name, ownedByMe)', supportsAllDrives=True, includeItemsFromAllDrives=True, corpora='allDrives').execute()
        items = results.get('files', [])

        if items:
            print(f"Found existing shared Google Drive folder: {folder_name} (ID: {items[0].get('id')})")
            return items[0].get('id')
            
        # Fallback to searching all folders (including inside Shared Drives!)
        query_all = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        results = service.files().list(q=query_all, spaces='drive', fields='files(id, name, ownedByMe)', supportsAllDrives=True, includeItemsFromAllDrives=True, corpora='allDrives').execute()
        items = results.get('files', [])
        
        if items:
            print(f"Found existing owned/Shared Google Drive folder: {folder_name} (ID: {items[0].get('id')})")
            return items[0].get('id')

        # Create folder
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
        print(f"Created Google Drive folder: {folder_name} (ID: {folder.get('id')})")
        return folder.get('id')
    except Exception as e:
        print(f"Error getting/creating folder: {e}")
        return None

def upload_to_gdrive(folder_name, file_paths, target_folder_id=None):
    service = get_gdrive_service()
    if not service:
        return []

    if target_folder_id:
        folder_id = target_folder_id
        print(f"Using explicitly provided Google Drive folder ID: {folder_id}")
    else:
        folder_id = get_or_create_folder(service, folder_name)
        
    if not folder_id:
        return []

    uploaded_ids = []
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            continue

        file_name = os.path.basename(file_path)
        try:
            import mimetypes
            mime_type, _ = mimetypes.guess_type(file_path)
            
            upload_path = file_path
            
            if not mime_type:
                if file_path.endswith('.jsonld'):
                    mime_type = 'application/ld+json'
                elif file_path.endswith('.md'):
                    mime_type = 'text/markdown'
                else:
                    mime_type = 'application/octet-stream'
                    
            file_metadata = {
                'name': file_name.replace('.md', '') if file_path.endswith('.md') else file_name,
                'parents': [folder_id]
            }
            
            # If the file is markdown, convert it to HTML first so Google Docs understands the headings/formatting natively
            if file_path.endswith('.md'):
                try:
                    import markdown
                    with open(file_path, 'r', encoding='utf-8') as f:
                        md_content = f.read()
                    html_body = markdown.markdown(md_content, extensions=['extra', 'sane_lists', 'nl2br', 'footnotes'])
                    
                    # Apply explicit inline styling so Google Docs enforces Arial 12 and paragraph splits
                    html_body = html_body.replace('<p>', '<p style="font-family: Arial, sans-serif; font-size: 12pt; margin-bottom: 12pt; line-height: 1.5;">')
                    html_body = html_body.replace('<li>', '<li style="font-family: Arial, sans-serif; font-size: 12pt; margin-bottom: 6pt; line-height: 1.5;">')
                    for h in ['h1', 'h2', 'h3', 'h4', 'h5']:
                        html_body = html_body.replace(f'<{h}>', f'<{h} style="font-family: Arial, sans-serif; margin-top: 16pt; margin-bottom: 8pt;">')
                        
                    html_content = f'<html><head><meta charset="UTF-8"></head><body style="font-family: Arial, sans-serif; font-size: 12pt;">\n{html_body}\n</body></html>'
                    
                    import tempfile
                    fd, upload_path = tempfile.mkstemp(suffix='.html')
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                        
                    mime_type = 'text/html'
                    file_metadata['mimeType'] = 'application/vnd.google-apps.document'
                except ImportError:
                    # Fallback if markdown library isn't available
                    file_metadata['mimeType'] = 'application/vnd.google-apps.document'
                
            media = MediaFileUpload(upload_path, mimetype=mime_type, resumable=True)
            
            # Check if file already exists in folder to avoid duplicates (optional but good)
            query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
            results = service.files().list(q=query, spaces='drive', fields='files(id)', supportsAllDrives=True, includeItemsFromAllDrives=True, corpora='allDrives').execute()
            items = results.get('files', [])
            
            if items:
                # Update existing
                file_id = items[0].get('id')
                service.files().update(fileId=file_id, media_body=media, supportsAllDrives=True).execute()
                print(f"Updated {file_name} in Google Drive")
                uploaded_ids.append(file_id)
            else:
                # Create new
                res = service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
                print(f"Uploaded {file_name} to Google Drive")
                uploaded_ids.append(res.get('id'))
        except Exception as e:
            print(f"Error uploading {file_name}: {e}")
            
    return uploaded_ids


def search_gdrive(query, folder_id=None):
    service = get_gdrive_service()
    if not service:
        return []
    try:
        q = query
        if folder_id:
            q = f"({q}) and '{folder_id}' in parents"
        results = service.files().list(q=q, spaces='drive', fields='files(id, name, mimeType)', supportsAllDrives=True, includeItemsFromAllDrives=True, corpora='allDrives').execute()
        return results.get('files', [])
    except Exception as e:
        print(f"Error searching Google Drive: {e}")
        return []

def read_gdrive_file(file_id):
    service = get_gdrive_service()
    if not service:
        return None
    try:
        # Get file metadata to check mime type
        file = service.files().get(fileId=file_id, fields='name, mimeType', supportsAllDrives=True).execute()
        mime_type = file.get('mimeType')
        
        if mime_type == 'application/vnd.google-apps.document':
            # Export Google Docs as plain text
            request = service.files().export_media(fileId=file_id, mimeType='text/plain')
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='text/csv')
        else:
            # Download regular files directly
            request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
            
        import io
        from googleapiclient.http import MediaIoBaseDownload
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        return fh.getvalue().decode('utf-8')
    except Exception as e:
        print(f"Error reading Google Drive file: {e}")
        return None
