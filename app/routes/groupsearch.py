from app.forms import GroupForm
from app.models import db, Listserv, Student, Employee
from app.utils import permission_required
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, jsonify, Blueprint, send_file, abort, make_response, Response
from flask_login import login_required, current_user
from google.auth.transport.requests import Request
from google.oauth2 import service_account
import os
import pytz
import requests

bp = Blueprint('groupsearch', __name__, url_prefix='/groupsearch')

#Google service account credentials
SERVICE_ACCOUNT_FILE =  os.path.join('app', 'nodal-album-464015-d4-e7b2f79666a6.json')
DELEGATED_EMAIL =  'groups-read-only@nodal-album-464015-d4.iam.gserviceaccount.com'  # Admin email
SCOPES = ['https://www.googleapis.com/auth/cloud-identity.groups.readonly']

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

def get_request_headers():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    ).with_subject(DELEGATED_EMAIL)

    # Refresh to get token
    credentials.refresh(Request())
    access_token = credentials.token
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    return headers

@bp.route('/list', methods=['GET', 'POST'])
@permission_required('listserv+view, listserv+add, listserv+edit, listserv+delete')
def list_groups():

    custom_breadcrumbs = [
        {'name': 'Google Groups', 'url': '/groupsearch/list'}
    ]
    form = GroupForm()
    if form.validate_on_submit():
        group_name = form.group_name.data.strip()
        existing = Listserv.query.filter_by(group_name=group_name).first()
        if existing and not existing.deleted:
            flash('Group already exists!', 'warning')
        elif existing and existing.deleted:
            # Reactivate soft-deleted group
            existing.deleted = False
            existing.delete_date = None
            existing.create_date = datetime.now()
            existing.create_by = int(current_user.id)
            db.session.commit()
            flash('Group restored!', 'success')
        else:
            new_group = Listserv(group_name=group_name)
            new_group.create_by = int(current_user.id)
            db.session.add(new_group)
            db.session.commit()
            flash('Group added successfully!', 'success')
        return redirect(url_for('groupsearch.list_groups'))
    
    groups = Listserv.query.filter_by(deleted=False).order_by(Listserv.group_name.asc()).all()
    return render_template('groupsearch/list_groups.html', form=form, groups=groups, breadcrumbs=custom_breadcrumbs)

@bp.route('/delete/<int:group_id>', methods=['POST'])
@permission_required('listserv+delete')
def delete_group(group_id):
    group = Listserv.query.get_or_404(group_id)
    if not group.deleted:
        group.deleted = True
        group.delete_date = datetime.now()
        group.delete_by=int(current_user.id)
        db.session.commit()
        flash('Group soft-deleted.', 'info')
    else:
        flash('Group already deleted.', 'warning')
    return redirect(url_for('groupsearch.list_groups'))

@bp.route('/members/<string:group_email>')
@permission_required('listserv+view')
def list_members(group_email):
    
    headers = get_request_headers()
    
    custom_breadcrumbs = [
        {'name': 'Google Groups', 'url': '/groupsearch/list'},
        {'name': f'{group_email} Members', 'url': f'/groupsearch/members/{group_email}'}
    ]
    # Make the HTTP request to Cloud Identity API
    # Lookup group
    lookup_resp = requests.get(
        'https://cloudidentity.googleapis.com/v1/groups:lookup',
        headers=headers,
        params={'groupKey.id': group_email}
    )
    lookup_resp.raise_for_status()
    group_name = lookup_resp.json()['name']  # e.g. "groups/ABCD123456"

    # Get members
    members = []
    page_token = None

    # Filter students by class_of, course_id, etc.
    students = Student.query.filter_by(deleted = False).order_by(Student.last_name, Student.first_name).all()
    employees = Employee.query.order_by(Employee.employee_last_name, Employee.employee_first_name).all()

    # Build username map
    usernames = {}

    # Add students
    for s in students:
        # You can adjust the key and value as needed
        usernames[s.username] = f"{s.first_name} {s.last_name}"

    # Add employees
    for e in employees:
        usernames[e.username] = f"{e.employee_first_name} {e.employee_last_name}"
    
    while True:
        params = {'pageToken': page_token, 'view': 'FULL'} if page_token else {'view': 'FULL'}
        resp = requests.get(
            f'https://cloudidentity.googleapis.com/v1/{group_name}/memberships',
            headers=headers,
            params=params
        )
        resp.raise_for_status()
        data = resp.json()
        for m in data.get('memberships', []):
            print(m)
            # Original UTC timestamp
            utc_time_str = m.get('createTime', '')

            # Parse the UTC datetime
            utc_dt = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
            utc_dt = utc_dt.replace(tzinfo=pytz.utc)

            # Convert to Pacific Time
            pacific = pytz.timezone("US/Pacific")
            pacific_dt = utc_dt.astimezone(pacific)

            members.append({
                'email': m['preferredMemberKey']['id'],
                'role': m['roles'][0]['name'] if m['roles'] else 'UNKNOWN',
                'added': pacific_dt.strftime("%Y-%m-%d %I:%M:%S %p"),
                'name': usernames.get(m['preferredMemberKey']['id'].split('@')[0], 'Unknown User')
            })

        page_token = data.get('nextPageToken')
        if not page_token:
            break

    return render_template('groupsearch/list_members.html', group=group_email, members=members, breadcrumbs=custom_breadcrumbs)
