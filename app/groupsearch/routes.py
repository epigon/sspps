from app.forms import GroupForm
from app.models import db, Listserv
from app.utils import permission_required
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, jsonify, Blueprint, send_file, abort, make_response, Response
from flask_login import login_required, current_user
from google.auth.transport.requests import Request
from google.oauth2 import service_account
import os
import requests

groupsearch_bp = Blueprint('groupsearch', __name__, url_prefix='/groupsearch')

SERVICE_ACCOUNT_FILE =  os.path.join('app', 'nodal-album-464015-d4-e7b2f79666a6.json')
DELEGATED_EMAIL =  'groups-read-only@nodal-album-464015-d4.iam.gserviceaccount.com'  # Admin email
SCOPES = ['https://www.googleapis.com/auth/cloud-identity.groups.readonly']
# GROUP_EMAIL = 'sspps-staff-l@ucsd.edu'

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

# Routes to Webpages
@groupsearch_bp.before_request
@login_required
def before_request():
    pass

@groupsearch_bp.route('/list', methods=['GET', 'POST'])
@permission_required('listserv+view, listserv+add, listserv+edit, listserv+delete')
def list_groups():
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
    return render_template('groupsearch/list_groups.html', form=form, groups=groups)

@groupsearch_bp.route('/delete/<int:group_id>', methods=['POST'])
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

@groupsearch_bp.route('/members/<string:group_email>')
@permission_required('listserv+view')
def list_members(group_email):
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

    while True:
        params = {'pageToken': page_token} if page_token else {}
        resp = requests.get(
            f'https://cloudidentity.googleapis.com/v1/{group_name}/memberships',
            headers=headers,
            params=params
        )
        resp.raise_for_status()
        data = resp.json()
        for m in data.get('memberships', []):
            members.append({
                'email': m['preferredMemberKey']['id'],
                'role': m['roles'][0]['name'] if m['roles'] else 'UNKNOWN'
            })
        page_token = data.get('nextPageToken')
        if not page_token:
            break

    return render_template('groupsearch/list_members.html', group=group_email, members=members)
