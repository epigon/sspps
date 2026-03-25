from app import config, db
# from app.forms import CategoryForm, ContactForm
from app.models import Applicant
# from app.cred import HR_EMAIL_ADDRESS
from app.utils import permission_required
from flask import abort, Blueprint, flash, jsonify, redirect, request, render_template, url_for
from flask_login import login_required, current_user
# from flask_wtf.csrf import generate_csrf
# from sqlalchemy.inspection import inspect
# import subprocess
from flask import request, jsonify
from app.models import Applicant
from app import db
from datetime import datetime
from flask import render_template, send_file
import io
import pandas as pd
import subprocess
import json
import re
from datetime import datetime, timezone, timedelta

# last_sync_time = None
bp = Blueprint("onboarding", __name__, url_prefix="/onboarding")

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

    applicants = Applicant.query.all()
    last_sync = get_last_sync()

    return render_template(
        "onboarding/audit.html",
        applicants=applicants,
        last_sync=last_sync
    )


@bp.route("/update-hs-email", methods=["POST"])
@permission_required('onboarding+add')
def update_hs_email():
    data = request.get_json()

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
    now = datetime.utcnow()

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

    result = subprocess.run(
        ["powershell", "-Command", ps_script],
        capture_output=True,
        text=True
    )

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
    applicants = Applicant.query.filter(Applicant.tsn.isnot(None)).all()

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