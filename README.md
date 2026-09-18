# CRIGHT File Cleaner — Drive-backed, no DB

Flask app: user uploads a raw bot-calling sheet → it's saved to Google Drive →
cleaned with the same logic from your notebook → cleaned CSV is saved back to
Drive → user gets a download link. Google Drive is the only storage; no
database.

## 1. One-time Google Drive setup

1. ✅ Already done — service account created in Cloud project
   `clean-framework-508311-k5`, key file:
   `clean-framework-508311-k5-e9e0b32ccd1b.json`, email:
   `cleaning-files@clean-framework-508311-k5.iam.gserviceaccount.com`.
2. **Copy the key file into this project folder** (next to `app.py`) so
   `.env`'s `GOOGLE_SERVICE_ACCOUNT_FILE` can find it.
3. **Share both Drive folders** with
   `cleaning-files@clean-framework-508311-k5.iam.gserviceaccount.com` as
   **Editor** — this is required, service accounts see nothing that isn't
   explicitly shared with them:
   - Uploads folder: https://drive.google.com/drive/folders/1NFBfeBMbQSCVcH3U5Nohe2b0YdGj4uuF
   - Processed folder: https://drive.google.com/drive/folders/1tcjdXPKBYEOkuTM2LaNqTETZX-pvJJyV
4. If these folders live in your **personal** Drive (not a Shared Drive),
   that's fine for Editor-sharing — but remember service accounts have no
   storage quota of their own, so uploaded files count against *your* Drive
   storage, which is expected here.

## 2. Configure

`.env` is already filled in:

```
GOOGLE_SERVICE_ACCOUNT_FILE=clean-framework-508311-k5-e9e0b32ccd1b.json
DRIVE_UPLOADS_FOLDER_ID=1NFBfeBMbQSCVcH3U5Nohe2b0YdGj4uuF
DRIVE_PROCESSED_FOLDER_ID=1tcjdXPKBYEOkuTM2LaNqTETZX-pvJJyV
FLASK_SECRET_KEY=change-me-to-something-random
FILE_EXPIRY_DAYS=30
```

Change `FLASK_SECRET_KEY` to something random before deploying. Load the
file however you normally do (e.g. `python-dotenv`, or export the vars in
your shell / hosting platform's environment settings) — Flask doesn't read
`.env` automatically on its own.

## 3. Run locally

```bash
pip install -r requirements.txt
export $(cat .env | xargs)   # or use python-dotenv
python app.py
```

Visit http://localhost:5000, upload a `.csv`/`.xlsx` file with columns:
`LAN, Customer Name, Mobile Number, State_2, Month Pending From, Emi Amount,
POS Amount, Firm Name`. You'll get a cleaned CSV back, and it also lands in
your Drive `processed` folder.

## 4. Deploy

Any small host works since there's no DB to provision — e.g. Render, Railway,
Fly.io, or a plain VM with gunicorn:

```bash
gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

Set the same environment variables on the host, and upload
`service_account.json` as a secret file (don't commit it to git).

## Files

- `app.py` — Flask routes: `/` (form + history), `/upload`, `/download/<id>`
- `drive_utils.py` — Drive auth + upload/download/list/delete-expired helpers
- `cleaning.py` — the cleaning logic pulled from your notebook, as a
  reusable `clean_dataframe(df)` function
- `cleanup.py` — standalone script to delete files older than
  `FILE_EXPIRY_DAYS` (default 30); run it on a schedule (see below)
- `templates/index.html` — bare-bones upload UI

## File expiry (30 days)

Files older than `FILE_EXPIRY_DAYS` (default 30, set in `.env`) get deleted
from both the uploads and processed Drive folders. This runs two ways:

- **On every visit to `/`** — the app checks and deletes expired files before
  rendering the page. Fine for occasional personal use, but does nothing if
  nobody visits the site for a while.
- **On a schedule (recommended for reliability)** — run `cleanup.py`
  independently, e.g. via cron:
  ```bash
  0 3 * * * /path/to/venv/bin/python /path/to/cright-app/cleanup.py
  ```
  or your host's scheduled-jobs / cron-job feature if it's a PaaS like
  Render/Railway.

Deletion is permanent (bypasses Drive trash) — lower `FILE_EXPIRY_DAYS` in
`.env` only if you're sure you don't need those files back.

## Notes / things to adjust for your real data

- `cleaning.py` expects specific column names (see `REQUIRED_COLUMNS`). Your
  notebook had several commented-out variants (different date column names,
  different filters) — if your input files vary, either standardize the
  export or add branching logic here.
- Currently synchronous: for very large files you may want to move the
  cleaning step to a background worker/queue instead of blocking the request.
- No auth on the upload endpoint — add something (API key, login) before
  exposing this publicly, since it writes to your Drive.
