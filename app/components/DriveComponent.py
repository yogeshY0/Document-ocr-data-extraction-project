import io
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from qrlib.QRComponent import QRComponent

from Constants import DOWNLOADS_DESTINATION, ACCEPTED_MIME_TYPES, SHARED_FOLDER_ID, SERVICE_ACCOUNT_FILE


class DriveComponent(QRComponent):

    SCOPES = ["https://www.googleapis.com/auth/drive"]

    def __init__(self, credentials_path: str = None, folder_id: str = None) -> None:
        super().__init__()
        self.credentials_path = credentials_path or SERVICE_ACCOUNT_FILE
        self.folder_id = str(folder_id or SHARED_FOLDER_ID).strip()
        self.drive_service = None
        self.next_page_token = None
        self.status_folder_ids = {}

    def setup(self) -> None:
        if not self.folder_id:
            raise ValueError("DriveComponent.folder_id is empty. Check SHARED_FOLDER_ID in Constants.py.")
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Service account credentials not found at {self.credentials_path}")

        creds = Credentials.from_service_account_file(self.credentials_path, scopes=self.SCOPES)
        self.drive_service = build("drive", "v3", credentials=creds)
        Path(DOWNLOADS_DESTINATION).mkdir(parents=True, exist_ok=True)

        if self.logger:
            self.logger.info("step=drive_setup status=authenticated folder_id=%s", self.folder_id)

    def list_files(self) -> List[Dict[str, Any]]:
        return self.fetch_all_drive_files_metadata()

    def fetch_all_drive_files_metadata(self) -> List[Dict[str, Any]]:
        all_files = []
        page_token = None
        mime_query = " or ".join(f"mimeType = '{mime}'" for mime in ACCEPTED_MIME_TYPES)
        query = f"'{self.folder_id}' in parents and ({mime_query}) and trashed = false"

        while True:
            try:
                response = (
                    self.drive_service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields="nextPageToken, files(id, name, mimeType, size, md5Checksum, parents)",
                        pageSize=10,
                        pageToken=page_token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True
                    )
                    .execute()
                )
                all_files.extend(response.get("files", []))
                page_token = response.get("nextPageToken", None)
                if not page_token:
                    break
            except HttpError as err:
                if self.logger:
                    self.logger.error("step=fetch_metadata status=failed error=%s", str(err))
                raise

        if self.logger:
            self.logger.info("step=fetch_all_drive_files_metadata count=%d", len(all_files))
        return all_files

    def download_file(self, file_id: str, destination_path: str) -> str:
        """Download a Drive file directly to destination_path (a FULL FILE PATH, not a directory)."""
        Path(destination_path).parent.mkdir(parents=True, exist_ok=True)

        request = self.drive_service.files().get_media(fileId=file_id, supportsAllDrives=True)
        with io.FileIO(destination_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        if self.logger:
            self.logger.info("step=download_file status=success path=%s", destination_path)
        return destination_path

    def move_file_to_status(self, drive_file_id: str, status: str) -> None:
        folder_name = status.lower()
        folder_id = self.status_folder_ids.get(folder_name)
        if not folder_id:
            folder_query = (
                f"'{self.folder_id}' in parents and "
                f"name = '{folder_name}' and "
                "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            )
            folders = self.drive_service.files().list(
                q=folder_query,
                spaces="drive",
                fields="files(id)",
                pageSize=1,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute().get("files", [])
            if folders:
                folder_id = folders[0]["id"]
            else:
                folder_id = self.drive_service.files().create(
                    body={
                        "name": folder_name,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [self.folder_id],
                    },
                    fields="id",
                    supportsAllDrives=True,
                ).execute()["id"]
            self.status_folder_ids[folder_name] = folder_id

        file_info = self.drive_service.files().get(
            fileId=drive_file_id, fields="parents", supportsAllDrives=True,
        ).execute()
        previous_parents = ",".join(file_info.get("parents", []))
        self.drive_service.files().update(
            fileId=drive_file_id,
            addParents=folder_id,
            removeParents=previous_parents or None,
            fields="id, parents",
            supportsAllDrives=True,
        ).execute()

    def cleanup_file(self, filePath: str) -> None:
        if os.path.exists(filePath):
            try:
                os.remove(filePath)
            except OSError as cleanup_err:
                if self.logger:
                    self.logger.warning("Failed to remove file '%s': %s", filePath, cleanup_err)

    def cleanup(self) -> None:
        if os.path.isdir(DOWNLOADS_DESTINATION):
            try:
                shutil.rmtree(DOWNLOADS_DESTINATION)
                if self.logger:
                    self.logger.info("step=cleanup status=success target=%s", DOWNLOADS_DESTINATION)
            except OSError as cleanup_err:
                if self.logger:
                    self.logger.warning("Failed to remove directory '%s': %s", DOWNLOADS_DESTINATION, cleanup_err)