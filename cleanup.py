"""
Standalone expiry cleanup — deletes files older than FILE_EXPIRY_DAYS from
both Drive folders. The web app also runs this on every page load, but that
only fires when someone visits. Schedule this script separately (cron,
systemd timer, or your host's scheduled-jobs feature) to guarantee expiry
even with no traffic, e.g. daily:

    0 3 * * * /path/to/venv/bin/python /path/to/cright-app/cleanup.py

Requires the same environment variables as app.py (GOOGLE_SERVICE_ACCOUNT_FILE,
DRIVE_UPLOADS_FOLDER_ID, DRIVE_PROCESSED_FOLDER_ID, FILE_EXPIRY_DAYS).
"""

import os

import drive_utils

FILE_EXPIRY_DAYS = int(os.environ.get("FILE_EXPIRY_DAYS", "30"))

if __name__ == "__main__":
    for label, folder_id in [
        ("uploads", drive_utils.UPLOADS_FOLDER_ID),
        ("processed", drive_utils.PROCESSED_FOLDER_ID),
    ]:
        if not folder_id:
            print(f"Skipping {label}: no folder ID configured")
            continue
        deleted = drive_utils.delete_expired_files(folder_id, FILE_EXPIRY_DAYS)
        print(f"{label}: deleted {len(deleted)} file(s) older than {FILE_EXPIRY_DAYS} days")
        for f in deleted:
            print(f"  - {f['name']} (created {f.get('createdTime')})")
