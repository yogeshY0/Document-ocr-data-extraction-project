import os

# Google Drive Configuration
SHARED_FOLDER_ID = "1CvkphMd8W3RW16bCyvuOph9kY-fvpPk6"
SERVICE_ACCOUNT_FILE = "credentials.json"
SCOPES = ['https://www.googleapis.com/auth/drive']

# Supported Document MIME Types
ACCEPTED_MIME_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/jpg'
]

# Local Input Directory
DOWNLOADS_DESTINATION = os.path.join("output", "input")

# SQLite Database Path
DATABASE_PATH = os.path.join("output", "kyc_records.db")

# Status Folder Definitions
STATUS_FOLDERS = {
    "processed": "processed",
    "flagged": "flagged",
    "failed": "failed"
}

# Validation Rules & Required Document Fields
REQUIRED_FIELDS = [
    "doc_type",
    "full_name",
    "date_of_birth",
    "id_number"
]

ACCEPTABLE_DOC_TYPES = [
    "DRIVING_LICENSE",
    "CITIZENSHIP",
    "PASSPORT",
    "NATIONAL_ID"
]