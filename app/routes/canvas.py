from app.cred import CANVAS_API_BASE, CANVAS_API_TOKEN, PANOPTO_API_BASE, PANOPTO_CLIENT_ID, PANOPTO_CLIENT_SECRET
from app.models import db, ScheduledRecording, CalendarGroup, CalendarGroupSelection
from app.utils import permission_required
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from flask import render_template, request, Blueprint, jsonify
from flask_login import login_required
from icalendar import Calendar, Event, vText
from os.path import dirname, join, abspath
from .panopto_oauth2 import PanoptoOAuth2
import argparse
import os
import pytz
import re
import requests
import sys
import urllib3

sys.path.insert(0, abspath(join(dirname(__file__), '..', 'common')))

bp = Blueprint('canvas', __name__, url_prefix='/canvas')

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

def get_canvas_courses(account="SSPPS", blueprint=False):
    """
    Fetches all Canvas courses for the authenticated user using pagination.

    Args:
        base_url (str): Base URL of the Canvas instance (e.g., 'https://canvas.instructure.com')
        access_token (str): Bearer token for authentication.
        per_page (int): Number of courses per page.

    Returns:
        list: List of all course dictionaries.
    """
    if account == "HS":
        accountID = HSAccountID
    elif account == "SSPPS":
        accountID = SSPPSAccountID
    elif account == "SOM":
        accountID = SOMAccountID
    else:
        accountID = mainAccountID
    
    headers = {'Authorization': f'Bearer {CANVAS_API_TOKEN}'}
    params = {'per_page': 100, 
              "blueprint": blueprint, 
              "include[]": ["term","account_name"]}
    url = f"{CANVAS_API_BASE}/accounts/{accountID}/courses"
    all_courses = []

    while url:
        # print(url)
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        all_courses.extend(response.json())

        # Parse the Link header for next page
        links = response.headers.get("Link", "")
        next_url = None
        for link in links.split(","):
            if 'rel="next"' in link:
                next_url = link[link.find("<") + 1:link.find(">")]
                break
        url = next_url
        params = None  # After the first request, pagination is handled by the link

    return all_courses

@bp.route("/api/courses")
def get_courses_api():
    term_id = request.args.get('term_id')
    print(term_id)
    all_courses = get_canvas_courses()
    filtered_courses = []

    for course in all_courses:
        if str(course.get('enrollment_term_id')) == str(term_id):
            filtered_courses.append({
                'id': course['id'],
                'name': course['name']
            })
    return jsonify({"courses": filtered_courses})

def get_canvas_courses_by_term(term_id, account="SSPPS"):
    """
    Fetch Canvas courses for a given term ID.

    Args:
        term_id (str or int): Canvas enrollment term ID to filter courses by.
        account (str): Canvas account short code (default "SSPPS").

    Returns:
        list: Filtered list of Canvas course dictionaries for the selected term.
    """
    all_courses = get_canvas_courses(account=account)
    filtered = [c for c in all_courses if str(c.get("enrollment_term_id")) == str(term_id)]
    return filtered

def get_canvas_events(context_codes=[], start_date=datetime.now(), end_date=None, all_events=True):
    headers = {'Authorization': f'Bearer {CANVAS_API_TOKEN}'}
    page = 1
    page_size = 100
    params = {'per_page': page_size, "state[]":"available"}    

    if context_codes:
        params.setdefault('context_codes[]', []).append(context_codes)
    
    # print("params",params)
    if start_date or end_date:
        if start_date:
            if isinstance(start_date, datetime):
                start_date = start_date.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            params['start_date'] = start_date
        # Default end_date to one year after start_date if not provided
            if not end_date:
                dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                end_date = (dt + timedelta(days=365)).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        if end_date:
            if isinstance(end_date, datetime):
                end_date = end_date.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            params['end_date'] = end_date
    else:
        params['all_events'] = 'true'

    url = f"{CANVAS_API_BASE}/calendar_events"
    events = []
    repeat = True

    while repeat:
        # print("page",page)
        params['page'] = page  
        response = requests.get(url, headers=headers, params=params)
        # print(response)
        if not response.ok:
            # print(f"Canvas API error {response.status_code}: {response.text}")
            break

        data = response.json()
        for event in data:
            if 'start_at' in event:
                event['local_start_at'] = datetime.fromisoformat(event['start_at'].replace('Z', '+00:00')).astimezone(PACIFIC_TZ).strftime('%m/%d/%Y %I:%M %p')
            if 'end_at' in event:
                event['local_end_at'] = datetime.fromisoformat(event['end_at'].replace('Z', '+00:00')).astimezone(PACIFIC_TZ).strftime('%m/%d/%Y %I:%M %p')
            events.append(event)
        # print("len",len(data))

        if len(data) < page_size:
            repeat = False

        page += 1

    return events

def chunked_list(lst, n):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# @bp.route('/terms')
def get_enrollment_terms(account=""):
    """
    Fetches all enrollment terms for a given Canvas account using pagination.

    Args:
        account (str): Short code for account ("SSPPS", "HS", "SOM", etc.)

    Returns:
        list: List of term dictionaries.
    """
    if account == "HS":
        accountID = HSAccountID
    elif account == "SSPPS":
        accountID = SSPPSAccountID
    elif account == "SOM":
        accountID = SOMAccountID
    else:
        accountID = mainAccountID

    headers = {'Authorization': f'Bearer {CANVAS_API_TOKEN}'}
    params = {'per_page': 100}
    url = f"{CANVAS_API_BASE}/accounts/{accountID}/terms"
    all_terms = []

    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        all_terms.extend(data.get("enrollment_terms", []))

        # Parse the Link header for pagination
        links = response.headers.get("Link", "")
        next_url = None
        for link in links.split(","):
            if 'rel="next"' in link:
                next_url = link[link.find("<") + 1:link.find(">")]
                break
        url = next_url
        params = None  # Don't re-apply params after the first request

    return all_terms

def get_enrollments(course_id, enrollment_type="StudentEnrollment"):
    """
    Fetches all enrollments for a given Canvas course using pagination.

    Args:
        course_id (int): Canvas course ID.
        enrollment_type (str): Type of enrollment to fetch (default is "StudentEnrollment").

    Returns:
        list: List of enrollment dictionaries.
    """
    headers = {'Authorization': f'Bearer {CANVAS_API_TOKEN}'}
    params = {
        'per_page': 100,
        'type[]': enrollment_type,
        'include[]': 'user'
    }
    url = f"{CANVAS_API_BASE}/courses/{course_id}/enrollments"
    all_enrollments = []

    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        all_enrollments.extend(response.json())

        # Pagination via Link header
        links = response.headers.get("Link", "")
        next_url = None
        for link in links.split(","):
            if 'rel="next"' in link:
                next_url = link[link.find("<") + 1:link.find(">")]
                break
        url = next_url
        params = None  # Handled via next URL

    return all_enrollments
