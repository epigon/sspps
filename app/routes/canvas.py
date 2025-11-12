from app.cred import CANVAS_API_BASE, CANVAS_API_TOKEN
from app.utils import permission_required
from datetime import datetime, timezone, timedelta
from flask import render_template, request, Blueprint, jsonify
from flask_login import login_required
from os.path import dirname, join, abspath
import os
import pytz
import requests
import sys

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
# @bp.before_request
# @login_required
# def before_request():
#     pass

def get_canvas_courses(account="SSPPS", blueprint=False, state=None, term_id=None):
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
    
    if term_id is not None:
      params['enrollment_term_id'] = term_id

    if state is not None:
      params['state[]'] = state
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

    all_courses = sorted(all_courses, key=lambda d: d['name'])

    return all_courses

def get_canvas_users(account="SSPPS", search_term=None):
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
    params = {'per_page': 100}
    
    if search_term is not None:
      params['search_term'] = search_term

    url = f"{CANVAS_API_BASE}/accounts/{accountID}/users"
    all_users = []

    while url:
        # print(url)
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        all_users.extend(response.json())

        # Parse the Link header for next page
        links = response.headers.get("Link", "")
        next_url = None
        for link in links.split(","):
            if 'rel="next"' in link:
                next_url = link[link.find("<") + 1:link.find(">")]
                break
        url = next_url
        params = None  # After the first request, pagination is handled by the link

    all_users = sorted(all_users, key=lambda d: d['name'])

    return all_users

# @bp.route("/api/courses")
def get_courses_api():
    term_id = request.args.get('term_id')
    # print(term_id)
    all_courses = get_canvas_courses()
    filtered_courses = []

    for course in all_courses:
        if str(course.get('enrollment_term_id')) == str(term_id):
            filtered_courses.append({
                'id': course['id'],
                'name': course['name']
            })
    return jsonify({"courses": filtered_courses})

from collections import defaultdict

def get_terms_with_courses(account="SSPPS"):
    """
    Builds a list of terms with their associated Canvas courses for dropdown filtering.
    This assumes get_canvas_courses() returns all courses in the account.
    
    Returns:
        List of dicts with keys: id, name, courses (list of dicts)
    """
    all_courses = get_canvas_courses(account=account)

    # Group courses by enrollment_term_id
    terms_dict = defaultdict(list)
    for course in all_courses:
        term_id = course.get("enrollment_term_id")
        if not term_id:
            continue
        terms_dict[term_id].append({
            "id": course.get("id"),
            "name": course.get("name"),
            "course_code": course.get("course_code") or ""
        })

    # Get term names — fallback to raw ID if name unavailable
    # You may want to replace this with a lookup from a Term model/table
    term_names = {
        str(t.get("id")): t.get("name", f"Term {t.get('id')}")
        for t in get_enrollment_terms()
    }

    # Assemble final list
    terms_with_courses = []
    for term_id, courses in terms_dict.items():
        terms_with_courses.append({
            "id": term_id,
            "name": term_names.get(str(term_id), f"Term {term_id}"),
            "courses": sorted(courses, key=lambda c: c["name"])
        })

    # Sort terms by name or ID
    terms_with_courses.sort(key=lambda t: t["name"])

    return terms_with_courses

@bp.route("/courses")
@permission_required('calendar+add, calendar+edit')
def canvas_courses_by_term():
    term_id = request.args.get("term_id", type=int)
    account = request.args.get("account", default="SSPPS", type=str)

    if term_id:
        courses = get_canvas_courses_by_term(term_id=term_id, account=account)
    else:
        courses = get_canvas_courses(account=account)

    return jsonify([
        {"id": c.get("id"), "name": c.get("name")}
        for c in courses
    ])

def get_canvas_courses_by_term(term_id, account="SSPPS"):
    """
    Fetch Canvas courses for a given term ID.

    Args:
        term_id (str or int): Canvas enrollment term ID to filter courses by.
        account (str): Canvas account short code (default "SSPPS").

    Returns:
        list: Filtered list of Canvas course dictionaries for the selected term.
    """
    all_courses = get_canvas_courses(account=account, term_id=term_id)
    return all_courses

def get_canvas_events(context_codes=[], start_date=datetime.now(), end_date=None, all_events=True):
    headers = {'Authorization': f'Bearer {CANVAS_API_TOKEN}'}
    page = 1
    page_size = 100
    params = {'per_page': page_size, "state[]":"available"}    
    print("start_date",start_date)
    print("end_date",end_date)
    
    # ✅ Correctly add multiple context_codes
    if context_codes:
        params['context_codes[]'] = context_codes 
        
    if start_date or end_date:
        if start_date and isinstance(start_date, datetime):
            start_date = start_date.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            start_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        params['start_date'] = start_date
        if end_date and isinstance(end_date, datetime):
            end_date = end_date.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            # Default end_date to one year after start_date if not provided
            dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_date = (dt + timedelta(days=365)).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        params['end_date'] = end_date
    else:
        params['all_events'] = 'true'

    print("context_codes",context_codes)
    print("params",params)
    
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
            if "all_day_date" in event and event["all_day_date"]:
                # Parse date (assume YYYY-MM-DD from Canvas or your source)
                all_day = datetime.strptime(event["all_day_date"], "%Y-%m-%d").date()
                event['start_at'] = all_day.strftime("%Y%m%d")  # 20251017
                event['end_at'] = (all_day + timedelta(days=1)).strftime("%Y%m%d")  # 20251018
                event['is_all_day'] = True
            else:
                if 'start_at' in event:
                    event['local_start_at'] = datetime.fromisoformat(
                        event['start_at'].replace('Z', '+00:00')
                    ).astimezone(PACIFIC_TZ).strftime('%m/%d/%Y %I:%M %p')
                if 'end_at' in event:
                    event['local_end_at'] = datetime.fromisoformat(
                        event['end_at'].replace('Z', '+00:00')
                    ).astimezone(PACIFIC_TZ).strftime('%m/%d/%Y %I:%M %p')
            events.append(event)
            # print(event['local_start_at'], event['local_end_at'], event.get('title','No Title'))
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
def get_enrollment_terms():
    """
    Fetches all enrollment terms for a given Canvas account using pagination.

    Returns:
        list: List of term dictionaries.
    """
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

@bp.route("/get_canvas_sections_api/<int:course_id>")
@permission_required('canvas_enrollments+view,canvas_enrollments+add')
def get_canvas_sections_api(course_id):
    """
    Returns all sections for a given Canvas course.
    """
    headers = {'Authorization': f'Bearer {CANVAS_API_TOKEN}'}
    url = f"{CANVAS_API_BASE}/courses/{course_id}/sections?per_page=100"

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return jsonify(response.json())

def enroll_user(course_id, user_id, enrollment_type="StudentEnrollment", enrollment_state="active", section_id="", notify=False):
    """
    Enrolls a user in a Canvas course.

    Args:
        course_id (int): Canvas course ID.
        user_id (int or str): Canvas user ID or SIS ID (e.g., 'sis_user_id:1234').
        enrollment_type (str): Type of enrollment (e.g., StudentEnrollment, TeacherEnrollment, TaEnrollment, ObserverEnrollment, DesignerEnrollment.).
        enrollment_state (str): State of the enrollment (e.g., active, invited, inactive).
        section_id (int): (optional)
        notify (bool): Whether to notify the user by email (default is False).

    Returns:
        dict: Enrollment response from Canvas.
    """
    headers = {'Authorization': f'Bearer {CANVAS_API_TOKEN}'}
    url = f"{CANVAS_API_BASE}/courses/{course_id}/enrollments"

    payload = {
        'enrollment[user_id]': user_id,
        'enrollment[type]': enrollment_type,
        'enrollment[enrollment_state]': enrollment_state,
        'enrollment[notify]': 'true' if notify else 'false'
        # 'enrollment[notify]': 'false'
    }

    if section_id:
        payload['enrollment[course_section_id]'] = section_id

    # print("payload",payload)
    # return payload.json()
    response = requests.post(url, headers=headers, data=payload)
    response.raise_for_status()
    return response.json()

def enroll_multiple_users(course_id, users, enrollment_type="StudentEnrollment", enrollment_state="active", section_id="", notify=False):
    """
    Enroll multiple users into a Canvas course.

    Args:
        course_id (int): Canvas course ID.
        users (list): List of user IDs or SIS IDs.
        enrollment_type (str): Type of enrollment (default: "StudentEnrollment").
        enrollment_state (str): Enrollment state (default: "active").
        section_id (int): (optional)
        notify (bool): Whether to notify the user by email (default is False).

    Returns:
        list: List of enrollment results or errors.
    """
    results = []
    for user_id in users:
        try:
            result = enroll_user(
                course_id=course_id,
                user_id=user_id,
                enrollment_type=enrollment_type,
                enrollment_state=enrollment_state,
                section_id=section_id,
                notify=notify
            )
            results.append({"user_id": user_id, "status": "success", "result": result})
        except requests.exceptions.HTTPError as e:
            results.append({
                "user_id": user_id,
                "status": "error",
                "message": str(e),
                "details": e.response.text
            })
    return results

@bp.route("/enroll_user_api", methods=["POST"])
@permission_required('canvas_enrollments+add')
def enroll_user_api():
    """
    Enroll a user into a Canvas course.
    Expects JSON payload with:
        - course_id (int)
        - user_id (int or str)
        - enrollment_type (optional, default "StudentEnrollment")
        - enrollment_state (optional, default "active")
        - section_id (int|optional)
        - notify (optional, default true)

    Returns:
        JSON response with enrollment result or error.
    """
    data = request.get_json()

    course_id = data.get("course_id")
    user_id = data.get("user_id")
    enrollment_type = data.get("enrollment_type", "StudentEnrollment")
    enrollment_state = data.get("enrollment_state", "active")
    section_id = data.get("section_id", "")
    notify = data.get("notify", True)

    if not course_id or not user_id:
        return jsonify({"error": "Missing course_id or user_id"}), 400

    try:
        result = enroll_user(
            course_id=course_id,
            user_id=user_id,
            enrollment_type=enrollment_type,
            enrollment_state=enrollment_state,
            section_id=section_id,
            notify=notify
        )
        return jsonify(result)
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": str(e), "details": e.response.text}), e.response.status_code

@bp.route("/enroll_users_bulk_api", methods=["POST"])
@permission_required('canvas_enrollments+add')
def enroll_users_bulk_api():
    """
    Bulk enroll users into a Canvas course.
    Expects JSON with:
        - course_id (int)
        - users (list of user IDs or SIS IDs)
        - enrollment_type (optional)
        - enrollment_state (optional)
        - section_id (int|optional)
        - notify (optional)

    Returns:
        JSON list of enrollment results per user.
    """
    data = request.get_json()
    course_id = data.get("course_id")
    users = data.get("users")

    if not course_id or not users:
        return jsonify({"error": "Missing course_id or users[]"}), 400

    enrollment_type = data.get("enrollment_type", "StudentEnrollment")
    enrollment_state = data.get("enrollment_state", "active")
    section_id = data.get("section_id", "")
    notify = data.get("notify", False)

    results = enroll_multiple_users(
        course_id=course_id,
        users=users,
        enrollment_type=enrollment_type,
        enrollment_state=enrollment_state,
        section_id=section_id,
        notify=notify
    )

    return jsonify(results)
