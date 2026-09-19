import io
import os
from datetime import datetime

import pandas as pd
from flask import Flask, flash, redirect, render_template, request, send_file, url_for

import drive_utils
from cleaning import clean_dataframe

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}
FILE_EXPIRY_DAYS = int(os.environ.get("FILE_EXPIRY_DAYS", "30"))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_any(data: bytes, filename: str) -> pd.DataFrame:
    ext = filename.rsplit(".", 1)[1].lower()
    if ext == "csv":
        return pd.read_csv(io.BytesIO(data))
    return pd.read_excel(io.BytesIO(data))


@app.route("/", methods=["GET"])
def index():
    try:
        if drive_utils.UPLOADS_FOLDER_ID:
            drive_utils.delete_expired_files(drive_utils.UPLOADS_FOLDER_ID, FILE_EXPIRY_DAYS)
        if drive_utils.PROCESSED_FOLDER_ID:
            drive_utils.delete_expired_files(drive_utils.PROCESSED_FOLDER_ID, FILE_EXPIRY_DAYS)
    except Exception:
        pass  # don't let cleanup failures block the page

    try:
        uploads = drive_utils.list_files(drive_utils.UPLOADS_FOLDER_ID) if drive_utils.UPLOADS_FOLDER_ID else []
        processed = drive_utils.list_files(drive_utils.PROCESSED_FOLDER_ID) if drive_utils.PROCESSED_FOLDER_ID else []
    except Exception as e:
        uploads, processed = [], []
        flash(f"Could not load Drive history: {e}")
    return render_template("index.html", uploads=uploads, processed=processed)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("No file selected.")
        return redirect(url_for("index"))

    file = request.files["file"]
    if file.filename == "" or not allowed_file(file.filename):
        flash("Please upload a .csv, .xlsx, or .xls file.")
        return redirect(url_for("index"))

    raw_bytes = file.read()

    # 1. Save the raw upload to Drive (uploads folder) — this is the "no DB" record of it.
    upload_meta = drive_utils.upload_bytes(
        data=raw_bytes,
        filename=file.filename,
        mimetype=file.mimetype or "application/octet-stream",
        folder_id=drive_utils.UPLOADS_FOLDER_ID,
    )

    # 2. Run the cleaning logic.
    try:
        df = read_any(raw_bytes, file.filename)
        cleaned, issues = clean_dataframe(df)
    except Exception as e:
        flash(f"Processing failed: {e}")
        return redirect(url_for("index"))

    # 3. Upload the cleaned result back to Drive (processed folder).
    out_buffer = io.StringIO()
    cleaned.to_csv(out_buffer, index=False)
    out_name = f"cleaned_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename.rsplit('.', 1)[0]}.csv"
    processed_meta = drive_utils.upload_bytes(
        data=out_buffer.getvalue().encode("utf-8"),
        filename=out_name,
        mimetype="text/csv",
        folder_id=drive_utils.PROCESSED_FOLDER_ID,
    )

    # 4. If any rows had problems (bad phone numbers, missing LAN, etc.),
    #    upload a matching errors CSV so you can see exactly what to fix,
    #    and stash a preview so we can show it right on the results page.
    errors_meta = None
    issues_preview = []
    if len(issues) > 0:
        err_buffer = io.StringIO()
        issues.to_csv(err_buffer, index=False)
        err_name = f"errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename.rsplit('.', 1)[0]}.csv"
        errors_meta = drive_utils.upload_bytes(
            data=err_buffer.getvalue().encode("utf-8"),
            filename=err_name,
            mimetype="text/csv",
            folder_id=drive_utils.PROCESSED_FOLDER_ID,
        )
        issues_preview = issues.head(50).to_dict("records")
        flash(f"Done — {len(cleaned)} row(s) cleaned, {len(issues)} row(s) flagged with issues.")
    else:
        flash(f"Done — {len(cleaned)} row(s) cleaned, no issues found.")

    return render_template(
        "index.html",
        uploads=[],
        processed=[],
        just_processed=processed_meta,
        errors_meta=errors_meta,
        issues_preview=issues_preview,
        issues_total=len(issues),
        cleaned_count=len(cleaned),
    )


@app.route("/result/<file_id>")
def download_page(file_id):
    meta = drive_utils.get_file_metadata(file_id)
    errors_id = request.args.get("errors_id")
    errors_meta = drive_utils.get_file_metadata(errors_id) if errors_id else None
    return render_template(
        "index.html", uploads=[], processed=[meta], just_processed=meta, errors_meta=errors_meta
    )


@app.route("/download/<file_id>")
def download(file_id):
    meta = drive_utils.get_file_metadata(file_id)
    data = drive_utils.download_bytes(file_id)
    return send_file(
        io.BytesIO(data),
        mimetype=meta.get("mimeType", "application/octet-stream"),
        as_attachment=True,
        download_name=meta["name"],
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
