from app.cred import PANOPTO_API_BASE, PANOPTO_CLIENT_ID, PANOPTO_CLIENT_SECRET
from app.models import db, ScheduledRecording
from app.utils import permission_required
from .canvas import get_canvas_courses, get_canvas_events, chunked_list
from datetime import datetime
from flask import Flask, render_template, request, Blueprint, jsonify, session, has_request_context
from flask_login import login_required
from os.path import dirname, join, abspath
from .panopto_oauth2 import PanoptoOAuth2
from requests_oauthlib import OAuth2Session
from urllib.parse import urlparse, urlunparse
import argparse
import os
import pytz
import requests
import sys
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

REDIRECT_PORT = 9127
                 
# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

# --- Panopto login helper ---
@bp.route("/panopto_login")
def panopto_login():
    args = argparse.Namespace(
        server=PANOPTO_API_BASE,
        client_id=PANOPTO_CLIENT_ID,
        client_secret=PANOPTO_CLIENT_SECRET,
        skip_verify=True
    )

    if args.skip_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    requests_session = requests.Session()
    requests_session.verify = not args.skip_verify

    # Build OAuth2 instance
    oauth2 = PanoptoOAuth2(args.server, args.client_id, args.client_secret, not args.skip_verify)

    # Only save config in session if we're inside a request
    if has_request_context():
        session["panopto"] = {
            "server": args.server,
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "ssl_verify": not args.skip_verify,
            "redirect_url": oauth2.redirect_url,
            "token_endpoint": oauth2.access_token_endpoint,
        }
        # return session["panopto"] 

    authorization(requests_session, oauth2)
    return requests_session, oauth2, args

@bp.route("/oauth2/callback")
def oauth2_callback():
    try:
        full_redirect_url = request.url
        panopto_cfg = session.get("panopto")
        if not panopto_cfg:
            return "No Panopto OAuth session found. Please try logging in again.", 400

        oauth2 = PanoptoOAuth2(
            panopto_cfg["server"],
            panopto_cfg["client_id"],
            panopto_cfg["client_secret"],
            panopto_cfg["ssl_verify"],
        )

        session_oauth = OAuth2Session(
            client_id=panopto_cfg["client_id"],
            redirect_uri=panopto_cfg["redirect_url"],
            scope=["openid", "api", "offline_access"]
        )

        token = session_oauth.fetch_token(
            panopto_cfg["token_endpoint"],
            client_secret=panopto_cfg["client_secret"],
            authorization_response=full_redirect_url,
            verify=panopto_cfg["ssl_verify"]
        )

        oauth2._PanoptoOAuth2__save_token_to_cache(token)
        return "Authorization complete. You may close this window."

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"OAuth2 callback failed: {e}", 500

# def panopto_login():
    
#     args = argparse.Namespace(
#         server=PANOPTO_API_BASE,
#         client_id=PANOPTO_CLIENT_ID,
#         client_secret=PANOPTO_CLIENT_SECRET,
#         skip_verify=True
#     )

#     if args.skip_verify:
#         # This line is needed to suppress annoying warning message.
#         urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

#     # Use requests module's Session object in this example.
#     # ref. https://2.python-requests.org/en/master/user/advanced/#session-objects
#     requests_session = requests.Session()
#     requests_session.verify = not args.skip_verify

#     # Load OAuth2 logic
#     hostname = urlparse(request.host_url).hostname
    
#     if hostname in ('localhost', '127.0.0.1'):
#         redirect_url = f"http://{hostname}:{REDIRECT_PORT}/redirect"
#         # Make oauthlib library accept non-HTTPS redirection.
#         # This should not be applied if the redirect is hosted by actual server (not localhost).
#         # Allow non-HTTPS redirect (safe for localhost dev only)
#         os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
#     else:
#         redirect_url = f"https://{hostname}/scheduler/oauth2/callback"
#         # Ensure oauthlib library requires HTTPS redirection (default behavior).
#         if "OAUTHLIB_INSECURE_TRANSPORT" in os.environ:
#             del os.environ["OAUTHLIB_INSECURE_TRANSPORT"]

#     try:
#         oauth2 = PanoptoOAuth2(args.server, args.client_id, args.client_secret, redirect_url, not args.skip_verify)
#     except Exception as e:   
#         return f"Error initializing Panopto OAuth2: {str(e)}", 500
    
#     # Initial authorization
#     test = authorization(requests_session, oauth2)
#     return test
#     return requests_session, oauth2, args

def authorization(requests_session, oauth2):
    # Go through authorization
    access_token = oauth2.get_access_token_authorization_code_grant()
    
    # Set the token as the header of requests
    requests_session.headers.update({'Authorization': 'Bearer ' + access_token})

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

    # Throw unhandled cases.
    response.raise_for_status()

def get_panopto_folders():

    requests_session, oauth2, args = panopto_login()
    folders = []
    # Call Panopto API (getting sub-folders from top level folder) repeatedly
    page_number = 0
    page_size = 50  # You can adjust this up to Panopto's max limit

    while True:
        # print(f'Calling GET /api/v1/folders/{PANOPTO_PARENT_FOLDER}/children?pageNumber={page_number}')
        url = f'https://{args.server}/Panopto/api/v1/folders/{PANOPTO_PARENT_FOLDER}/children'
        params = {
            'pageNumber': page_number,
            'maxNumberResults': page_size
        }
        resp = requests_session.get(url=url, params=params)

        if inspect_response_is_unauthorized(resp):
            authorization(requests_session, oauth2)
            resp = requests_session.get(url=url, params=params)

        data = resp.json()
        results = data.get("Results", [])
        for folder in results:
            # if any("spps" in str(value).lower() for value in folder.values()):
            folders.append({"id": folder['Id'], "name": folder['Name']})

        if len(results) < page_size:
            break  # We've reached the last page

        page_number += 1
    # print(folders)
    return folders

def get_panopto_recorders():
    requests_session, oauth2, args = panopto_login()

    recorders = []
    page_number = 0
    page_size = 50  # You can adjust this up to Panopto's max limit

    while True:
        # print('Calling GET /api/v1/remoteRecorders endpoint')
        url = 'https://{0}/Panopto/api/remoteRecorders'.format(args.server)
        params = {
            'pageNumber': page_number,
            'maxNumberResults': page_size
        }
        resp = requests_session.get(url=url, params=params)

        if inspect_response_is_unauthorized(resp):
            authorization(requests_session, oauth2)
            resp = requests_session.get(url=url, params=params)

        data = resp.json()
        # results = data.get("Results", [])
        for recorder in data:
            recorders.append({"id": recorder['Id'], "name": recorder['Name']})

        if len(data) < page_size:
            break  # We've reached the last page

        page_number += 1
    # print(folders)
    return recorders

@bp.route('/events')
@permission_required('panopto_scheduler+add, panopto_scheduler+edit')
def list_canvas_events():
    courses = get_canvas_courses()
    
    # Build a map from course ID to course info
    course_map = {
        f"course_{course['id']}": {
            "course_id": course['id'],
            "sis_course_id": course['sis_course_id'],
            "course_name": course.get('name', 'Unnamed Course'),
            "enrollment_term_id": course['enrollment_term_id'],
            "enrollment_term_name": course['term']['name'],
            "sis_term_id": course['term']['sis_term_id']
        }
        for course in courses if 'id' in course and course['term']['sis_term_id'] != "term_default"
    }
    course_ids = list(course_map.keys())

    events = []

    for course_chunk in chunked_list(course_ids, 10):
        course_events = get_canvas_events(course_chunk)
        for event in course_events:
            # Assume event has a 'context_code' like 'course_12345'
            course_info = course_map.get(event.get('context_code'))
            if course_info:
                # event['course_id'] = course_info['course_id']
                event['course_name'] = course_info['course_name']
                event['sis_course_id'] = course_info["sis_course_id"]
                event['term_id'] = course_info["enrollment_term_id"]
                event['session_title'] = event['sis_course_id']+" "+event['title']+" "+ datetime.fromisoformat(event['start_at'].replace('Z', '+00:00')).astimezone(PACIFIC_TZ).strftime('%#m/%#d/%Y')
            #     
        events.extend(course_events)

    # Sort events by 'start_at' (convert to datetime for robust sorting)
    events.sort(key=lambda e: datetime.fromisoformat(e['start_at'].replace('Z', '+00:00')) if e.get('start_at') else datetime.max)
  
    scheduled = ScheduledRecording.query.all()
    scheduled_map = { int(rec.canvas_event_id) : 
                        {"recorder_id": rec.recorder_id, 
                        "session_id": rec.panopto_session_id,
                        "folder_id": rec.folder_id,
                        "broadcast": rec.broadcast } for rec in scheduled }
    
    folders = get_panopto_folders()
    recorders = get_panopto_recorders()
    
    return render_template("scheduler/canvas_events.html", events=events, scheduled_map=scheduled_map, folders=folders, recorders=recorders)

@bp.route('/recordings/toggle', methods=['POST'])
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
        return jsonify({"success": True, "message": "Recording unscheduled."})
    else:
        session_id = schedule_panopto_recording(title, start_time, end_time, folder_id, recorder_id, broadcast)
        if session_id:
            new_rec = ScheduledRecording(
                canvas_event_id=canvas_event_id,
                title=title,
                start_time=datetime.fromisoformat(start_time),
                end_time=datetime.fromisoformat(end_time),
                folder_id=folder_id,
                recorder_id=recorder_id,
                panopto_session_id=session_id,
                broadcast=broadcast
            )
            db.session.add(new_rec)
            db.session.commit()
            return jsonify({"success": True, "message": "Recording scheduled."})
            # flash("Recording scheduled", "success")
        else:
            return jsonify({"success": False, "message": "Failed to schedule."})
            # flash("Failed to schedule", "danger")

    # return redirect(url_for('scheduler.list_canvas_events'))

def schedule_panopto_recording(name, start_time, end_time, folder_id, recorder_id, broadcast):
    requests_session, oauth2, args = panopto_login()
    
    url = 'https://{0}/Panopto/api/v1/scheduledRecordings'.format(args.server)
    session_data = {
        "Name": name,
        "StartTime": start_time,
        "EndTime": end_time,
        "FolderId": folder_id,
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
    headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
    resp = requests_session.post(url=url, json=session_data, params=params, headers=headers)

    if inspect_response_is_unauthorized(resp):
        authorization(requests_session, oauth2)
        resp = requests_session.post(url=url, params=session_data)

    if resp.ok:
        return resp.json()['Id']

    return None

def delete_panopto_recording(session_id):
    requests_session, oauth2, args = panopto_login()
    
    url = 'https://{0}/Panopto/api/v1/scheduledRecordings/{1}'.format(args.server,session_id)
    resp = requests_session.delete(url=url)

    if inspect_response_is_unauthorized(resp):
        authorization(requests_session, oauth2)
        resp = requests_session.delete(url=url)

    return resp.ok