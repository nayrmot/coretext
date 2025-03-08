from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import pickle

class GoogleDriveManager:
    """Handles all Google Drive operations for the CoreText system."""
    
    # Define the required scopes
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    
    def __init__(self, credentials_path='credentials.json', token_path='token.pickle'):
        """Initialize the Google Drive Manager."""
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Drive API."""
        credentials = None
        
        # Check if token file exists
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                credentials = pickle.load(token)
        
        # If credentials don't exist or are invalid, get new ones
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, self.SCOPES)
                credentials = flow.run_local_server(port=0)
            
            # Save the credentials for future use
            with open(self.token_path, 'wb') as token:
                pickle.dump(credentials, token)
        
        # Build the service
        self.service = build('drive', 'v3', credentials=credentials)
    
    def create_case_folder(self, case_name, parent_folder_id=None):
        """Create a folder for a case in Google Drive."""
        folder_metadata = {
            'name': case_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        # Add parent folder if specified
        if parent_folder_id:
            folder_metadata['parents'] = [parent_folder_id]
        
        folder = self.service.files().create(
            body=folder_metadata,
            fields='id,name,webViewLink'
        ).execute()
        
        return {
            'id': folder.get('id'),
            'name': folder.get('name'),
            'url': folder.get('webViewLink')
        }
    
    def create_folder_structure(self, case_name, parent_folder_id=None):
        """Create a complete folder structure for a case."""
        # Create main case folder
        case_folder = self.create_case_folder(case_name, parent_folder_id)
        
        # Create standard subfolders
        subfolders = ['Pleadings', 'Discovery', 'Correspondence', 'Exhibits', 'Transcripts', 'Research']
        folder_structure = {
            'case_folder': case_folder,
            'subfolders': {}
        }
        
        for folder_name in subfolders:
            subfolder = self.create_case_folder(folder_name, case_folder['id'])
            folder_structure['subfolders'][folder_name] = subfolder
        
        return folder_structure
    
    def upload_file(self, file_path, file_name, folder_id):
        """Upload a file to Google Drive."""
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(
            file_path,
            resumable=True
        )
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink,mimeType'
        ).execute()
        
        return {
            'id': file.get('id'),
            'name': file.get('name'),
            'url': file.get('webViewLink'),
            'mime_type': file.get('mimeType')
        }
    
    def get_file(self, file_id):
        """Get file metadata from Google Drive."""
        return self.service.files().get(
            fileId=file_id,
            fields='id,name,webViewLink,mimeType,size,createdTime,modifiedTime'
        ).execute()
    
    def search_files(self, query):
        """Search for files in Google Drive."""
        results = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType, webViewLink)'
        ).execute()
        
        return results.get('files', [])
    
    def get_folder_contents(self, folder_id):
        """Get all files and subfolders in a folder."""
        query = f"'{folder_id}' in parents"
        return self.search_files(query)
    
    def create_file_shortcut(self, file_id, shortcut_name, folder_id):
        """Create a shortcut to a file in another folder."""
        shortcut_metadata = {
            'name': shortcut_name,
            'mimeType': 'application/vnd.google-apps.shortcut',
            'shortcutDetails': {
                'targetId': file_id
            },
            'parents': [folder_id]
        }
        
        shortcut = self.service.files().create(
            body=shortcut_metadata,
            fields='id,name'
        ).execute()
        
        return shortcut
    
    def organize_by_document_type(self, file_id, file_name, case_folder_structure, document_type):
        """Place a document in the appropriate subfolder based on document type."""
        # Map document types to folder names
        folder_mapping = {
            'pleading': 'Pleadings',
            'discovery': 'Discovery',
            'letter': 'Correspondence',
            'email': 'Correspondence',
            'exhibit': 'Exhibits',
            'transcript': 'Transcripts',
            'research': 'Research'
        }
        
        # Get the appropriate folder ID
        target_folder_name = folder_mapping.get(document_type.lower(), 'Discovery')
        target_folder_id = case_folder_structure['subfolders'][target_folder_name]['id']
        
        # Create a shortcut in the appropriate folder
        return self.create_file_shortcut(file_id, file_name, target_folder_id)
