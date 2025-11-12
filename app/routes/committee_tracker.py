from app.utils import permission_required, has_permission, committee_edit_required
from app.models import db, AcademicYear, Attendance, AYCommittee, Committee, Member, MemberRole, FrequencyType, CommitteeType, Employee, Meeting, FileUpload, User, Role, Permission
from app.forms import AYCommitteeForm, CommitteeForm, CommitteeReportForm, MemberForm, MemberRoleForm, MeetingForm, FileUploadForm, FrequencyTypeForm, CommitteeTypeForm
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, jsonify, Blueprint
from flask_login import login_required, current_user
from .academic_years import get_academic_years
import calendar
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, with_loader_criteria
from werkzeug.utils import secure_filename
import os

bp = Blueprint('committee', __name__, url_prefix='/committee_tracker')

# Allow presentations, documents, images, and PDFs
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "pages", "numbers", "key",
    "ppt", "pptx",  # PowerPoint
    "jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"
}

UPLOAD_FOLDER = 'app/static/uploads/'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

# List Committees
@bp.route('/dashboard')
@bp.route('/base_committees')
@bp.route('/')
@permission_required('committee+view, committee+add, committee+edit, committee+delete')
def base_committees():    
    form = CommitteeForm()
    base_committees = Committee.query.filter_by(deleted=False).order_by(Committee.name).all()

    return render_template('committee_tracker/base_committees.html', form = form, committees=base_committees)

def get_month_name(month_number):
    try:
        return calendar.month_name[month_number]
    except IndexError:
        return "Invalid Month"

# Add/Edit a Committee
@bp.route('/base_committee/new', methods=['GET', 'POST'])
@bp.route('/base_committee/<int:committee_id>/edit', methods=['GET', 'POST'])
@permission_required('committee+add, committee+edit')
def edit_committee(committee_id:int=None):
    committee = Committee.query.filter_by(id=committee_id, deleted=False).first() if committee_id else Committee()
    form = CommitteeForm(original_name=committee.name if committee.id else None, obj=committee)

    form.committee_type_id.choices = []
    for row in get_committee_types():
        form.committee_type_id.choices.append([row.id, row.type])

    if form.validate_on_submit():
        committee.name = form.name.data
        committee.short_name=form.short_name.data
        committee.description=form.description.data
        committee.reporting_start=form.reporting_start.data
        committee.mission = form.mission.data
        committee.committee_type_id=form.committee_type_id.data
        if committee_id:
            committee.modify_date = datetime.now()
            committee.modify_by =  current_user.id
        else:
            committee.create_date = datetime.now()
            committee.create_by =  current_user.id
        try:
            db.session.add(committee)
            db.session.commit()
            flash("Committee saved successfully!", 'success')
            return redirect(url_for('committee.base_committees'))
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                flash("ERROR: Committee name already exists (%s)" % form.name.data, 'danger')
                return render_template('committee_tracker/edit_base_committee.html', form=form)
            else:
                flash("ERROR: (%s)" % err_msg, 'danger')
                return render_template('committee_tracker/edit_base_committee.html', form=form)

    return render_template('committee_tracker/edit_base_committee.html', form=form, committee=committee)

@bp.route('/base_committee/<int:committee_id>/delete')
@permission_required('committee+delete')
def delete_base(committee_id):
    try:
        committee = Committee.query.filter_by(id=committee_id, deleted=False).first_or_404()
        # Check if any AYCommittee are assigned to this base committee
        assigned_ay = AYCommittee.query.filter_by(committee_id=committee.id, deleted=False).count()
    
        if assigned_ay > 0:
            flash("Cannot delete this committee because it is currently assigned to one or more academic years.", "danger")
            return redirect(url_for('committee.base_committees'))

        committee.deleted = True
        committee.delete_date = datetime.now()
        committee.delete_by =  current_user.id
        db.session.commit()
        flash("Committee deleted.", "success")
        return redirect(url_for('committee.base_committees'))
    except Exception as e:
        db.session.rollback()
        # return jsonify({"success": False, "message": str(e)})
        flash(str(e), "danger")
        return redirect(url_for('committee.base_committees'))
    
@bp.route('/ay_committees/')
@bp.route('<int:academic_year_id>/ay_committees/')
@permission_required('ay_committee+view, ay_committee+add, ay_committee+edit, ay_committee+delete')
def ay_committees(academic_year_id:int=None):

    academic_years = AcademicYear.query.filter_by(deleted=False).order_by(AcademicYear.year.desc()).all()

    if academic_year_id:
        current_year = AcademicYear.query.filter_by(id=academic_year_id, deleted=False).first()
    else:
        current_year = AcademicYear.query.filter_by(is_current=True, deleted=False).first()

    if current_year:
        current_ay_committees = AYCommittee.query.filter_by(academic_year_id=current_year.id, deleted=False).all()
    else:
        current_ay_committees = []

    for c in current_ay_committees:
        c.member_count = sum(1 for m in c.members if not m.deleted)

    custom_breadcrumbs = [
        {'name': 'Committees Home', 'url': '/committee_tracker'},
        {'name': f'Committess for {current_year.year}', 'url': f'/committee_tracker/{academic_year_id}/ay_committees/'}
    ]

    return render_template('committee_tracker/ay_committees.html', ay_committees=current_ay_committees, current_year=current_year, academic_years=academic_years, breadcrumbs=custom_breadcrumbs)

@bp.route('/ay_committees_by_user/<int:user_id>')
@permission_required('ay_committee+view, ay_committee+add, ay_committee+edit, ay_committee+delete')
def ay_committees_by_user(user_id:int):

    user = User.query.filter_by(id=user_id, deleted=False).first() 

    if user.id:
        employee = Employee.query.filter_by(employee_id=user.employee_id).first()

    form=CommitteeReportForm()

    # Academic Year choices
    form.academic_year.choices = [(0, "All")]
    form.academic_year.choices += [(row.id, row.year) for row in get_academic_years()]
    form.academic_year.data = [0]  # Select "All" by default

    # Committee choices
    form.committee.choices = [(0, "All")]
    form.committee.choices += [(row.id, row.name) for row in get_committees()]
    form.committee.data = [0]

    # Committee Type choices
    form.committee_type.choices = [(0, "All")]
    form.committee_type.choices += [(row.id, row.type) for row in get_committee_types()]
    form.committee_type.data = [0]

    # User choices
    form.users.choices = [(row.employee_id, f"{row.employee_last_name}, {row.employee_first_name}") for row in get_employees() if row.employee_id == employee.employee_id]
    form.users.data = [employee.employee_id]

    return render_template('reports/report_by_member.html', form=form)

# Add a Committee    
@bp.route('/ay_committee/new', methods=['GET', 'POST'])
@permission_required('ay_committee+add, ay_committee+edit')
# @committee_edit_required("edit")
def ay_committee(ay_committee_id:int=None):
    
    academic_year_id = request.args.get("academic_year_id", type=int)  # e.g. /new?academic_year_id=3
    form = AYCommitteeForm()

    # build select field choices
    form.academic_year_id.choices = [(0, 'Select Academic Year')] + [
        (row.id, row.year) for row in get_academic_years()
    ]

    # Prepare base committee list
    all_committees = get_committees()

    # 🔍 Filter committees that are already used for this academic year
    if academic_year_id:
        used_committee_ids = {
            c.committee_id for c in AYCommittee.query.filter_by(
                academic_year_id=academic_year_id, deleted=False
            ).all()
        }

        available_committees = [
            c for c in all_committees if c.id not in used_committee_ids
        ]
    else:
        available_committees = all_committees

    # Build committee choices (only unused ones if academic_year_id provided)
    form.committee_id.choices = [(0, 'Select Committee')] + [
        (row.id, f"{row.name} ({row.short_name})" if row.short_name else row.name)
        for row in available_committees
    ]
    
    form.meeting_frequency_type_id.choices = [
        (row.id, f"{row.type} ({row.multiplier}x/year)") for row in get_frequency_types()
    ]

    # ✅ Initialize copy_from_id safely with an empty list
    form.copy_from_id.choices = [(0, 'Select Previous Year')]
    
    if academic_year_id:
        form.academic_year_id.data = academic_year_id
    
    # --- Rebuild copy_from_id choices if committee selected ---
    if request.method == "POST":
        # Safely parse committee_id and academic_year_id from submitted data
        try:
            committee_id = int(request.form.get("committee_id", 0))
            ay_id = int(request.form.get("academic_year_id", 0))
        except ValueError:
            committee_id = 0
            ay_id = 0

        if committee_id:
            prev_committees = AYCommittee.query.filter(
                AYCommittee.committee_id == committee_id,
                AYCommittee.academic_year_id != ay_id,
                AYCommittee.deleted == False,
            ).order_by(AYCommittee.academic_year_id.desc()).all()

            form.copy_from_id.choices += [
                (c.id, f"{c.academic_year.year} ({c.committee.name})")
                for c in prev_committees
            ]

    if form.validate_on_submit():
        print("Form validated successfully.")
        # If user selected a committee to copy, prefill from it
        source = None
        if form.copy_from_id.data and form.copy_from_id.data != 0:
            source = AYCommittee.query.get(form.copy_from_id.data)

        aycommittee = AYCommittee()
        aycommittee.academic_year_id=form.academic_year_id.data
        aycommittee.committee_id=form.committee_id.data                     
        aycommittee.meeting_frequency_type_id=form.meeting_frequency_type_id.data
        aycommittee.meeting_duration_in_minutes=form.meeting_duration_in_minutes.data
        aycommittee.supplemental_minutes_per_frequency=form.supplemental_minutes_per_frequency.data
        aycommittee.create_date = datetime.now()
        aycommittee.create_by =  current_user.id
        try:
            db.session.add(aycommittee)
            db.session.commit()
                    
            # Copy only selected members
            selected_ids = request.form.getlist("copy_member_ids")  # list of employee_ids as strings
            if selected_ids and source:
                selected_ids = [int(eid) for eid in selected_ids]  # convert to int
                for m in source.members:
                    if m.deleted or m.employee_id not in selected_ids:
                        continue
                    new_member = Member(
                        ay_committee_id=aycommittee.id,
                        employee_id=m.employee_id,
                        member_role_id=m.member_role_id,
                        start_date=m.start_date,
                        end_date=m.end_date,
                        voting=m.voting,
                        allow_edit=m.allow_edit,
                        notes=f"Copied from {source.academic_year.year}" if hasattr(source, "academic_year") else None,
                        create_date = datetime.now(),
                        create_by =  current_user.id
                    )
                    db.session.add(new_member)

            db.session.commit()
            flash("Committee saved successfully!", "success")
            return redirect(url_for('committee.members', ay_committee_id = aycommittee.id))

        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                aycom = AYCommittee.query.filter_by(academic_year_id=form.academic_year_id.data, committee_id=form.committee_id.data, deleted=False).first()
                flash(f"Warning: Committee name already exists {aycom.committee.name} for {aycom.academic_year.year}. \n You can edit it here.", 'warning')
                return redirect(url_for('committee.members', ay_committee_id = aycom.id))
            else:
                flash(f"ERROR: {err_msg}", "danger")
                return render_template('committee_tracker/edit_ay_committee.html', form=form)
    
    # Pass flag to disable or hide the academic year field in template
    disable_academic_year = bool(academic_year_id)

    return render_template(
        "committee_tracker/edit_ay_committee.html",
        form=form,
        disable_academic_year=disable_academic_year
    )

@bp.route("/ay_committee/<int:ay_committee_id>/finalize", methods=["POST"])
@permission_required("ay_committee+edit")
def finalize_ay_committee(ay_committee_id):
    aycommittee = AYCommittee.query.filter_by(id=ay_committee_id, deleted=False).first_or_404()

    aycommittee.finalized = True
    aycommittee.finalized_date = datetime.now()
    aycommittee.finalized_by = current_user.id

    db.session.commit()

    flash(
        f"Committee '{aycommittee.committee.name}' for {aycommittee.academic_year.year} has been finalized by {current_user.username}.",
        "success"
    )
    return redirect(url_for("committee.members", ay_committee_id=ay_committee_id))


@bp.route("/ay_committee/<int:ay_committee_id>/unfinalize", methods=["POST"])
@permission_required("ay_committee+edit")
def unfinalize_ay_committee(ay_committee_id):
    aycommittee = AYCommittee.query.filter_by(id=ay_committee_id, deleted=False).first_or_404()

    aycommittee.finalized = False
    aycommittee.finalized_date = None
    aycommittee.finalized_by = None

    db.session.commit()

    flash(
        f"Committee '{aycommittee.committee.name}' has been unlocked for editing.",
        "info"
    )
    return redirect(url_for("committee.members", ay_committee_id=ay_committee_id))


@bp.route('/get_previous_committees/<int:committee_id>/<int:current_ay_id>')
def get_previous_committees(committee_id, current_ay_id):
    """Return JSON of previous AYCommittee records for a given committee,
       excluding the current academic year"""
    previous = (
        AYCommittee.query
        .join(AcademicYear)
        .filter(
            AYCommittee.deleted == False,
            AYCommittee.committee_id == committee_id,
            AYCommittee.academic_year_id != current_ay_id
        )
        .order_by(AcademicYear.year.desc())
        .all()
    )

    data = [
        {"id": row.id, "label": f"{row.academic_year.year}"}
        for row in previous
    ]
    return jsonify(data)

@bp.route("/get_source_committee/<int:ay_committee_id>")
def get_source_committee(ay_committee_id):
    """AJAX: Return meeting details and member list for a previous AYCommittee"""
    aycom = AYCommittee.query.filter_by(id=ay_committee_id, deleted=False).first()

    if not aycom:
        return jsonify({"error": "Not found"}), 404

    details = {
        "meeting_frequency_type_id": aycom.meeting_frequency_type_id,
        "meeting_duration_in_minutes": aycom.meeting_duration_in_minutes,
        "supplemental_minutes_per_frequency": aycom.supplemental_minutes_per_frequency,
        "members": []
    }

    for m in aycom.members:
        if m.deleted:
            continue
        details["members"].append({
            "employee_id": m.employee_id,
            "employee_name": m.employee.employee_name if hasattr(m.employee, "employee_name") else f"Employee #{m.employee_id}",
            "member_role_id": m.member_role_id,
            "member_role": m.member_role.role if hasattr(m.member_role, "role") else "",
            "start_date": m.start_date.strftime("%Y-%m-%d") if m.start_date else "",
            "end_date": m.end_date.strftime("%Y-%m-%d") if m.end_date else "",
            "voting": m.voting,
            "allow_edit": m.allow_edit
        })

    return jsonify(details)

@bp.route("/ay_committees/batch_copy", methods=["GET", "POST"])
@permission_required("ay_committee+add, ay_committee+edit")
def batch_copy_ay_committees():
    academic_years = AcademicYear.query.filter_by(deleted=False).order_by(AcademicYear.year.desc()).all()

    # Determine source and target year
    source_year_id = request.args.get("source_year_id", type=int)
    target_year_id = request.args.get("target_year_id", type=int)

    if not source_year_id:
        current = AcademicYear.query.filter_by(is_current=True, deleted=False).first()
        source_year_id = current.id if current else None

    # Fetch source committees and count members
    source_committees = []
    if source_year_id:
        ay_coms = AYCommittee.query.filter_by(academic_year_id=source_year_id, deleted=False).all()
        for c in ay_coms:
            member_count = sum(1 for m in c.members if not m.deleted)
            source_committees.append({
                "id": c.id,
                "committee_id": c.committee_id,
                "committee_name": c.committee.name,
                "member_count": member_count
            })

    # Identify which committees already exist in the target year
    existing_committee_ids = set()
    if target_year_id:
        existing_committee_ids = {
            c.committee_id
            for c in AYCommittee.query.filter_by(
                academic_year_id=target_year_id, deleted=False
            ).all()
        }

    if request.method == "POST":
        source_year_id = int(request.form.get("source_year_id"))
        target_year_id = int(request.form.get("target_year_id"))
        selected_committee_ids = [int(cid) for cid in request.form.getlist("committee_ids")]
        copy_members = "copy_members" in request.form

        source_committees_to_copy = AYCommittee.query.filter(
            AYCommittee.academic_year_id == source_year_id,
            AYCommittee.id.in_(selected_committee_ids),
            AYCommittee.deleted == False
        ).all()

        created = []
        for src in source_committees_to_copy:
            exists = AYCommittee.query.filter_by(
                academic_year_id=target_year_id,
                committee_id=src.committee_id,
                deleted=False
            ).first()
            if exists:
                continue

            new_aycom = AYCommittee(
                academic_year_id=target_year_id,
                committee_id=src.committee_id,
                meeting_frequency_type_id=src.meeting_frequency_type_id,
                meeting_duration_in_minutes=src.meeting_duration_in_minutes,
                supplemental_minutes_per_frequency=src.supplemental_minutes_per_frequency,
                create_date = datetime.now(),
                create_by =  current_user.id
            )
            db.session.add(new_aycom)
            db.session.flush()

            if copy_members:
                for m in src.members:
                    if m.deleted:
                        continue
                    new_member = Member(
                        ay_committee_id=new_aycom.id,
                        employee_id=m.employee_id,
                        member_role_id=m.member_role_id,
                        start_date=m.start_date,
                        end_date=m.end_date,
                        voting=m.voting,
                        allow_edit=m.allow_edit,
                        notes=f"Copied from {src.academic_year.year}",
                        create_date = datetime.now(),
                        create_by =  current_user.id
                    )
                    db.session.add(new_member)

            created.append(src.committee.name)

        db.session.commit()
        flash(
            f"Copied {len(created)} committee(s) to {dict((a.id, a.year) for a in academic_years)[target_year_id]} successfully!",
            "success",
        )
        return redirect(url_for("committee.ay_committees", academic_year_id=target_year_id))

    return render_template(
        "committee_tracker/batch_copy_ay_committees.html",
        academic_years=academic_years,
        source_year_id=source_year_id,
        target_year_id=target_year_id,
        committees=source_committees,
        existing_committee_ids=existing_committee_ids,
    )

@bp.route("/ay_committee/<int:ay_committee_id>/members/json")
@permission_required("ay_committee+view")
def get_committee_members_json(ay_committee_id):
    """Return JSON list of members for a given AYCommittee."""
    aycom = AYCommittee.query.filter_by(id=ay_committee_id, deleted=False).first()
    if not aycom:
        return jsonify({"error": "Committee not found"}), 404

    members = [
        {
            "employee_name": m.employee.employee_name if hasattr(m.employee, "employee_name") else f"Employee #{m.employee_id}",
            "role": m.member_role.role if hasattr(m.member_role, "role") else "",
            "voting": m.voting,
            "allow_edit": m.allow_edit,
            "start_date": m.start_date.strftime("%Y-%m-%d") if m.start_date else "",
            "end_date": m.end_date.strftime("%Y-%m-%d") if m.end_date else "",
        }
        for m in aycom.members if not m.deleted
    ]
    return jsonify({"committee": aycom.committee.name, "members": members})


@bp.route("/save_commitment/<int:ay_committee_id>", methods=["POST"])
# @permission_required('ay_committee+add, ay_committee+edit')
@committee_edit_required("edit")
def save_commitment(ay_committee_id):
    form = AYCommitteeForm()

    # Populate choices before validation
    form.academic_year_id.choices = [(ay.id, ay.year) for ay in (get_academic_years() or [])]
    form.committee_id.choices = [(c.id, f"{c.name} ({c.short_name})" if c.short_name else c.name) for c in (get_committees() or [])]
    form.meeting_frequency_type_id.choices = [(f.id, f"{f.type} ({f.multiplier}x/year)") for f in (get_frequency_types() or [])]

    if form.validate_on_submit():
        aycommittee = AYCommittee.query.get_or_404(ay_committee_id)
        aycommittee.meeting_frequency_type_id = form.meeting_frequency_type_id.data
        aycommittee.meeting_duration_in_minutes = form.meeting_duration_in_minutes.data
        aycommittee.supplemental_minutes_per_frequency = form.supplemental_minutes_per_frequency.data
        aycommittee.modify_date = datetime.now()
        aycommittee.modify_by =  current_user.id
        db.session.commit()
        return jsonify(success=True, message="Commitment hours updated")
    return jsonify(success=False, error=form.errors)

@bp.route('/delete_ay_committee/<int:ay_committee_id>')
# @permission_required('ay_committee+delete')
@committee_edit_required("delete")
def delete_ay_committee(ay_committee_id):
    try:
        ay_committee = AYCommittee.query.filter_by(id=ay_committee_id, deleted=False).first_or_404()
        ay_committee.deleted = True
        ay_committee.delete_date = datetime.now()
        ay_committee.delete_by =  current_user.id
        academic_year_id = ay_committee.academic_year_id

        db.session.commit()
        # delete members, meetings, files associated with this AYCommittee
        for member in ay_committee.members:
            member.deleted = True
            member.delete_date = datetime.now()
            member.delete_by =  current_user.id
            db.session.commit()
        for meeting in ay_committee.meetings:
            meeting.deleted = True
            meeting.delete_date = datetime.now()
            meeting.delete_by =  current_user.id
            db.session.commit()
            for attendance in meeting.attendance:
                attendance.deleted = True
                attendance.delete_date = datetime.now()
                attendance.delete_by =  current_user.id
                db.session.commit()
        for file in ay_committee.fileuploads:
            file.deleted = True
            file.delete_date = datetime.now()
            file.delete_by =  current_user.id
            db.session.commit()
        flash(f"Committee {ay_committee.committee.name} for {ay_committee.academic_year.year} deleted successfully.", "success")
        return redirect(url_for('committee.ay_committees', academic_year_id=academic_year_id))
    except Exception as e:
        db.session.rollback()
        # return jsonify({"success": False, "message": str(e)})
        flash(str(e), "danger")
        return redirect(url_for('committee.ay_committees'))
    
# List Frequency Type
@bp.route('/frequency_types')
@permission_required("frequency_type+view,frequency_type+add,frequency_type+edit,frequency_type+delete")
def frequency_types():
    form = FrequencyTypeForm()
    ftypes = get_frequency_types()
    return render_template('committee_tracker/frequency_types.html', form=form, ftypes = ftypes)

# Add/Edit Frequency Type
@bp.route("/frequency_type/new/", methods=["POST", "GET"])
@bp.route("/frequency_type/<int:frequency_type_id>/", methods=["POST", "GET"])
@permission_required("frequency_type+add, frequency_type+edit")
def edit_frequency_type(frequency_type_id:int=None):
    ftypes = get_frequency_types()
    ftype = FrequencyType.query.filter_by(id=frequency_type_id, deleted=False).first() if frequency_type_id else FrequencyType()
    form = FrequencyTypeForm()
    if request.method == "POST":
        ftype.type = request.form['type']
        ftype.multiplier = request.form['multiplier']
        if frequency_type_id:
            ftype.modify_date = datetime.now()
            ftype.modify_by =  current_user.id
        else:
            ftype.create_date = datetime.now()
            ftype.create_by =  current_user.id
        try:
            db.session.add(ftype)
            db.session.commit()
            return jsonify({
                'success': True,
                'ftype': {
                    'id': ftype.id,
                    'type': ftype.type,
                    'multiplier': ftype.multiplier
                }
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                return jsonify({"success": False, "message":"Frequency Type already exists (%s)" % form.type.data})
            else:
                return jsonify({"success": False, "message":"unknown error adding frequency type."})
        except Exception as e:
            db.session.rollback()
            print(str(e))
            return jsonify({"success": False, "message": str(e)})
    
    return render_template('committee_tracker/frequency_types.html', form=form, ftypes = ftypes)

# Delete Frequency Type
@bp.route('/frequency_type/<int:frequency_type_id>', methods=['DELETE'])
@permission_required("frequency_type+delete")
def delete_frequency_type(frequency_type_id):
    try:
        ftype = FrequencyType.query.filter_by(id=frequency_type_id, deleted=False).first()
        # Check if any frequency_type is assigned to committees 
        assigned_com = Committee.query.filter_by(frequency_type_id=ftype.id, deleted=False).count()
    
        if assigned_com > 0:
            return jsonify({"success": False, "message": "Cannot delete this frequency type because it is currently assigned to one or more committees."})
        
        if not ftype:
            return jsonify({"success": False, "message": "Frequency Type not found"})
        ftype.deleted = True
        ftype.delete_date = datetime.now()
        ftype.delete_by =  current_user.id
        db.session.commit()
        return jsonify({"success": True, "deleted_frequency_type_id": frequency_type_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

# Add/List Committee Type
@bp.route('/committee_types')
@permission_required("committee_type+view,committee_type+add,committee_type+edit,committee_type+delete")
def committee_types():
    form = CommitteeTypeForm()
    ctypes = get_committee_types()
    return render_template('committee_tracker/committee_types.html', form=form, ctypes = ctypes)

# Add/Edit Committee Type
@bp.route("/committee_type/new/", methods=["POST", "GET"])    
@bp.route("/committee_type/<int:committee_type_id>/", methods=["POST", "GET"])
@permission_required("committee_type+add,committee_type+edit")
def edit_committee_type(committee_type_id:int=None):
    ctypes = get_committee_types()
    ctype = CommitteeType.query.filter_by(id=committee_type_id, deleted=False).first() if committee_type_id else CommitteeType()
    form = CommitteeTypeForm()
    if request.method == "POST":
        ctype.type = request.form['type']
        if committee_type_id:
            ctype.modify_date = datetime.now()
            ctype.modify_by =  current_user.id
        else:
            ctype.create_date = datetime.now()
            ctype.create_by =  current_user.id
        try:
            db.session.add(ctype)
            db.session.commit()
            return jsonify({
                'success': True,
                'ctype': {
                    'id': ctype.id,
                    'type': ctype.type
                }
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                return jsonify(success=False,message="Committee Type already exists (%s)" % form.type.data)
            else:
                print(err_msg)
                return jsonify(success=False,message="unknown error adding committee type.")
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": str(e)})
    return render_template('committee_tracker/committee_types.html', form=form, ctypes = ctypes)

# Delete Committee Type
@bp.route('/committee_type/<int:committee_type_id>', methods=['DELETE'])
@permission_required("committee_type+delete")
def delete_committee_type(committee_type_id):
    try:
        ctype = CommitteeType.query.filter_by(id=committee_type_id, deleted=False).first()
        if not ctype:
            return jsonify({"success": False, "message": "Committee Type not found"})
        
        # Check if any committee_type is assigned to committees 
        assigned_com = Committee.query.filter_by(committee_type_id=ctype.id, deleted=False).count()
    
        if assigned_com > 0:
            return jsonify({"success": False, "message": "Cannot delete this committee type because it is currently assigned to one or more committees."})
        
        ctype.deleted = True
        ctype.delete_date = datetime.now()
        ctype.delete_by =  current_user.id
        db.session.commit()

        return jsonify({"success": True, "deleted_committee_type_id": committee_type_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

# List Member Role
@bp.route('/member_roles')
@permission_required("member_role+view,member_role+add,member_role+edit,member_role+delete")
def member_roles():
    form = MemberRoleForm()
    roles = MemberRole.query.filter_by(deleted=False).all()
    return render_template('committee_tracker/member_roles.html', form=form, roles = roles)

# Edit Member Role
@bp.route("/member_role/new/", methods=["POST", "GET"])
@bp.route("/member_role/<int:role_id>/", methods=["POST", "GET"])
@permission_required("member_role+add, member_role+edit")
def edit_role(role_id:int=None):
    mroles = get_member_roles()
    mrole = MemberRole.query.filter_by(id=role_id, deleted=False).first() if role_id else MemberRole()
    form = MemberRoleForm()
    if request.method == "POST":
        mrole.role = request.form['role']
        mrole.description = request.form['description']
        if role_id:
            mrole.modify_date = datetime.now()
            mrole.modify_by =  current_user.id
        else:
            mrole.create_date = datetime.now()
            mrole.create_by =  current_user.id
        try:
            db.session.add(mrole)
            db.session.commit()
            return jsonify({
                'success': True,
                'role': {
                    'id': mrole.id,
                    'role': mrole.role,
                    'description': mrole.description
                }
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                return jsonify({"success": False, "message": "Member Role already exists (%s)" % form.role.data})
            else:
                return jsonify({"success": False, "message": err_msg})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": str(e)})
    return render_template('committee_tracker/member_roles.html', form=form, roles = mroles)

# Delete Member Role
@bp.route('/member_role/<int:role_id>', methods=['DELETE'])
@permission_required("member_role+delete")
def delete_role(role_id):
    try:
        role = MemberRole.query.filter_by(id=role_id, deleted=False).first()
        if not role:
            return jsonify({"success": False, "message": "Role not found"})
        
        # Check if any members is assigned to member role 
        assigned_members = Member.query.filter_by(member_role_id=role.id, deleted=False).count()
    
        if assigned_members > 0:
            return jsonify({"success": False, "message": "Cannot delete this member role because it is currently assigned to one or more members."})
        
        role.deleted = True
        role.delete_date = datetime.now()
        role.delete_by =  current_user.id
        db.session.commit()

        return jsonify({"success": True, "deleted_role_id": role_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

# List Members    
@bp.route('/<int:ay_committee_id>/members/', methods=['GET'])
@permission_required("ay_committee+add,ay_committee+edit,ay_committee+view")
# @committee_edit_required("edit")
def members(ay_committee_id:int):
    memberForm = MemberForm()
    memberForm.ay_committee_id.data = ay_committee_id
    memberForm.employee_id.choices = [('', 'Select one')]
    memberForm.member_role_id.choices = [('', 'Select one')]

    for row in get_employees():
        memberForm.employee_id.choices.append(
            (row.employee_id, f"{row.employee_last_name}, {row.employee_first_name} ({row.username})")
        )

    for row in get_member_roles():
        memberForm.member_role_id.choices.append((row.id, row.role))

    aycommittee = AYCommittee.query.filter_by(id=ay_committee_id, deleted=False).options(
            joinedload(AYCommittee.members),
            joinedload(AYCommittee.fileuploads),
            joinedload(AYCommittee.meetings),
            with_loader_criteria(FileUpload, lambda f: f.deleted == False),
            with_loader_criteria(Meeting, lambda m: m.deleted == False),
        ).first() if ay_committee_id else AYCommittee()
    # print(aycommittee.members)
    meetingForm = MeetingForm(ay_committee_id=ay_committee_id)
    uploadForm = FileUploadForm(ay_committee_id=ay_committee_id)

    aycommitteeForm = AYCommitteeForm(obj=aycommittee)

    # build select field choices
    aycommitteeForm.academic_year_id.choices = [(0, 'Select Academic Year')] + [
        (row.id, row.year) for row in get_academic_years()
    ]

    aycommitteeForm.committee_id.choices = [(0, 'Select Committee')] + [
        (row.id, f"{row.name} ({row.short_name})" if row.short_name else row.name)
        for row in get_committees()
    ]

    aycommitteeForm.meeting_frequency_type_id.choices = [
        (row.id, f"{row.type} ({row.multiplier}x/year)") for row in get_frequency_types()
    ]

    if request.method == "GET":
        aycommitteeForm.process(obj=aycommittee)

    aycommittee.committee.reporting_start_month_name = get_month_name(aycommittee.committee.reporting_start) if aycommittee.committee and aycommittee.committee.reporting_start else "N/A"

    return render_template('committee_tracker/members.html', aycommitteeForm=aycommitteeForm, memberForm=memberForm, meetingForm=meetingForm, 
                           uploadForm=uploadForm, aycommittee=aycommittee)

@bp.route('/add_member', methods=['POST'])
# @permission_required("member+add, member+edit")
@committee_edit_required("edit")
def add_member():
    form = MemberForm(request.form)
    form.employee_id.choices = [(['', 'Select one'])]
    form.member_role_id.choices = [(['', 'Select one'])]
    for row in get_employees():
        form.employee_id.choices.append([row.employee_id, row.employee_last_name+', '+row.employee_first_name])
    for row in get_member_roles():
        form.member_role_id.choices.append([row.id, row.role])
    if form.validate_on_submit():
        new_member = Member(
            ay_committee_id=form.ay_committee_id.data,
            employee_id=form.employee_id.data,
            member_role_id=form.member_role_id.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            voting=form.voting.data,
            allow_edit=form.allow_edit.data,
            notes=form.notes.data,
            create_date = datetime.now(),
            create_by =  current_user.id
        )

        try:
            db.session.add(new_member)
            db.session.commit()       
            new_member.user = Employee.query.filter_by(employee_id=new_member.employee_id).first()
            new_member.member_role = MemberRole.query.filter_by(id=new_member.member_role_id, deleted=False).first()
            add_member_as_user(employee_id=new_member.employee_id)

            return jsonify({
                'success': True,
                'message':'Member '+new_member.user.employee_name+' added successfully!',
                'member': {
                    'id': new_member.id,
                    'ay_committee_id':new_member.ay_committee_id, 
                    'employee_id':new_member.employee_id, 
                    "user": new_member.user.employee_name,
                    "member_role_id": new_member.member_role_id,
                    "member_role": new_member.member_role.role,
                    "start_date": new_member.start_date.strftime('%Y-%m-%d') if new_member.start_date else "",
                    "end_date": new_member.end_date.strftime('%Y-%m-%d') if new_member.end_date else "",
                    "voting": new_member.voting,
                    "allow_edit": new_member.allow_edit,
                    "notes": new_member.notes
                }
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                return jsonify({"success": False, "message":"Member already exists."})
            else:
                print(err_msg)
                return jsonify({"success": False, "message":"unknown error adding member."})
    else:
        message=[]
        errors=[]
        if form.errors:
            for key,value in form.errors.items():
                for i in value:
                    message.extend(value)
                    errors.append(key)
        return jsonify({"message": message, "errors": errors}), 400
    
@bp.route('/edit_member/<int:member_id>', methods=['POST'])
# @permission_required("member+add, member+edit")
@committee_edit_required("edit")
def edit_member(member_id:int):
    # member = db.session.query(Member).get(member_id)
    member = Member.query.filter_by(id=member_id, deleted=False).first()
    form = MemberForm()
    form.employee_id.choices = [(['', 'Select one'])]
    form.member_role_id.choices = [(['', 'Select one'])]
    for row in get_employees():
        form.employee_id.choices.append([row.employee_id, row.employee_last_name+', '+row.employee_first_name])
    for row in get_member_roles():
        form.member_role_id.choices.append([row.id, row.role])
    if form.validate_on_submit():
        try:
            member.notes = form.notes.data
            member.member_role_id = form.member_role_id.data
            member.start_date = form.start_date.data
            member.end_date = form.end_date.data           
            member.voting=form.voting.data
            member.allow_edit=form.allow_edit.data
            db.session.commit()
            member.user = Employee.query.filter_by(employee_id=member.employee_id).first()
            member.member_role = MemberRole.query.filter_by(id=member.member_role_id, deleted=False).first()
            member.modify_date = datetime.now()
            member.modify_by =  current_user.id
            add_member_as_user(employee_id=member.employee_id)

            return jsonify({
                'success': True,
                'message':'Member '+member.user.employee_name+' saved successfully!',
                'member': {
                    'id': member.id,
                    'ay_committee_id':member.ay_committee_id, 
                    'employee_id':member.employee_id, 
                    "user": member.user.employee_name,
                    "member_role_id": member.member_role_id,
                    "member_role": member.member_role.role,
                    "start_date": member.start_date.strftime('%Y-%m-%d') if member.start_date else "",
                    "end_date": member.end_date.strftime('%Y-%m-%d') if member.end_date else "",
                    "voting": member.voting,
                    "allow_edit": member.allow_edit,
                    "notes": member.notes
                }
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE constraint failed" in err_msg:
                return jsonify({"success": False, "message":"Member already exists."})
            else:
                return jsonify({"success": False, "message":"unknown error adding member."})
    else:
        message=[]
        errors=[]
        if form.errors:
            for key,value in form.errors.items():
                for i in value:
                    message.extend(value)
                    errors.append(key)
        return jsonify({"message": message, "errors": errors}), 400

@bp.route('/delete_member/<int:member_id>', methods=['POST'])
# @permission_required("member+delete")
@committee_edit_required("edit")
def delete_member(member_id:int):
        
    try:
        member = Member.query.filter_by(id=member_id, deleted=False).first()
        user = Employee.query.filter_by(employee_id=member.employee_id).first()
        form = MemberForm()
        if member:
            member.notes = form.notes.data
            member.deleted = True
            member.delete_date = datetime.now()
            member.delete_by =  current_user.id
            
            db.session.commit()
            return jsonify({'success': True, 
                            'message':'Member '+user.employee_name+' deleted successfully!',
                            'member': {
                                "notes": member.notes,
                                "deleted": member.deleted,
                                "delete_date": member.delete_date.strftime('%Y-%m-%d')
                            }
                        })
        return jsonify({'success': False, 'message':'Member not found'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

# @permission_required("member+add, member+edit")
def add_member_as_user(employee_id=None):
    user = User.query.filter_by(employee_id=employee_id, deleted=False).first() or User()
    role = Role.query.filter_by(name="Committee Viewer", deleted=False).first()
    
    if not user.id:
        employee = Employee.query.filter_by(employee_id=employee_id).first()
        user.role_id = role.id
        user.username = employee.username
        user.employee_id = employee.employee_id
        user.create_date = datetime.now()
        user.create_by = current_user.id
        db.session.add(user)
        db.session.commit()
        
        print("success")
        flash("User saved successfully.", "success")
    else:
        committee_viewer_perm = Permission.query.filter_by(deleted=False).filter(Permission.resource=="committee", Permission.action=="view").first()
        role_permission_ids = set(p.id for p in user.role.permissions) if user.role else set()
        user_permission_ids = set(p.id for p in user.permissions)
        combined_permission_ids = role_permission_ids.union(user_permission_ids)
        if committee_viewer_perm.id not in combined_permission_ids:
            user_permission_ids.add(committee_viewer_perm.id)
            user.permissions = Permission.query.filter_by(deleted=False).filter(Permission.id.in_(user_permission_ids)).all()
            user.modify_date = datetime.now()
            user.modify_by = current_user.id
            db.session.add(user)
            db.session.commit()
    return user

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# @bp.route("/<int:ay_committee_id>/upload", methods=["POST"])
@bp.route("/upload", methods=["POST"])
# @permission_required("document+add, document+edit")
@committee_edit_required("edit")
def upload_files():
    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    uploaded_files = request.files.getlist("files")
    saved_files = []

    for file in uploaded_files:
        if file.filename == "" or not allowed_file(file.filename):
            continue
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        
        # Append a timestamp to ensure uniqueness
        # unique_filename = f"{name}_{int(time.time())}{ext}"
        unique_filename = f"{name}_{datetime.now().strftime('%Y%m%d')}{ext}"        
        
        # Alternative: Use UUID
        # unique_filename = f"{name}_{uuid.uuid4().hex}{ext}"
        
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)
        saved_files.append(unique_filename)

        new_file = FileUpload(ay_committee_id=request.form['ay_committee_id'],filename=unique_filename,upload_date=datetime.now())
        new_file.upload_date = datetime.now()
        new_file.upload_by =  current_user.id

        try:
            db.session.add(new_file)
            db.session.commit()            
        except Exception as e:
            return f"ERROR:{e}"
        
    return jsonify({"success": "Files uploaded successfully", "files": saved_files})

@bp.route("/<int:ay_committee_id>/uploaded_files", methods=["GET"])
# @permission_required("document+view, document+add, document+edit, document+delete")
# @committee_edit_required("edit")
def uploaded_files(ay_committee_id:int):
    allfiles = FileUpload.query.filter_by(ay_committee_id=ay_committee_id, deleted=False).all()
    files = [{"ay_committee_id": f.ay_committee_id, "name": f.filename, "size": os.path.getsize(os.path.join(UPLOAD_FOLDER, f.filename)), "id": f.id} for f in allfiles]
    return jsonify({"files": files})

# Delete File
@bp.route('/delete_file/<int:file_id>', methods=['POST'])
# @permission_required("document+delete")
@committee_edit_required("edit")
def delete_file(file_id:int):
    try:
        ay_committee_id = request.form.get("ay_committee_id")
        doc = FileUpload.query.filter_by(id=file_id, deleted=False).first()
        doc.delete_date = datetime.now()
        doc.deleted = True
        doc.delete_by =  current_user.id
        
        if not doc:
            return jsonify({"success": False, "message": "File not found"})
        db.session.commit()

        return jsonify({"success": True, "message": doc.filename+" successfully deleted."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

@bp.route("/save_meeting", methods=["POST"])
# @permission_required("meeting+add, meeting+edit")
@committee_edit_required("edit")
def save_meeting():
    form = MeetingForm()
    meeting_id = request.form["meeting_id"]
    # print(meeting_id)
    if form.validate():
        if meeting_id:
            meeting = Meeting.query.filter_by(id=meeting_id, deleted=False).first()
            meeting.modify_date = datetime.now()
            meeting.modify_by =  current_user.id
            if not meeting:
                return jsonify({"error": "Meeting not found"}), 404
        else:
            meeting = Meeting()
            meeting.create_date = datetime.now()
            meeting.create_by =  current_user.id

        meeting.ay_committee_id = request.form["ay_committee_id"]
        meeting.title = request.form["title"]
        meeting.date = request.form["date"]
        meeting.location = request.form["location"]
        meeting.notes = request.form["notes"]

        db.session.add(meeting)
        db.session.commit()
        
        return jsonify({"success": True, "meetings": get_meetings_json(meeting.ay_committee_id)})
    else:
        print("error")
        return jsonify({"error": "Invalid data"}), 400

@bp.route("/delete_meeting/<int:meeting_id>", methods=["POST"])
@committee_edit_required("edit")
def delete_meeting(meeting_id:int):
    try:
        ay_committee_id = request.form.get("ay_committee_id")
        meeting = Meeting.query.filter_by(id=meeting_id, ay_committee_id=ay_committee_id, deleted=False).first()

        if not meeting:
            return jsonify({"error": "Meeting not found"}), 404

        meeting.delete_date = datetime.now()
        meeting.deleted = True
        meeting.delete_by =  current_user.id

        db.session.commit()

        return jsonify({"success": True, "meetings": get_meetings_json(ay_committee_id)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

@bp.route("/save_attendance", methods=["POST"])
# @permission_required("meeting+add, meeting+edit")
@committee_edit_required("edit")
def save_attendance():
    try:
        meeting_id = request.form.get("meeting_id")
        
        if not meeting_id:
            msg = "No meeting specified."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=msg), 400
            flash(msg, "danger")
            return redirect(request.referrer)

        meeting = Meeting.query.get_or_404(meeting_id)

        # Loop through all form keys starting with 'status_'
        for key, value in request.form.items():
            if key.startswith("status_"):
                print(key, value)
                member_id = key.replace("status_", "")
                status = value.strip()  # Can be '', "Present", "Absent", or "Excused"

                # Find existing attendance record or create a new one
                attendance = Attendance.query.filter_by(
                    meeting_id=meeting_id,
                    member_id=member_id
                ).first()

                if attendance:
                    # Update existing record
                    attendance.status = status if status else None
                    attendance.modify_date = datetime.now()
                    attendance.modify_by = current_user.id
                else:
                    # Create new record
                    new_attendance = Attendance(
                        meeting_id=meeting_id,
                        member_id=member_id,
                        status=status if status else None,
                        create_date=datetime.now(),
                        create_by=current_user.id
                    )
                    db.session.add(new_attendance)

        db.session.commit()
        # print(get_meetings_json(meeting.ay_committee_id))
        return jsonify({"success": True, "meetings": get_meetings_json(meeting.ay_committee_id)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

@bp.route("/<int:ay_committee_id>/meetings/json")
# @permission_required("meeting+view, meeting+add, meeting+edit, meeting+delete")
# @committee_edit_required("edit")
def meetings_json(ay_committee_id: int):
    return jsonify(get_meetings_json(ay_committee_id))

def get_meetings_json(ay_committee_id):
    meetings = Meeting.query.filter_by(ay_committee_id=ay_committee_id, deleted=False).all()
    data = []
    for m in meetings:
        member_statuses = []
        for member in m.ay_committee.members:
            if member.deleted:
                continue
            record = next((a for a in m.attendance if a.member_id == member.id), None)
            status = record.status if record else "—"
            member_statuses.append({
                "name": f"{member.employee.employee_last_name}, {member.employee.employee_first_name}",
                "status": status
            })

        data.append({
            "id": m.id,
            "ay_committee_id": m.ay_committee_id,
            "title": m.title,
            "date": m.date.strftime("%Y-%m-%d"),
            "location": m.location or "",
            "notes": m.notes or "",
            "attendance": member_statuses
        })
    return data

@bp.route("/<int:ay_committee_id>/meeting/<int:meeting_id>/attendance/json")
# @permission_required("meeting+view")
def meeting_attendance_json(ay_committee_id, meeting_id):
    meeting = Meeting.query.filter_by(id=meeting_id, ay_committee_id=ay_committee_id, deleted=False).first()
    if not meeting:
        return jsonify({"members": [], "attendance": {}})

    # Build members list
    members = [
        {"id": m.id, "first_name": m.employee.employee_first_name, "last_name": m.employee.employee_last_name}
        for m in meeting.ay_committee.members if not m.deleted
    ]

    # Build existing attendance dict
    attendance = {a.member_id: a.status for a in meeting.attendance if not a.deleted}

    return jsonify({"members": members, "attendance": attendance})

def get_frequency_types():
    ftypes = FrequencyType.query.filter_by(deleted=False).order_by(FrequencyType.type).all()
    return ftypes

def get_committee_types():
    ctypes = CommitteeType.query.filter_by(deleted=False).order_by(CommitteeType.type).all()
    return ctypes

def get_member_roles():
    mroles = MemberRole.query.filter_by(deleted=False).order_by(MemberRole.role).all()
    return mroles

def get_committees():
    data = Committee.query.filter_by(deleted=False).order_by(Committee.name).all()
    return data

def get_employees():
    data = Employee.query.filter(Employee.username.isnot(None),Employee.employee_status == 'Active').order_by(Employee.employee_last_name,Employee.employee_first_name).all()
    return data