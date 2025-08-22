from app.utils import admin_required, permission_required, has_permission
from app.models import db, AcademicYear, Attendance, AYCommittee, Committee, Member, MemberRole, FrequencyType, CommitteeType, Employee, Meeting, FileUpload, User, Role, Permission
from app.forms import AYCommitteeForm, CommitteeForm, CommitteeReportForm, MemberForm, MemberRoleForm, MeetingForm, FileUploadForm, FrequencyTypeForm, CommitteeTypeForm
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, jsonify, Blueprint
from flask_login import login_required
from .academic_years import get_academic_years
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

# Add/Edit a Committee
@bp.route('/base_committee/new', methods=['GET', 'POST'])
@bp.route('/base_committee/<int:committee_id>/edit', methods=['GET', 'POST'])
@permission_required('committee+add, committee+edit')
def edit_committee(committee_id:int=None):
    committee = Committee.query.filter_by(id=committee_id, deleted=False).first() if committee_id else Committee()
    form = CommitteeForm(original_name=committee.name if committee.id else None, obj=committee)
    # form.frequency_type_id.choices = []
    # for row in get_frequency_types():
    #     form.frequency_type_id.choices.append([row.id, row.type])
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
        # db.session.delete(committee)
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
def ay_committee(ay_committee_id:int=None):

    form = AYCommitteeForm(academic_year_id = request.args.get('academic_year_id', type=int))

    # build select field choices
    form.academic_year_id.choices = [(0, 'Select Academic Year')] + [
        (row.id, row.year) for row in get_academic_years()
    ]

    form.committee_id.choices = [(0, 'Select Committee')] + [
        (row.id, f"{row.name} ({row.short_name})" if row.short_name else row.name)
        for row in get_committees()
    ]

    form.meeting_frequency_type_id.choices = [
        (row.id, row.type) for row in get_frequency_types()
    ]

    if request.method == "GET":
        form.process()


    if form.validate_on_submit():
        aycommittee = AYCommittee()
        aycommittee.academic_year_id=form.academic_year_id.data
        aycommittee.committee_id=form.committee_id.data                     
        aycommittee.meeting_frequency_type_id=form.meeting_frequency_type_id.data
        aycommittee.meeting_duration_in_minutes=form.meeting_duration_in_minutes.data
        aycommittee.supplemental_minutes_per_frequency=form.supplemental_minutes_per_frequency.data

        try:
            db.session.add(aycommittee)
            db.session.commit()
            flash("Committee has been saved!", 'success')   
            return redirect(url_for('committee.members', ay_committee_id = aycommittee.id))

        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                aycom = AYCommittee.query.filter_by(academic_year_id=form.academic_year_id.data, committee_id=form.committee_id.data, deleted=False).first()
                flash(f"Warning: Committee name already exists {aycom.committee.name} for {aycom.academic_year.year}. \n You can edit it here.", 'warning')
                return redirect(url_for('committee.members', ay_committee_id = aycom.id))
            else:
                flash("ERROR: (%s)" % err_msg, 'danger')
                return render_template('committee_tracker/edit_ay_committee.html', form=form)
    
    return render_template('committee_tracker/edit_ay_committee.html', form=form)

@bp.route("/save_commitment/<int:ay_committee_id>", methods=["POST"])
@permission_required('ay_committee+add, ay_committee+edit')
def save_commitment(ay_committee_id):
    form = AYCommitteeForm()

    # Populate choices before validation
    form.academic_year_id.choices = [(ay.id, ay.year) for ay in get_academic_years()]
    form.committee_id.choices = [(c.id, f"{c.name} ({c.short_name})" if c.short_name else c.name) for c in get_committees()]
    form.meeting_frequency_type_id.choices = [(f.id, f.type) for f in get_frequency_types()]
    
    if form.validate_on_submit():
        aycommittee = AYCommittee.query.get_or_404(ay_committee_id)
        aycommittee.meeting_frequency_type_id = form.meeting_frequency_type_id.data
        aycommittee.meeting_duration_in_minutes = form.meeting_duration_in_minutes.data
        aycommittee.supplemental_minutes_per_frequency = form.supplemental_minutes_per_frequency.data
        db.session.commit()
        return jsonify(success=True, message="Commitment hours updated")
    return jsonify(success=False, error=form.errors)

@bp.route('/delete_ay_committee/<int:ay_committee_id>')
@permission_required('ay_committee+delete')
def delete_ay_committee(ay_committee_id):
    try:
        ay_committee = AYCommittee.query.filter_by(id=ay_committee_id, deleted=False).first_or_404()        
        ay_committee.deleted = True
        ay_committee.delete_date = datetime.now()
        db.session.commit()
        flash("Committee deleted.", "success")
        return redirect(url_for('committee.ay_committees'))
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
        # db.session.delete(ftype)
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
        # db.session.delete(ctype)
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
            # flash("Cannot delete this member role because it is currently assigned to one or more members.", "danger")
            # return redirect(url_for('committee.member_roles'))
            return jsonify({"success": False, "message": "Cannot delete this member role because it is currently assigned to one or more members."})
            return render_template('committee_tracker/member_roles.html', form=form, roles = mroles)
        
        role.deleted = True
        role.delete_date = datetime.now()
        # db.session.delete(role)
        db.session.commit()

        return jsonify({"success": True, "deleted_role_id": role_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

# List Members    
@bp.route('/<int:ay_committee_id>/members/', methods=['GET'])
@permission_required("ay_committee+add,ay_committee+edit,ay_committee+view")
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
            with_loader_criteria(Member, lambda m: m.deleted == False),
            with_loader_criteria(FileUpload, lambda f: f.deleted == False),
            with_loader_criteria(Meeting, lambda m: m.deleted == False),
        ).first() if ay_committee_id else AYCommittee()
    
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

    return render_template('committee_tracker/members.html', aycommitteeForm=aycommitteeForm, memberForm=memberForm, meetingForm=meetingForm, 
                           uploadForm=uploadForm, aycommittee=aycommittee)

@bp.route('/add_member', methods=['POST'])
@permission_required("member+add, member+edit")
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
            notes=form.notes.data
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
@permission_required("member+add, member+edit")
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
            db.session.commit()
            member.user = Employee.query.filter_by(employee_id=member.employee_id).first()
            member.member_role = MemberRole.query.filter_by(id=member.member_role_id, deleted=False).first()
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
@permission_required("member+delete")
def delete_member(member_id:int):
        
    try:
        member = Member.query.filter_by(id=member_id, deleted=False).first()
        user = Employee.query.filter_by(employee_id=member.employee_id).first()
        form = MemberForm()
        if member:
            # db.session.delete(member)
            member.notes = form.notes.data
            member.deleted = True
            member.delete_date = datetime.now()
            
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

@permission_required("member+add, member+edit")
def add_member_as_user(employee_id=None):
    user = User.query.filter_by(employee_id=employee_id, deleted=False).first() or User()
    role = Role.query.filter_by(name="Committee Viewer", deleted=False).first()
    
    if not user.id:
        employee = Employee.query.filter_by(employee_id=employee_id).first()
        user.role_id = role.id
        user.username = employee.username
        user.employee_id = employee.employee_id
        db.session.add(user)
        db.session.commit()
        # return user
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
            db.session.add(user)
            db.session.commit()
    return user

@permission_required("member+add, member+edit")
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@permission_required("document+add, document+edit")
@bp.route("/upload", methods=["POST"])
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

        try:
            db.session.add(new_file)
            db.session.commit()            
        except Exception as e:
            return f"ERROR:{e}"
        
    return jsonify({"success": "Files uploaded successfully", "files": saved_files})

@bp.route("/<int:ay_committee_id>/uploaded_files", methods=["GET"])
@permission_required("document+view, document+add, document+edit, document+delete")
def uploaded_files(ay_committee_id:int):
    allfiles = FileUpload.query.filter_by(ay_committee_id=ay_committee_id, deleted=False).all()
    files = [{"ay_committee_id": f.ay_committee_id, "name": f.filename, "size": os.path.getsize(os.path.join(UPLOAD_FOLDER, f.filename)), "id": f.id} for f in allfiles]
    # print(files)
    return jsonify({"files": files, "allow_delete": has_permission('document+delete')})

# Delete File
@bp.route('/delete_file/<int:file_id>', methods=['POST'])
@permission_required("document+delete")
def delete_file(file_id:int):
    try:
        doc = FileUpload.query.filter_by(id=file_id, deleted=False).first()
        doc.delete_date = datetime.now()
        doc.deleted = True
        if not doc:
            return jsonify({"success": False, "message": "File not found"})
        db.session.commit()

        return jsonify({"success": True, "message": doc.filename+" successfully deleted."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

@permission_required("meeting+view, meeting+add, meeting+edit, meeting+delete")
def meetings(ay_committee_id:int):
    allMeetings = Meeting.query.filter_by(ay_committee_id=ay_committee_id, deleted=False).all()
    meetings = [{"title": row.title, "date": row.data, "location": row.location, \
                "notes": row.notes, "id": row.id} for row in allMeetings]
    return jsonify({"meetings": meetings})

@bp.route("/save_meeting", methods=["POST"])
@permission_required("meeting+add, meeting+edit")
def save_meeting():
    form = MeetingForm()
    meeting_id = request.form["meeting_id"]
    # print(meeting_id)
    if form.validate():
        if meeting_id:
            meeting = Meeting.query.filter_by(id=meeting_id, deleted=False).first()
            if not meeting:
                return jsonify({"error": "Meeting not found"}), 404
        else:
            meeting = Meeting()

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
@permission_required("meeting+delete")
def delete_meeting(meeting_id:int):
    try:
        meeting = Meeting.query.filter_by(id=meeting_id, deleted=False).first()
        ay_committee_id = meeting.ay_committee_id

        if not meeting:
            return jsonify({"error": "Meeting not found"}), 404

        meeting.delete_date = datetime.now()
        meeting.deleted = True
        db.session.commit()

        return jsonify({"success": True, "meetings": get_meetings_json(ay_committee_id)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

@permission_required("meeting+add, meeting+edit")
@bp.route("/save_attendance", methods=["POST"])
def save_attendance():
    try:
        meeting_id = request.form.get("meeting_id")
        meeting = Meeting.query.get_or_404(meeting_id)

        if not meeting_id:
            print("No meeting specified.")
            flash("No meeting specified.", "danger")
            return redirect(request.referrer)

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
                else:
                    # Create new record
                    new_attendance = Attendance(
                        meeting_id=meeting_id,
                        member_id=member_id,
                        status=status if status else None
                    )
                    db.session.add(new_attendance)

        db.session.commit()
        return jsonify({"success": True, "meetings": get_meetings_json(meeting.ay_committee_id)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

@permission_required("meeting+view, meeting+add, meeting+edit, meeting+delete")
@bp.route("/<int:ay_committee_id>/meetings/json")
def meetings_json(ay_committee_id: int):
    print("meetings_json",jsonify(get_meetings_json(ay_committee_id)))
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
            "title": m.title,
            "date": m.date.strftime("%Y-%m-%d"),
            "location": m.location or "",
            "notes": m.notes or "",
            "attendance": member_statuses
        })
    return data

@bp.route("/<int:ay_committee_id>/meeting/<int:meeting_id>/attendance/json")
@permission_required("meeting+view")
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