"""
Cleaning logic, generalized from cright_data_clean_copy_3.ipynb.

clean_dataframe(df) takes the raw bot-calling sheet and returns:
    (cleaned_df, issues_df)

cleaned_df   -> the cleaned, deduped, enriched dataframe your notebook was
                producing manually.
issues_df    -> one row per problem found (missing LAN, invalid mobile
                number, duplicate LAN, unparseable due-date, unrecognized
                state), with enough identifying info (source row number,
                LAN, mobile number, reason) to go fix the source file.
"""

import numpy as np
import pandas as pd

STATE_LANGUAGE_MAP = {
    "Andhra Pradesh": "TELUGU",
    "Arunachal Pradesh": "HINDI",
    "Assam": "HINDI",
    "Andaman and Nicobar Islands": "HINDI",
    "Bihar": "HINDI",
    "Chhattisgarh": "HINDI",
    "Chandigarh": "HINDI",
    "Delhi": "HINDI",
    "Daman and Diu": "HINDI",
    "Goa": "HINDI",
    "Gujarat": "GUJARATI",
    "Haryana": "HINDI",
    "Himachal Pradesh": "HINDI",
    "Jharkhand": "HINDI",
    "Jammu and Kashmir": "HINDI",
    "Karnataka": "KANNADA",
    "Kerala": "MALAYALAM",
    "Ladakh": "HINDI",
    "Lakshadweep": "HINDI",
    "Madhya Pradesh": "HINDI",
    "Maharashtra": "MARATHI",
    "Manipur": "HINDI",
    "Meghalaya": "HINDI",
    "Mizoram": "HINDI",
    "Nagaland": "HINDI",
    "Odisha": "ODIA",
    "Punjab": "HINDI",
    "Puducherry": "TAMIL",
    "Rajasthan": "HINDI",
    "Sikkim": "HINDI",
    "Tamil Nadu": "TAMIL",
    "Telangana": "TELUGU",
    "Tripura": "HINDI",
    "Uttar Pradesh": "HINDI",
    "Uttarakhand": "HINDI",
    "West Bengal": "BENGALI",
    "India": "HINDI",
    "Dadra and Nagar Haveli": "HINDI",
}

REQUIRED_COLUMNS = [
    "LAN",
    "Customer Name",
    "Mobile Number",
    "State_2",
    "Month Pending From",
    "Emi Amount",
    "POS Amount",
    "Firm Name",
]


def _issue_row(row, reason, extra=""):
    """Build one issues_df row with the identifying info a human needs to find/fix it in the source file."""
    return {
        "source_row": int(row.name) + 2,  # +2: 1-indexed + header row, matches what you'd see in Excel
        "LAN": row.get("LAN", ""),
        "Customer Name": row.get("Customer Name", ""),
        "Mobile Number (raw)": row.get("Mobile Number", ""),
        "issue": reason,
        "detail": extra,
    }


def clean_dataframe(df: pd.DataFrame):
    df = df.copy()
    df.columns = df.columns.str.strip()
    df = df.reset_index(drop=True)

    issues = []

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Uploaded file is missing required column(s): {', '.join(missing_cols)}. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}"
        )

    # --- Missing LAN -------------------------------------------------------
    no_lan_mask = df["LAN"].isna() | (df["LAN"].astype(str).str.strip() == "")
    for _, row in df[no_lan_mask].iterrows():
        issues.append(_issue_row(row, "Missing LAN (loan account number)"))
    df = df[~no_lan_mask].copy()

    # --- Mobile number validation -------------------------------------------
    # Excel often stores phone numbers as floats (e.g. 8688516093.0). Strip a
    # trailing ".0" BEFORE removing non-digit characters, otherwise the
    # decimal point disappears but its "0" stays behind and silently turns a
    # valid 10-digit number into a fake 11-digit one.
    raw_phone = df["Mobile Number"].fillna("").astype(str).str.strip()
    raw_phone = raw_phone.str.replace(r"\.0+$", "", regex=True)
    df["phone_clean"] = raw_phone.str.replace(r"\D", "", regex=True)
    bad_phone_mask = df["phone_clean"].str.len() != 10
    for idx, row in df[bad_phone_mask].iterrows():
        digits = row["phone_clean"]
        if digits == "" or digits == "nan":
            reason = "Missing mobile number"
        elif len(digits) < 10:
            reason = "Mobile number too short"
        else:
            reason = "Mobile number too long"
        issues.append(_issue_row(row, reason, f"got '{raw_phone.loc[idx]}' -> {len(digits)} digits after cleaning"))
    df = df[~bad_phone_mask].copy()
    df["Mobile Number"] = df["phone_clean"]
    df.drop(columns=["phone_clean"], inplace=True)

    new_df = df[REQUIRED_COLUMNS].copy()

    # --- Clean numeric-looking amount columns -------------------------------
    new_df["POS Amount"] = new_df["POS Amount"].astype(str).str.replace(",", "", regex=False)
    new_df["Emi Amount"] = new_df["Emi Amount"].astype(str).str.replace(",", "", regex=False)

    # --- Rename + parse the EMI due date ------------------------------------
    new_df.rename(columns={"Month Pending From": "Emi Date"}, inplace=True)
    parsed_dates = pd.to_datetime(new_df["Emi Date"], format="%d/%m/%Y", errors="coerce")
    bad_date_mask = new_df["Emi Date"].notna() & parsed_dates.isna()
    for idx in new_df[bad_date_mask].index:
        row = new_df.loc[idx]
        issues.append(_issue_row(row, "Emi Date couldn't be parsed (expected dd/mm/yyyy)", f"got '{row['Emi Date']}'"))
    new_df["Emi Date"] = parsed_dates
    new_df["Due Date"] = pd.to_datetime(new_df["Emi Date"], dayfirst=True, errors="coerce").dt.strftime("%d/%m/%Y")

    # --- Duplicate LAN -------------------------------------------------------
    dup_mask = new_df.duplicated(subset=["LAN"], keep="first")
    for idx in new_df[dup_mask].index:
        row = new_df.loc[idx]
        issues.append(_issue_row(row, "Duplicate LAN (row dropped, first occurrence kept)"))
    new_df = new_df[~dup_mask].copy()

    # --- Derived fields --------------------------------------------------------
    new_df["priority"] = new_df["LAN"].astype(str).str[-4:]
    new_df["language"] = new_df["State_2"].map(STATE_LANGUAGE_MAP)
    unmapped_state_mask = new_df["language"].isna() & new_df["State_2"].notna()
    for idx in new_df[unmapped_state_mask].index:
        row = new_df.loc[idx]
        issues.append(_issue_row(row, "State_2 not recognized, language left blank", f"got '{row['State_2']}'"))
    new_df["address_type"] = "HOME"
    new_df["address"] = new_df["State_2"]

    issues_df = pd.DataFrame(
        issues,
        columns=["source_row", "LAN", "Customer Name", "Mobile Number (raw)", "issue", "detail"],
    )

    return new_df, issues_df
