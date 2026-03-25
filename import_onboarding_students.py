from app import create_app
from app.cred import server, user, pwd, database, odbcdriver
from datetime import datetime
from sqlalchemy import create_engine, text
import pandas as pd
import os
import subprocess
import json
import re
from datetime import datetime, timedelta, timezone


app = create_app()

connection_string = f'mssql+pyodbc://{user}:{pwd}@{server}/{database}?driver={odbcdriver}&TrustServerCertificate=yes'
engine = create_engine(connection_string, fast_executemany=True)

ERROR_FILE_IMPORT = "app/static/files/applicant_import_errors.csv"
ERROR_FILE_TSN = "app/static/files/tsn_update_errors.csv"

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def clean(val):
    if pd.isna(val):
        return None
    return str(val).strip()


def parse_date(val):
    try:
        return pd.to_datetime(val, errors="coerce")
    except Exception:
        return None


def normalize_yes_no(val):
    val = clean(val)
    if not val:
        return 0
    return 1 if val.lower() in ["yes", "y", "true", "1"] else 0


def load_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".csv":
        df = pd.read_csv(filepath)
    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(filepath, dtype=str)
    else:
        raise ValueError("Unsupported file type")

    df.columns = [c.strip() for c in df.columns]
    return df


def load_existing_pharmcas(conn):
    rows = conn.execute(text("SELECT pharmcas_id FROM dbo.ACCEPTED_APPLICANTS WHERE pharmcas_id IS NOT NULL"))
    return set(r.pharmcas_id for r in rows)

def ensure_accepted_applicants_table(conn):
    conn.execute(text("""
    IF NOT EXISTS (
        SELECT * FROM sys.objects 
        WHERE object_id = OBJECT_ID(N'dbo.ACCEPTED_APPLICANTS') 
        AND type = 'U'
    )
    BEGIN
        CREATE TABLE [dbo].[ACCEPTED_APPLICANTS](
            [id] [int] IDENTITY(1,1) NOT NULL,
            [tracking_number] [nvarchar](50) NULL,
            [last_name] [nvarchar](100) NOT NULL,
            [first_name] [nvarchar](100) NOT NULL,
            [middle_name] [nvarchar](100) NULL,
            [birth_month] [tinyint] NULL,
            [birth_day] [tinyint] NULL,
            [affiliate_email] [nvarchar](255) NOT NULL,
            [affiliate_phone] [nvarchar](50) NULL,
            [access_start_date] [datetime] NULL,
            [accept_date] [datetime] NULL,
            [department_code] [nvarchar](50) NULL,
            [job_title] [nvarchar](255) NULL,
            [manager_emp_id] [nvarchar](50) NULL,
            [needs_ad_account] [bit] NOT NULL,
            [last4_ssn] [char](4) NULL,
            [nursing_student_type] [nvarchar](100) NULL,
            [additional_info] [nvarchar](max) NULL,
            [pharmcas_id] [nvarchar](100) NULL,
            [created_at] [datetime] NOT NULL,
            [updated_at] [datetime] NULL,
            [tsn] [nvarchar](100) NULL,
            [app_pharmcas_id] [nvarchar](100) NULL,
            [ad_create_timestamp] [datetime] NULL,
            [ad_distinguished_name] [nvarchar](500) NULL,
            [ad_enabled] [bit] NULL,
            [ad_given_name] [nvarchar](100) NULL,
            [ad_name] [nvarchar](255) NULL,
            [ad_object_class] [nvarchar](100) NULL,
            [ad_object_guid] [nvarchar](100) NULL,
            [ad_password_last_set] [datetime] NULL,
            [ad_sam_account_name] [nvarchar](100) NULL,
            [ad_sid] [nvarchar](200) NULL,
            [ad_student_number] [nvarchar](100) NULL,
            [ad_surname] [nvarchar](100) NULL,
            [ad_user_principal_name] [nvarchar](255) NULL,
            [hs_email_requested_date] [datetime] NULL,
            [hs_email] [nvarchar](100) NULL,
            CONSTRAINT [PK__ACCEPTED__3213E83F4F697542] PRIMARY KEY CLUSTERED 
            (
                [id] ASC
            ) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
        ) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]

        ALTER TABLE [dbo].[ACCEPTED_APPLICANTS] ADD  CONSTRAINT [DF__ACCEPTED___needs__07970BFE]  DEFAULT ((0)) FOR [needs_ad_account]

        ALTER TABLE [dbo].[ACCEPTED_APPLICANTS] ADD  CONSTRAINT [DF__ACCEPTED___creat__088B3037]  DEFAULT (getdate()) FOR [created_at]

        ALTER TABLE [dbo].[ACCEPTED_APPLICANTS]  WITH CHECK ADD  CONSTRAINT [CK_ACCEPTED_APPLICANTS_BIRTH_DAY] CHECK  (([birth_day]>=(1) AND [birth_day]<=(31)))

        ALTER TABLE [dbo].[ACCEPTED_APPLICANTS] CHECK CONSTRAINT [CK_ACCEPTED_APPLICANTS_BIRTH_DAY]

        ALTER TABLE [dbo].[ACCEPTED_APPLICANTS]  WITH CHECK ADD  CONSTRAINT [CK_ACCEPTED_APPLICANTS_BIRTH_MONTH] CHECK  (([birth_month]>=(1) AND [birth_month]<=(12)))

        ALTER TABLE [dbo].[ACCEPTED_APPLICANTS] CHECK CONSTRAINT [CK_ACCEPTED_APPLICANTS_BIRTH_MONTH]

        ALTER TABLE [dbo].[ACCEPTED_APPLICANTS]  WITH CHECK ADD  CONSTRAINT [CK_ACCEPTED_APPLICANTS_SSN] CHECK  (([last4_ssn] IS NULL OR [last4_ssn] like '[0-9][0-9][0-9][0-9]'))

        ALTER TABLE [dbo].[ACCEPTED_APPLICANTS] CHECK CONSTRAINT [CK_ACCEPTED_APPLICANTS_SSN]
        
    END
    """))

    conn.execute(text("""
    IF NOT EXISTS (
        SELECT * FROM sys.objects 
        WHERE object_id = OBJECT_ID(N'dbo.APP_SETTINGS') 
        AND type = 'U'
    )
    BEGIN
        CREATE TABLE APP_SETTINGS (
            key_name NVARCHAR(100) PRIMARY KEY,
            value NVARCHAR(255)
        );
    END
    """))

# -------------------------------------------------
# IMPORT ACCEPTED_APPLICANTS
# -------------------------------------------------
def import_applicants(filepath):
    df = load_file(filepath)

    errors = []
    inserts = []

    with engine.begin() as conn:
        ensure_accepted_applicants_table(conn)
        pharmcas_set = load_existing_pharmcas(conn)

        for _, row in df.iterrows():
            try:
                pharmcas_id = clean(row.get("P-PharmCASID"))
                app_pharmcas_id = clean(row.get("Applications PharmCasID"))
                email = clean(row.get("Affiliate Email"))

                if not email:
                    raise ValueError("Missing email")

                if pharmcas_id and pharmcas_id in pharmcas_set:
                    raise ValueError("Duplicate PharmCASID")

                record = {
                    "tracking_number": clean(row.get("Tracking Number")),
                    "last_name": clean(row.get("Legal Last Name")),
                    "first_name": clean(row.get("Legal First Name")),
                    "middle_name": clean(row.get("Middle Name")),
                    "birth_month": clean(row.get("Month of Birth (MM)")),
                    "birth_day": clean(row.get("Date of Birth (DD)")),
                    "affiliate_email": email,
                    "affiliate_phone": clean(row.get("Affiliate Phone")),
                    "access_start_date": parse_date(row.get("Access Start Date")),
                    "department_code": clean(row.get("Department Code")),
                    "job_title": clean(row.get("LMS Title  (UCLC Secondary Job Title)")),
                    "manager_emp_id": clean(row.get("Manager Emp ID")),
                    "needs_ad_account": normalize_yes_no(row.get("Does Affiliate Need Active Directory Account?")),
                    "last4_ssn": clean(row.get("Last 4 SSN")),
                    "nursing_student_type": clean(row.get("Nursing Student Type")),
                    "additional_info": clean(row.get("Additional Information")),
                    "accept_date": parse_date(row.get("Accept Date")),
                    "pharmcas_id": pharmcas_id,
                    "app_pharmcas_id": app_pharmcas_id,
                    "created_at": datetime.now()
                }

                inserts.append(record)

                if pharmcas_id:
                    pharmcas_set.add(pharmcas_id)

            except Exception as e:
                r = row.to_dict()
                r["error"] = str(e)
                errors.append(r)

        if inserts:
            conn.execute(text("""
                INSERT INTO dbo.ACCEPTED_APPLICANTS (
                    tracking_number, last_name, first_name, middle_name,
                    birth_month, birth_day, affiliate_email, affiliate_phone,
                    access_start_date, department_code, job_title,
                    manager_emp_id, needs_ad_account, last4_ssn,
                    nursing_student_type, additional_info, accept_date,
                    pharmcas_id, app_pharmcas_id, created_at
                ) VALUES (
                    :tracking_number, :last_name, :first_name, :middle_name,
                    :birth_month, :birth_day, :affiliate_email, :affiliate_phone,
                    :access_start_date, :department_code, :job_title,
                    :manager_emp_id, :needs_ad_account, :last4_ssn,
                    :nursing_student_type, :additional_info, :accept_date,
                    :pharmcas_id, :app_pharmcas_id,:created_at
                )
            """), inserts)

    if errors:
        pd.DataFrame(errors).to_csv(ERROR_FILE_IMPORT, index=False)

    return {"inserted": len(inserts), "failed": len(errors)}

# -------------------------------------------------
# UPDATE TSN
# -------------------------------------------------
def update_tsn(filepath):
    df = load_file(filepath)

    errors = []
    updates = []

    with engine.begin() as conn:
        ensure_accepted_applicants_table(conn)
        existing = load_existing_pharmcas(conn)

        for _, row in df.iterrows():
            try:
                tsn = clean(row.get("TSN"))
                pharmcas_id = clean(row.get("PHARMCASID"))

                if not tsn or not pharmcas_id:
                    raise ValueError("Missing TSN or PharmCASID")

                if pharmcas_id not in existing:
                    raise ValueError("PharmCASID not found")

                updates.append({"pharmcas_id": pharmcas_id, "tsn": tsn})

            except Exception as e:
                r = row.to_dict()
                r["error"] = str(e)
                errors.append(r)

            if updates:
                conn.execute(text("TRUNCATE TABLE dbo.TSN_STAGE"))

                conn.execute(text("""
                    INSERT INTO dbo.TSN_STAGE (pharmcas_id, tsn)
                    VALUES (:pharmcas_id, :tsn)
                """), updates)

                conn.execute(text("""
                    UPDATE A
                    SET A.tsn = T.tsn
                    FROM dbo.ACCEPTED_APPLICANTS A
                    JOIN dbo.TSN_STAGE T
                        ON A.pharmcas_id = T.pharmcas_id
                """))

    if errors:
        pd.DataFrame(errors).to_csv(ERROR_FILE_TSN, index=False)

    return {"updated": len(updates), "failed": len(errors)}

# -------------------------------------------------
# Flask Routes
# -------------------------------------------------
from flask import Blueprint, request, jsonify

bp = Blueprint("applicant_ops", __name__)
UPLOAD_FOLDER = "app/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@bp.route("/upload-applicants", methods=["POST"])
def upload_applicants():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file"}), 400

    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    result = import_applicants(path)
    return jsonify(result)


@bp.route("/upload-tsn", methods=["POST"])
def upload_tsn():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file"}), 400

    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    result = update_tsn(path)
    return jsonify(result)

# -------------------------------------------------
# Main
# -------------------------------------------------
if __name__ == "__main__":
    applicants_file = "app/static/files/CO2030.xlsx"
    tsn_file = "app/static/files/CO2030-tsn.xlsx"

    print("Running applicant import...")
    print(import_applicants(applicants_file))

    print("Running TSN update...")
    print(update_tsn(tsn_file))
