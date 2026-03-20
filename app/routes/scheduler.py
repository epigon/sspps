from app.cred import PANOPTO_API_BASE, PANOPTO_CLIENT_ID, PANOPTO_CLIENT_SECRET
from app.models import db, ScheduledRecording
from app.utils import permission_required
from .canvas import get_canvas_courses, get_canvas_events, chunked_list, get_enrollment_terms, get_canvas_courses_by_term
from datetime import datetime, timedelta, timezone
from dateutil import parser  # safer parsing
from flask import Flask, redirect, render_template, request, Blueprint, jsonify, session, has_request_context, url_for
from flask_login import login_required
from os.path import dirname, join, abspath
from functools import wraps
# from .panopto_oauth2 import PanoptoOAuth2
from requests_oauthlib import OAuth2Session
from urllib.parse import urlparse, urlunparse
import argparse
import os
import pytz
import requests
import sys
import time
import urllib3

sys.path.insert(0, abspath(join(dirname(__file__), '..', 'common')))

bp = Blueprint('scheduler', __name__, url_prefix='/scheduler')

PACIFIC_TZ = pytz.timezone("America/Los_Angeles")
PANOPTO_PARENT_FOLDER = '66a0fa02-94a9-4fb9-ae75-aa71011bd7fc'

CALENDAR_FOLDER = os.path.join("app","static","calendars")
os.makedirs(CALENDAR_FOLDER, exist_ok=True)

mainAccountID = 1	
HSAccountID = 9	
SOMAccountID = 445	
SSPPSAccountID = 50 

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

from functools import wraps
from flask import session, redirect, url_for, request

def panopto_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("panopto_token"):
            # Save current URL so we can redirect back after login
            session["next_page"] = request.url
            return redirect(url_for("scheduler.panopto_login"))
        return f(*args, **kwargs)
    return decorated_function

# --- Panopto login helper ---
@bp.route("/panopto/login")
def panopto_login():
    hostname = urlparse(request.host_url).hostname
    if hostname in ('localhost', '127.0.0.1'):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # ✅ allow HTTP for localhost
    else:
        # Ensure oauthlib library requires HTTPS redirection (default behavior).
        if "OAUTHLIB_INSECURE_TRANSPORT" in os.environ:
            del os.environ["OAUTHLIB_INSECURE_TRANSPORT"]

    # Make sure redirect URL matches what Panopto allows
    redirect_uri = url_for("scheduler.oauth2_callback", _external=True)

    # Scope: openid + api + offline_access (refresh token)
    scope = ["openid", "api", "offline_access"]

    # Create OAuth2Session
    oauth = OAuth2Session(
        client_id=PANOPTO_CLIENT_ID,
        redirect_uri=redirect_uri,
        scope=scope
    )

    # Get the authorization URL
    authorization_url, state = oauth.authorization_url(
        f"https://{PANOPTO_API_BASE}/Panopto/oauth2/connect/authorize"
    )

    # Save state for callback verification
    session["oauth_state"] = state

    # Redirect user to Panopto login page
    return redirect(authorization_url)


@bp.route("/oauth2/callback")
def oauth2_callback():
    # Recreate the OAuth2Session with the saved state
    oauth = OAuth2Session(
        client_id=PANOPTO_CLIENT_ID,
        redirect_uri=url_for("scheduler.oauth2_callback", _external=True),
        state=session.get("oauth_state")
    )

    # Exchange authorization code for access token
    token = oauth.fetch_token(
        f"https://{PANOPTO_API_BASE}/Panopto/oauth2/connect/token",
        client_secret=PANOPTO_CLIENT_SECRET,
        authorization_response=request.url
    )

    # Save token in session for reuse
    session["panopto_token"] = token

    return "Panopto authorization complete. You may close this window."

def get_panopto_session():
    token = session.get("panopto_token")

    if not token:
        raise Exception("User not authenticated with Panopto")

    oauth = OAuth2Session(
        client_id=PANOPTO_CLIENT_ID,
        token=token,
        auto_refresh_url=f"https://{PANOPTO_API_BASE}/Panopto/oauth2/connect/token",
        auto_refresh_kwargs={
            "client_id": PANOPTO_CLIENT_ID,
            "client_secret": PANOPTO_CLIENT_SECRET,
        },
        token_updater=lambda t: session.update({"panopto_token": t})
    )

    return oauth


def inspect_response(response):
    """
    Inspect a requests.Response object from Panopto API.
    """
    try:
        # ✅ Success
        if response.status_code // 100 == 2:
            try:
                return {"id": response.json().get("Id")}
            except ValueError:
                return {"id": None}

        # 🔐 Unauthorized
        if response.status_code == requests.codes.unauthorized:
            return {"unauthorized": True}

        # ⚠️ Bad Request
        if response.status_code == 400:
            try:
                data = response.json()
                error = data.get("Error", {})
                error_code = error.get("ErrorCode", "UnknownError")
                message = error.get("Message", "Unknown error from Panopto.")

                if error_code == "ScheduledRecordingConflict":
                    friendly = f"Scheduling conflict: {message}"
                else:
                    friendly = message

                return {"error": friendly, "details": data}
            except ValueError:
                return {"error": response.text, "details": None}

        # 💥 SERVER ERROR (500s) — THIS IS WHAT YOU WANT
        if response.status_code >= 500:
            print("🔥 PANOPTO 500 ERROR")
            print("URL:", response.url)
            print("Status:", response.status_code)
            print("Response Text:", response.text)

            return {
                "error": "Panopto server error. Please try again later.",
                "details": response.text,
                "status_code": response.status_code
            }

        # ❓ Other errors (403, 404, etc.)
        print("⚠️ UNHANDLED RESPONSE")
        print("URL:", response.url)
        print("Status:", response.status_code)
        print("Response:", response.text)

        return {
            "error": f"Unexpected error ({response.status_code})",
            "details": response.text
        }

    except Exception as e:
        print("🚨 inspect_response FAILED")
        import traceback
        traceback.print_exc()

        return {
            "error": "Internal error processing response",
            "details": str(e)
        }


def inspect_response_is_unauthorized(response):
    '''
    Inspect the response of a requets' call, and return True if the response was Unauthorized.
    An exception is thrown at other error responses.
    Reference: https://stackoverflow.com/a/24519419
    '''
    if response.status_code // 100 == 2:
        # Success on 2xx response.
        return False

    if response.status_code == requests.codes.unauthorized:
        # print('Unauthorized. Access token is invalid.')
        return True

    if response.status_code == 400:  # Bad Request (conflict, invalid input, etc.)
        try:
            return {"error": response.json()}
        except ValueError:
            return {"error": response.text}

    # Throw unhandled cases.
    response.raise_for_status()


@panopto_required
def get_panopto_folders():
    try:
        session_oauth = get_panopto_session()

        folders = []
        page_number = 0
        page_size = 50

        while True:
            url = f"https://{PANOPTO_API_BASE}/Panopto/api/v1/folders/{PANOPTO_PARENT_FOLDER}/children"
            params = {
                "pageNumber": page_number,
                "maxNumberResults": page_size
            }

            resp = session_oauth.get(url, params=params)

            # 🔍 Handle response safely
            if resp.status_code >= 500:
                print("🔥 Panopto 500 error (folders):", resp.text)
                break

            if resp.status_code == 401:
                raise Exception("Panopto token expired or unauthorized")

            data = resp.json()
            results = data.get("Results", [])

            for folder in results:
                folders.append({
                    "id": folder["Id"],
                    "name": folder["Name"]
                })

            if len(results) < page_size:
                break

            page_number += 1

        return folders

    except Exception as e:
        import traceback
        print("🚨 get_panopto_folders FAILED")
        traceback.print_exc()
        return []


@panopto_required
def get_panopto_recorders():
    try:
        session_oauth = get_panopto_session()

        recorders = []
        page_number = 0
        page_size = 50

        while True:
            url = f"https://{PANOPTO_API_BASE}/Panopto/api/remoteRecorders"
            params = {
                "pageNumber": page_number,
                "maxNumberResults": page_size
            }

            resp = session_oauth.get(url, params=params)

            # 🔍 Handle response safely
            if resp.status_code >= 500:
                print("🔥 Panopto 500 error (recorders):", resp.text)
                break

            if resp.status_code == 401:
                raise Exception("Panopto token expired or unauthorized")

            data = resp.json()

            for recorder in data:
                recorders.append({
                    "id": recorder["Id"],
                    "name": recorder["Name"]
                })

            if len(data) < page_size:
                break

            page_number += 1

        return recorders

    except Exception as e:
        import traceback
        print("🚨 get_panopto_recorders FAILED")
        traceback.print_exc()
        return []

@bp.route('/events')
@panopto_required
@permission_required('panopto_scheduler+add, panopto_scheduler+edit')
def list_canvas_events():
    account = request.args.get("account")
    term_id = request.args.get("term_id")

    # Step 1: No account/term selected yet -> show selection screen
    if not account or not term_id:
        # You may want to control which accounts are available
        accounts = [
            {"code": "SSPPS", "name": "Skaggs School of Pharmacy"},
            {"code": "SOM", "name": "School of Medicine"},
            {"code": "HS", "name": "Health Sciences"},
            {"code": "MAIN", "name": "Main Account"},
        ]
        terms = get_enrollment_terms()
        terms = [
            {"id": t["id"], "name": t.get("name", f"Term {t['id']}")}
            for t in terms
        ]
        return render_template("scheduler/select_term_account.html",
                               accounts=accounts,
                               terms=terms)

    # Step 2: User selected a term -> fetch courses + events
    start_overall = time.perf_counter()

    # 🔹 Get term details (so we can grab its dates)
    terms = get_enrollment_terms()
    selected_term = next((t for t in terms if str(t["id"]) == str(term_id)), None)
    if not selected_term:
        return f"Term {term_id} not found", 400

    # 🔹 Parse start/end dates from the term
    start_date = None
    end_date = None
    if selected_term.get("start_at"):
        start_date = parser.isoparse(selected_term["start_at"])
    if selected_term.get("end_at"):
        end_date = parser.isoparse(selected_term["end_at"])

    # Fall back in case Canvas doesn’t provide
    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=30)
    if not end_date:
        end_date = datetime.utcnow() + timedelta(days=90)

    print(f"📅 Using term date range: {start_date} → {end_date} {term_id} {account}")

    # 🔹 Fetch courses for the account+term
    courses = get_canvas_courses_by_term(term_id, account=account)

    # Build course_map
    course_map = {
        f"course_{c['id']}": {
            "course_id": c['id'],
            "sis_course_id": c.get('sis_course_id'),
            "course_name": c.get('name', 'Unnamed Course'),
            "enrollment_term_id": c.get('enrollment_term_id'),
            "enrollment_term_name": c.get("term", {}).get("name"),
            "sis_term_id": c.get("term", {}).get("sis_term_id")
        }
        for c in courses if 'id' in c
    }
    course_ids = list(course_map.keys())
    events = []

    # 🔹 Fetch events within the term’s date range
    for course_chunk in chunked_list(course_ids, 10):
        course_events = get_canvas_events(
            context_codes=course_chunk,
            start_date=start_date,
            end_date=end_date
        )
        for event in course_events:
            if event.get("end_at"):
                try:
                    # Convert from ISO string to datetime, add 9 minutes, then back to ISO
                    dt = datetime.fromisoformat(event["end_at"].replace("Z", "+00:00"))
                    event["adjusted_end_at"] = (dt + timedelta(minutes=9)).isoformat()
                    event["local_end_at"] = datetime.fromisoformat(event["adjusted_end_at"].replace('Z', '+00:00')
                    ).astimezone(PACIFIC_TZ).strftime('%m/%d/%Y %I:%M %p')
                except Exception:
                    event["adjusted_end_at"] = event["end_at"]
                    event["local_end_at"] = datetime.fromisoformat(
                    event['end_at'].replace('Z', '+00:00')
                    ).astimezone(PACIFIC_TZ).strftime('%m/%d/%Y %I:%M %p')

            ci = course_map.get(event.get('context_code'))
            if ci:
                event['course_name'] = ci['course_name']
                event['sis_course_id'] = ci["sis_course_id"]
                event['term_id'] = ci["enrollment_term_id"]
                event['session_title'] = (
                    f"{event['sis_course_id']} {event['title']} "
                    f"{datetime.fromisoformat(event['start_at'].replace('Z', '+00:00')).astimezone(PACIFIC_TZ).strftime('%#m/%#d/%Y')}"
                )
        events.extend(course_events)

    events.sort(
        key=lambda e: datetime.fromisoformat(e['start_at'].replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        if e.get('start_at')
        else datetime.max.replace(tzinfo=timezone.utc)
    )
    
    scheduled = ScheduledRecording.query.all()
    scheduled_map = {int(rec.canvas_event_id): {
        "recorder_id": rec.recorder_id,
        "session_id": rec.panopto_session_id,
        "folder_id": rec.folder_id,
        "broadcast": rec.broadcast
    } for rec in scheduled}

    # if not session.get("panopto_token"):
    #     return redirect(url_for("scheduler.panopto_login"))

    folders = get_panopto_folders()
    recorders = get_panopto_recorders()
    # print(f"Found {len(folders)} folders and {len(recorders)} recorders in Panopto.",folders)
    duration = time.perf_counter() - start_overall
    print(f"⏱ list_canvas_events (account {account}, term {term_id}) took {duration:.2f} seconds and returned {len(events)} events.")

    return render_template(
        "scheduler/canvas_events.html",
        events=events,
        scheduled_map=scheduled_map,
        folders=folders,
        recorders=recorders,
        account=account,
        term_id=term_id,
        term_name=selected_term.get("name")
    )

@bp.route('/recordings/toggle', methods=['POST'])
@panopto_required
@permission_required('panopto_scheduler+add, panopto_scheduler+edit')
def toggle_recording():
    data = request.form
    canvas_event_id = data['event_id']
    title = data['title']
    start_time = data['start_time']
    end_time = data['end_time']
    folder_id = data['folder_id']
    recorder_id = data['recorder_id']
    broadcast_str = data.get("broadcast", "false")
    broadcast = broadcast_str.lower() == "true"

    existing = ScheduledRecording.query.filter_by(canvas_event_id=canvas_event_id).first()

    if existing:
        if existing.panopto_session_id:
            delete_panopto_recording(existing.panopto_session_id)
        db.session.delete(existing)
        db.session.commit()
        # flash("Recording unscheduled", "info")
        return jsonify({"success": True, "message": "Recording schedule deleted."})
    else:
        result = schedule_panopto_recording(title, start_time, end_time, folder_id, recorder_id, broadcast)

        if "id" in result:
            print("Scheduled successfully:", result["id"])
            new_rec = ScheduledRecording(
                canvas_event_id=canvas_event_id,
                title=title,
                start_time=datetime.fromisoformat(start_time),
                end_time=datetime.fromisoformat(end_time),
                folder_id=folder_id,
                recorder_id=recorder_id,
                panopto_session_id=result["id"],
                broadcast=broadcast
            )
            db.session.add(new_rec)
            db.session.commit()
            return jsonify({"success": True, "message": "Recording scheduled."})
        elif "error" in result:
            # Failed to schedule, return error to JS
            print("Failed to schedule:", result["error"])
            return jsonify({"success": False, "message": result["error"]})

        else:
            # Catch-all in case schedule_panopto_recording returned None
            return jsonify({"success": False, "message": "Unknown error occurred."})

@panopto_required
def schedule_panopto_recording(name, start_time, end_time, folder_id, recorder_id, broadcast):
    try:
        session_oauth = get_panopto_session()
            
        url = f"https://{PANOPTO_API_BASE}/Panopto/api/v1/scheduledRecordings"

        payload = {
            "Name": name,
            "StartTime": start_time,
            "EndTime": end_time,
            "FolderId": folder_id,
            # "RecorderId": recorder_id,
            "Recorders": [
                {
                    "RemoteRecorderId": recorder_id,
                    "SuppressPrimary": False,
                    "SuppressSecondary": False
                }
            ],
            "IsBroadcast": broadcast
        }
        params = {"resolveConflicts": False}
        headers = {"Content-Type": "application/json"}

        resp = session_oauth.post(url, json=payload, params=params, headers=headers)
        print(resp)
        # If token expired, refresh once
        if resp.status_code == 401:  # Unauthorized
            session_oauth = get_panopto_session(refresh=True)
            resp = session_oauth.post(url, json=payload, params=params, headers=headers)

        return inspect_response(resp)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@panopto_required
def delete_panopto_recording(session_id):
    try:
        session_oauth = get_panopto_session()

        url = f"https://{PANOPTO_API_BASE}/Panopto/api/v1/scheduledRecordings/{session_id}"

        resp = session_oauth.delete(url)
        print(resp)

        if resp.status_code >= 500:
            print("🔥 Panopto 500 error (delete):", resp.text)
            return False

        if resp.status_code == 401:
            raise Exception("Panopto token expired or unauthorized")

        if resp.status_code not in (200, 204):
            print("⚠️ Unexpected delete response:", resp.status_code, resp.text)
            return False

        return True

    except Exception as e:
        import traceback
        print("🚨 delete_panopto_recording FAILED")
        traceback.print_exc()
        return False