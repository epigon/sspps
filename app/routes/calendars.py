from app.cred import CANVAS_API_BASE, CANVAS_API_TOKEN, PANOPTO_API_BASE, PANOPTO_CLIENT_ID, PANOPTO_CLIENT_SECRET
from app.forms import CalendarGroupForm
from app.models import db, CalendarGroup, CalendarGroupSelection
from app.utils import permission_required
from .canvas import get_canvas_courses, get_canvas_events
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from flask import render_template, request, Blueprint, jsonify, redirect, url_for, flash
from flask_login import login_required
from icalendar import Calendar, Event, vText
from os.path import dirname, join, abspath
import os
import pytz
import re
import sys

sys.path.insert(0, abspath(join(dirname(__file__), '..', 'common')))

bp = Blueprint('calendars', __name__, url_prefix='/calendars')

PACIFIC_TZ = pytz.timezone("America/Los_Angeles")
PANOPTO_PARENT_FOLDER = '66a0fa02-94a9-4fb9-ae75-aa71011bd7fc'

CALENDAR_FOLDER = os.path.join("app","static","calendars")
os.makedirs(CALENDAR_FOLDER, exist_ok=True)

mainAccountID = 1	
HSAccountID = 9	
SOMAccountID = 445	
SSPPSAccountID = 50 

@bp.before_request
def before_request():
    excluded_endpoints = ['calendars.generate_scheduled_ics']  # full endpoint name: blueprint_name.view_function_name
    if request.endpoint in excluded_endpoints:
        return  # Skip login_required check
    return login_required(lambda: None)()  # Call login_required manually

@bp.route('/calendar_groups/new', methods=['GET', 'POST'])
@bp.route('/calendar_groups/<int:group_id>', methods=['GET', 'POST'])
def edit_calendar_groups(group_id=None):
    form = CalendarGroupForm()
    groups = CalendarGroup.query.all()

    if group_id:
        group = CalendarGroup.query.get_or_404(group_id)
        if request.method == 'GET':
            form = CalendarGroupForm(obj=group)
        if form.validate_on_submit():
            group.name = form.name.data
            group.ics_filename = form.ics_filename.data
            db.session.commit()
            flash('Calendar group updated.', 'success')
            return redirect(url_for('calendars.edit_calendar_groups'))
        title = "Edit Calendar Group"
    else:
        if form.validate_on_submit():
            new_group = CalendarGroup(
                name=form.name.data,
                ics_filename=form.ics_filename.data
            )
            db.session.add(new_group)
            db.session.commit()
            flash('Calendar group added.', 'success')
            return redirect(url_for('calendars.edit_calendar_groups'))
        title = "Add Calendar Group"

    return render_template('calendars/edit_calendar_groups.html', groups=groups, form=form, group_id=group_id, title=title)

@bp.route('/calendar_groups/delete/<int:group_id>', methods=['POST'])
def delete_calendar_groups(group_id):
    group = CalendarGroup.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    flash('Calendar group deleted.', 'success')
    return redirect(url_for('calendars.edit_calendar_groups'))

@permission_required('calendar+add, calendar+edit')
@bp.route("/calendar_groups")
def calendar_groups():

    courses1 = get_canvas_courses(account="SSPPS")
    courses2= get_canvas_courses(account="SOM")
    courses = sorted(courses1 + courses2, key=lambda c: c["name"])
    groups = CalendarGroup.query.all()
    selections = CalendarGroupSelection.query.order_by(CalendarGroupSelection.course_name).all()

    # Group selections by group name
    grouped_selections = {}
    for sel in selections:
        grouped_selections.setdefault(sel.group_name, []).append({
            "id": sel.course_id,
            "name": sel.course_name
        })

    return render_template("calendars/calendar_groups.html", courses=courses, groups=groups, selections=grouped_selections)

@permission_required('calendar+add, calendar+edit')
@bp.route("/save_selections", methods=["POST"])
def save_selections():
    data = request.json
    CalendarGroupSelection.query.delete()
    for group_dom_id, courses in data.items():
        group_id = group_dom_id.replace("calendar-group-", "")
        group = CalendarGroup.query.get(int(group_id))
        for course in courses:
            db.session.add(CalendarGroupSelection(
                group_name=group.name,
                course_id=course["id"],
                course_name=course["name"]
            ))
    db.session.commit()
    return jsonify({"message": "Selections saved."})

# @permission_required('calendar+add, calendar+edit')
@bp.route("/generate_scheduled_ics", methods=["POST"])
def generate_scheduled_ics():
    print(f"[{datetime.now()}] Running scheduled ICS generation job...")

    courses1 = get_canvas_courses(account="SSPPS", state=["available"])
    courses2= get_canvas_courses(account="SOM", state=["available"])
    courses = sorted(courses1 + courses2, key=lambda c: c["name"])
    
    # Build a map from course ID to course info
    course_map = {
        f"{course['id']}": {
            "course_id": course['id'],
            "course_name": course.get('name', 'Unnamed Course'),
            "start_at": (
                course['start_at'] 
                if course.get('start_at') else
                datetime(datetime.now().year, 1, 1, tzinfo=timezone.utc)
            ),
            "end_at": (
                course['end_at'] 
                if course.get('end_at') else
                datetime(datetime.now().year, 1, 1, tzinfo=timezone.utc)
            )
        }
        for course in courses if 'id' in course 
    }

    selections = CalendarGroupSelection.query.all()
    group_data = {}
    for selection in selections:
        group = selection.group_name
        group_data.setdefault(group, []).append({
            "id": selection.course_id,
            "name": selection.course_name
        })

    # Fetch calendar groups with their filenames
    groups = CalendarGroup.query.all()
    filename_map = {group.name: group.ics_filename for group in groups}
    for group_name, courses in group_data.items():
        calendar = Calendar()
        calendar.add('prodid', f'-//Canvas Calendars//{group_name}//EN')
        calendar.add('version', '2.0')
        calendar.add('calscale', 'GREGORIAN')  # Optional but recommended
        for course in courses:            
            course_info = course_map.get(course['id'])
            if course_info:
                course_events = get_canvas_events(context_codes=f"course_{course_info['course_id']}", start_date = course_info['start_at'], end_date = course_info['end_at'])
                for item in course_events:
                    event = Event()
                    event.add('uid', f"canvas-eventid-{item['id']}")
                    event.add('dtstamp', datetime.now().replace(tzinfo=timezone.utc))
                    event.add('summary', course_info['course_name'] + " " + item["title"])
                    
                    # Remove 'Z' and replace with '+00:00' to make it ISO compliant for fromisoformat
                    dtstart = datetime.fromisoformat(item["start_at"].replace('Z', '+00:00'))
                    # Optionally convert to UTC explicitly
                    dtstart = dtstart.astimezone(timezone.utc)
                    event.add('dtstart', dtstart)

                    # Remove 'Z' and replace with '+00:00' to make it ISO compliant for fromisoformat
                    dtend = datetime.fromisoformat(item["end_at"].replace('Z', '+00:00'))
                    # Optionally convert to UTC explicitly
                    dtend = dtend.astimezone(timezone.utc)
                    event.add('dtend', dtend)

                    event.add('location', item["location_name"])
                    event.add('description', html_to_text(item.get("description", "")))

                    # Add HTML version (non-standard but widely supported)
                    # Create the HTML description with parameter
                    event['X-ALT-DESC'] = vText(item.get("description", ""))
                    event['X-ALT-DESC'].params['FMTTYPE'] = 'text/html'
                    calendar.add_component(event)
                    
        filename = filename_map.get(group_name, f"{group_name}.ics")
        full_path = os.path.join(CALENDAR_FOLDER, filename)

        with open(full_path, "wb") as f:
            f.write(calendar.to_ical())
            
    print(f"[{datetime.now()}] ICS files generated.")
    return jsonify({"message": "Calendar files updated."})

def html_to_text(html):
    if not html:
        return ""
    
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")

    # Normalize line endings and remove excessive empty lines
    text = re.sub(r'\n\s*\n+', '\n\n', text.strip())
    
    # Escape problematic characters for ICS
    text = text.replace('\\', '\\\\').replace('\n', '\\n').replace(',', '\\,').replace(';', '\\;')
    
    return text