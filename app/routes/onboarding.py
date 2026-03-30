from app import config, db
from app.models import Applicant
from app.utils import permission_required
from datetime import datetime, timezone, timedelta
from flask import abort, Blueprint, flash, jsonify, redirect, request, render_template, url_for
from flask_login import login_required, current_user
from sqlalchemy import text
import io
import json
import os
import pandas as pd
import re
import subprocess

# engine = db.engine

# last_sync_time = None
bp = Blueprint("onboarding", __name__, url_prefix="/onboarding")

UPLOAD_FOLDER = "app/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ERROR_FILE_IMPORT = "app/static/files/applicant_import_errors.csv"
ERROR_FILE_TSN = "app/static/files/tsn_update_errors.csv"

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

@bp.route("/audit", methods=["GET"])
@permission_required('onboarding+add')
def audit():
    """
    Renders audit table page with DataTables.
    """
    run_sync_if_needed()

    applicants = Applicant.query.filter_by(is_deleted=False).all()
    last_sync = get_last_sync()

    return render_template(
        "onboarding/audit.html",
        applicants=applicants,
        last_sync=last_sync.isoformat() if last_sync else None
    )


@bp.route("/update-hs-email", methods=["POST"])
@permission_required('onboarding+add')
def update_hs_email():
    
    data = request.get_json()
    print("🔥 update_hs_email hit", data)

    applicant = Applicant.query.get(data.get("id"))
    if not applicant:
        return jsonify({"error": "Not found"}), 404

    try:
        applicant.hs_email = data.get("hs_email")

        date_str = data.get("hs_email_requested_date")
        if date_str:
            applicant.hs_email_requested_date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            applicant.hs_email_requested_date = None

        db.session.commit()
        print("After:", applicant.hs_email)
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route("/sync-ad", methods=["POST"])
@permission_required('onboarding+add')
def sync_ad_manual():
    try:
        run_sync_if_needed(force=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# -----------------------------
# Helpers
# -----------------------------
def run_sync_if_needed(force=False):
    last_sync = get_last_sync()
    now = datetime.now(timezone.utc)

    if last_sync and last_sync.tzinfo is None:
        # assume DB stored as UTC (common case)
        last_sync = last_sync.replace(tzinfo=timezone.utc)

    if force or not last_sync or (now - last_sync) > timedelta(hours=1):
        print("🔄 Running AD sync...")
        sync_ad_from_tsn_batch()
        set_last_sync(now)
        return True
    else:
        print("⏭ Skipping AD sync (within 1 hour)")
        return False


def get_last_sync():
    row = db.session.execute(
        db.text("SELECT value FROM APP_SETTINGS WHERE key_name = 'ad_last_sync'")
    ).fetchone()

    if row and row.value:
        return datetime.fromisoformat(row.value)

    return None


def set_last_sync(dt):
    db.session.execute(
        db.text("""
            MERGE APP_SETTINGS AS target
            USING (SELECT 'ad_last_sync' AS key_name) AS source
            ON target.key_name = source.key_name
            WHEN MATCHED THEN
                UPDATE SET value = :val
            WHEN NOT MATCHED THEN
                INSERT (key_name, value) VALUES ('ad_last_sync', :val);
        """),
        {"val": dt.isoformat()}
    )
    db.session.commit()


def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def build_ldap_filter(tsn_list):
    parts = "".join([f"(studentNumber={tsn})" for tsn in tsn_list])
    return f"(|{parts})"


def extract_sid(sid_obj):
    if not sid_obj:
        return None
    return sid_obj.get("Value")


def parse_dotnet_date(dotnet_str):
    if not dotnet_str:
        return None

    match = re.search(r"/Date\((\d+)\)/", dotnet_str)
    if not match:
        return None

    millis = int(match.group(1))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return epoch + timedelta(milliseconds=millis)


# -----------------------------
# PowerShell Call
# -----------------------------
def get_ad_users_by_batch(tsn_batch):
    ldap_filter = build_ldap_filter(tsn_batch)

    ps_script = f"""
    $users = Get-ADUser -LDAPFilter "{ldap_filter}" `
        -Properties studentNumber, createTimestamp, passwordLastSet, SamAccountName,
                    GivenName, Surname, DistinguishedName, Enabled, ObjectGUID, SID, UserPrincipalName

    if ($users) {{
        $users | Select-Object `
            createTimestamp,
            DistinguishedName,
            Enabled,
            GivenName,
            Name,
            ObjectClass,
            ObjectGUID,
            PasswordLastSet,
            SamAccountName,
            SID,
            studentNumber,
            Surname,
            UserPrincipalName |
        ConvertTo-Json -Compress
    }}
    """

    result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    print("PowerShell Output:", result.stdout, "Error:", result.stderr, "Return Code:", result.returncode)
    if result.stdout:
        data = json.loads(result.stdout)
        return [data] if isinstance(data, dict) else data

    return []


# -----------------------------
# ORM Sync Function
# -----------------------------
def sync_ad_from_tsn_batch(batch_size=50):
    updates = []
    errors = []

    # ✅ Pull from ORM
    applicants = Applicant.query.filter_by(is_deleted=False).filter(Applicant.tsn.isnot(None)).all()
    
    tsn_map = {a.tsn: a.id for a in applicants}
    tsn_list = list(tsn_map.keys())

    print(f"Total TSNs to sync: {len(tsn_list)}")

    for tsn_batch in chunk_list(tsn_list, batch_size):
        try:
            ad_users = get_ad_users_by_batch(tsn_batch)

            found_tsns = set()

            for ad in ad_users:
                tsn = ad.get("studentNumber")

                if tsn not in tsn_map:
                    continue

                updates.append({
                    "id": tsn_map[tsn],
                    "ad_create_timestamp": parse_dotnet_date(ad.get("createTimestamp")),
                    "ad_distinguished_name": ad.get("DistinguishedName"),
                    "ad_enabled": ad.get("Enabled"),
                    "ad_given_name": ad.get("GivenName"),
                    "ad_name": ad.get("Name"),
                    "ad_object_class": ad.get("ObjectClass"),
                    "ad_object_guid": str(ad.get("ObjectGUID")),
                    "ad_password_last_set": parse_dotnet_date(ad.get("PasswordLastSet")),
                    "ad_sam_account_name": ad.get("SamAccountName"),
                    "ad_sid": extract_sid(ad.get("SID")),
                    "ad_student_number": tsn,
                    "ad_surname": ad.get("Surname"),
                    "ad_user_principal_name": ad.get("UserPrincipalName")
                })

                found_tsns.add(tsn)

            # Missing users
            missing = set(tsn_batch) - found_tsns
            for m in missing:
                errors.append({"tsn": m, "error": "AD user not found"})

        except Exception as e:
            for tsn in tsn_batch:
                errors.append({"tsn": tsn, "error": str(e)})

    # -----------------------------
    # Bulk Update (FAST)
    # -----------------------------
    if updates:
        db.session.bulk_update_mappings(Applicant, updates)
        db.session.commit()

    print(f"✅ Updated {len(updates)} AD records")
    print(f"❌ {len(errors)} missing or failed")

    return {"updated": len(updates), "errors": errors}

@bp.route("/delete-applicant/<int:id>", methods=["POST"])
@permission_required('onboarding+add')
def delete_applicant(id):
    applicant = Applicant.query.get(id)

    if not applicant:
        return jsonify({"success": False, "message": "Not found"}), 404

    try:
        applicant.is_deleted = True
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    
#------------------------------
# Import applicants from CSV
#------------------------------
@bp.route("/import", methods=["GET", "POST"])
@permission_required('onboarding+add')
def import_files():
    if request.method == "POST":
        applicants_file = request.files.get("applicants_file")
        tsn_file = request.files.get("tsn_file")

        results = {}

        if applicants_file:
            path = os.path.join("app/uploads", applicants_file.filename)
            applicants_file.save(path)
            results["applicants"] = import_applicants(path)

        if tsn_file:
            path = os.path.join("app/uploads", tsn_file.filename)
            tsn_file.save(path)
            results["tsn"] = update_tsn(path)

        return render_template("onboarding/import.html", results=results)

    return render_template("onboarding/import.html")


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

    # with engine.begin() as conn:
    conn = db.session
    ensure_accepted_applicants_table(conn)
    pharmcas_set = load_existing_pharmcas(conn)

    for _, row in df.iterrows():
        try:
            pharmcas_id = clean(row.get("PharmCASID"))
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
                "app_pharmcas_id": app_pharmcas_id
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
                pharmcas_id, app_pharmcas_id
            ) VALUES (
                :tracking_number, :last_name, :first_name, :middle_name,
                :birth_month, :birth_day, :affiliate_email, :affiliate_phone,
                :access_start_date, :department_code, :job_title,
                :manager_emp_id, :needs_ad_account, :last4_ssn,
                :nursing_student_type, :additional_info, :accept_date,
                :pharmcas_id, :app_pharmcas_id
            )
        """), inserts)

    db.session.commit()

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

    # with engine.begin() as conn:
    conn = db.session
    ensure_accepted_applicants_table(conn)
    existing = load_existing_pharmcas(conn)
    print(existing)

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
            db.session.commit()

    if errors:
        pd.DataFrame(errors).to_csv(ERROR_FILE_TSN, index=False)

    return {"updated": len(updates), "failed": len(errors)}


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
