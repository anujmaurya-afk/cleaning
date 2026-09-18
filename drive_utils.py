"""
Google Drive storage helpers.

Uses a Google service account to store uploaded and processed files in a
Drive folder (ideally a Shared Drive) instead of a database or local disk.
Two Drive folders are used as "tables":
    UPLOADS_FOLDER_ID    -> raw files the user uploaded
    PROCESSED_FOLDER_ID  -> cleaned output files, ready for download

Set these via environment variables (see .env.example).
"""

import io
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]

SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
UPLOADS_FOLDER_ID = os.environ.get("DRIVE_UPLOADS_FOLDER_ID")
PROCESSED_FOLDER_ID = os.environ.get("DRIVE_PROCESSED_FOLDER_ID")

# Needed only if your folders live in a Shared Drive (recommended, since
# service accounts have no personal storage quota of their own).
SUPPORTS_ALL_DRIVES = True


def get_drive_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise RuntimeError(
            f"Service account file not found at {SERVICE_ACCOUNT_FILE}. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE or place service_account.json here."
        )
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_bytes(data: bytes, filename: str, mimetype: str, folder_id: str) -> dict:
    """Upload raw bytes to a Drive folder. Returns the created file's metadata."""
    service = get_drive_service()
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype, resumable=False)
    file = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink, webContentLink",
            supportsAllDrives=SUPPORTS_ALL_DRIVES,
        )
        .execute()
    )
    return file


def download_bytes(file_id: str) -> bytes:
    """Download a file's raw bytes from Drive by file ID."""
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=SUPPORTS_ALL_DRIVES)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()


def get_file_metadata(file_id: str) -> dict:
    service = get_drive_service()
    return (
        service.files()
        .get(fileId=file_id, fields="id, name, mimeType, webViewLink, webContentLink", supportsAllDrives=SUPPORTS_ALL_DRIVES)
        .execute()
    )


def list_files(folder_id: str) -> list:
    """List files in a folder, newest first. Used to show upload/processed history without a DB."""
    service = get_drive_service()
    results = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents and trashed = false",
            orderBy="createdTime desc",
            fields="files(id, name, createdTime, webViewLink)",
            supportsAllDrives=SUPPORTS_ALL_DRIVES,
            includeItemsFromAllDrives=SUPPORTS_ALL_DRIVES,
        )
        .execute()
    )
    return results.get("files", [])


def delete_expired_files(folder_id: str, max_age_days: int = 30) -> list:
    """
    Permanently delete files in folder_id older than max_age_days.
    Returns the list of {id, name} deleted. Call this periodically (e.g. on
    each page load, or from a cron job) since Drive has no built-in TTL.
    """
    import datetime as _dt

    service = get_drive_service()
    cutoff = (_dt.datetime.utcnow() - _dt.timedelta(days=max_age_days)).strftime("%Y-%m-%dT%H:%M:%S")
    results = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents and trashed = false and createdTime < '{cutoff}'",
            fields="files(id, name, createdTime)",
            supportsAllDrives=SUPPORTS_ALL_DRIVES,
            includeItemsFromAllDrives=SUPPORTS_ALL_DRIVES,
        )
        .execute()
    )
    expired = results.get("files", [])
    deleted = []
    for f in expired:
        try:
            service.files().delete(fileId=f["id"], supportsAllDrives=SUPPORTS_ALL_DRIVES).execute()
            deleted.append(f)
        except Exception:
            pass  # skip files that fail to delete (e.g. already removed); don't block the request
    return deleted
