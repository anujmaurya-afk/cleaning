"""
Cleaning logic, generalized from cright_data_clean_copy_3.ipynb.

clean_dataframe(df) takes the raw bot-calling sheet and returns the cleaned,
deduped, enriched dataframe your notebook was producing manually.
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


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()

    # Drop rows with no loan account number
    df.dropna(subset=["LAN"], inplace=True)

    # Normalize mobile numbers to digits only, keep valid 10-digit ones
    df["phone_clean"] = df["Mobile Number"].astype(str).str.replace(r"\D", "", regex=True)
    df = df[df["phone_clean"].str.len() == 10].copy()
    df["Mobile Number"] = df["phone_clean"]
    df.drop(columns=["phone_clean"], inplace=True)

    # Keep only the columns needed downstream
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Uploaded file is missing required column(s): {', '.join(missing)}. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}"
        )
    new_df = df[REQUIRED_COLUMNS].copy()

    # Clean numeric-looking amount columns
    new_df["POS Amount"] = new_df["POS Amount"].astype(str).str.replace(",", "", regex=False)
    new_df["Emi Amount"] = new_df["Emi Amount"].astype(str).str.replace(",", "", regex=False)

    # Rename + parse the EMI due date
    new_df.rename(columns={"Month Pending From": "Emi Date"}, inplace=True)
    new_df["Emi Date"] = pd.to_datetime(new_df["Emi Date"], format="%d/%m/%Y", errors="coerce")
    new_df["Due Date"] = pd.to_datetime(new_df["Emi Date"], dayfirst=True, errors="coerce").dt.strftime("%d/%m/%Y")

    # Drop duplicate loan accounts, keep first
    new_df.drop_duplicates(subset=["LAN"], keep="first", inplace=True)

    # Derived fields
    new_df["priority"] = new_df["LAN"].astype(str).str[-4:]
    new_df["language"] = new_df["State_2"].map(STATE_LANGUAGE_MAP)
    new_df["address_type"] = "HOME"
    new_df["address"] = new_df["State_2"]

    return new_df
