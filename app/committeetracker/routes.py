from app.utils import admin_required, permission_required
from app.models import db, AcademicYear, AYCommittee, Committee, Member, MemberRole, FrequencyType, CommitteeType, Employee, Meeting, FileUpload, MemberTask, MemberType
from app.forms import AcademicYearForm, AYCommitteeForm, CommitteeForm, CommitteeReportForm, MemberForm, MemberRoleForm, MemberTaskForm, MemberTypeForm, MeetingForm, FileUploadForm, FrequencyTypeForm, CommitteeTypeForm
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, jsonify, Blueprint, send_file, abort, make_response
from flask_login import login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload, with_loader_criteria
from sqlalchemy.sql import func
from urllib.parse import urljoin, urlparse, parse_qs
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa
import io
import os
import pandas as pd
import re
import sys
import traceback

committee_bp = Blueprint('committee', __name__, url_prefix='/committeetracker')

# Allow presentations, documents, images, and PDFs
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "pages", "numbers", "key",
    "ppt", "pptx",  # PowerPoint
    "jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"
}

UPLOAD_FOLDER = 'app/static/uploads/'

# Routes to Webpages
@committee_bp.before_request
@login_required
def before_request():
    pass

@committee_bp.route('/dashboard')
@committee_bp.route('/base_committees')
@permission_required('committee+view, committee+add, committee+edit, committee+delete')
def base_committees():    
    form = CommitteeForm()
    base_committees = Committee.query.filter_by(deleted=False).order_by(Committee.name).all()

    return render_template('committeetracker/base_committees.html', form = form, committees=base_committees)

# Add/Edit a Committee
@committee_bp.route('/base_committee/new', methods=['GET', 'POST'])
@committee_bp.route('/base_committee/<int:committee_id>/edit', methods=['GET', 'POST'])
@permission_required('committee+add, committee+edit')
# @committee_bp.route('/base_committee/', methods=['GET','POST'])
def edit_committee(committee_id:int=None):
    committee = Committee.query.filter_by(id=committee_id, deleted=False).first() if committee_id else Committee()
    form = CommitteeForm(original_name=committee.name if committee.id else None, obj=committee)
    form.frequency_type_id.choices = []
    form.committee_type_id.choices = []
    for row in get_frequency_types():
        form.frequency_type_id.choices.append([row.id, row.type])
    for row in get_committee_types():
        form.committee_type_id.choices.append([row.id, row.type])

    if form.validate_on_submit():
        committee.name = form.name.data
        committee.short_name=form.short_name.data
        committee.description=form.description.data
        committee.reporting_start=form.reporting_start.data
        committee.mission = form.mission.data
        committee.frequency_type_id=form.frequency_type_id.data
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
                return render_template('committeetracker/edit_base_committee.html', form=form)
            else:
                flash("ERROR: (%s)" % err_msg, 'danger')
                return render_template('committeetracker/edit_base_committee.html', form=form)

    return render_template('committeetracker/edit_base_committee.html', form=form, committee=committee)

@committee_bp.route('/base_committee/<int:committee_id>/delete')
@permission_required('committee+delete')
def delete_base(committee_id):
    committee = Committee.query.filter_by(id=committee_id, deleted=False).first_or_404()
    # # Check if any AYCommittee are assigned to this role
    # assigned_ay = AYCommittee.query.filter_by(committee_id=committee.id, deleted=False).count()
 
    # if assigned_ay > 0:
    #     flash("Cannot delete this committee because it is currently assigned to one or more academic years.", "danger")
    #     return redirect(url_for('committee.base_committees'))

    try:
        committee.deleted = True
        committee.delete_date = datetime.now()
        # db.session.delete(committee)
        db.session.commit()
        flash("Committee deleted.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Cannot delete this committee because it is currently assigned to one or more years.", "danger")
    return redirect(url_for('committee.base_committees'))

@committee_bp.route('/ay_committees/')
@committee_bp.route('<int:academic_year_id>/ay_committees/')
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

    return render_template('committeetracker/ay_committees.html', ay_committees=current_ay_committees, current_year = current_year, academic_years = academic_years)

# Add a Committee    
@committee_bp.route('/ay_committee/new', methods=['GET','POST'])
@permission_required('ay_committee+add, ay_committee+edit')
def ay_committee():
    form = AYCommitteeForm()
    form.academic_year_id.choices = [(0, 'Select Academic Year')]
    for row in get_academic_years():
        form.academic_year_id.choices.append([row.id, row.year])

    form.committee_id.choices = [(0, 'Select Committee')]
    for row in get_committees():
        short_name = " ("+row.short_name+")" if row.short_name else ""
        form.committee_id.choices.append([row.id, row.name + short_name])

    if form.validate_on_submit():
        new_committee = AYCommittee(
                                academic_year_id=form.academic_year_id.data,
                                committee_id=form.committee_id.data
                                )
        try:
            db.session.add(new_committee)
            db.session.commit()
            flash("New committee has been created!", 'success')   
            return redirect(url_for('committee.members', ay_committee_id = new_committee.id))

        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                # aycom = db.session.query(AYCommittee).filter_by(academic_year_id=form.academic_year_id.data, committee_id=form.committee_id.data).first()
                aycom = AYCommittee.query.filter_by(academic_year_id=form.academic_year_id.data, committee_id=form.committee_id.data, deleted=False).first()
                flash(f"Warning: Committee name already exists {aycom.committee.name} for {aycom.academic_year.year}. \n You can edit it here.", 'warning')
                return redirect(url_for('committee.members', ay_committee_id = aycom.id))
            else:
                flash("ERROR: (%s)" % err_msg, 'danger')
                return render_template('committeetracker/edit_ay_committee.html', form=form)
    
    return render_template('committeetracker/edit_ay_committee.html', form=form)

# List Academic Year
@committee_bp.route('/academic_years', methods=['GET'])
@permission_required('academic_year+view, academic_year+add, academic_year+edit, academic_year+delete')
def academic_years():
    form = AcademicYearForm()
    ayears = get_academic_years()
    ayears_data = [{"id": ay.id, "year": ay.year, "is_current": ay.is_current} for ay in ayears]
    return render_template('committeetracker/academic_years.html', form=form, ayears = ayears_data)

# Add Academic Year
@committee_bp.route('/academic_year', methods=['POST'])
@permission_required('academic_year+add, academic_year+edit')
def add_academic_year():
    form = AcademicYearForm()

    if form.validate_on_submit():
        new_ay = AcademicYear(
            year=form.year.data,
            is_current=False  # or form.is_current.data if you have the field
        )
        db.session.add(new_ay)
        db.session.commit()

        return jsonify(success=True, academic_year={
            "id": new_ay.id,
            "year": new_ay.year,
            "is_current": new_ay.is_current
        })
    else:
        return jsonify(success=False, message="Form validation failed")

# Edit Academic Year
@committee_bp.route("/academic_year/<int:academic_year_id>/", methods=["POST", "GET"])
@permission_required('academic_year+add, academic_year+edit')
def edit_academic_year(academic_year_id:int):
    ayears = get_academic_years()
    # academic_year = db.session.query(AcademicYear).get(academic_year_id)
    academic_year = AcademicYear.query.filter_by(id=academic_year_id, deleted=False).first()
    form = AcademicYearForm()
    if request.method == "POST":
        academic_year.year = request.form['year']
        try:
            db.session.commit()
            return jsonify({"success":True})
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE constraint failed" in err_msg:
                return jsonify(message="Academic Year already exists (%s)" % form.year.data)
            else:
                return jsonify(message="unknown error adding academic year.")
    return render_template('committeetracker/academic_years.html', form=form, academic_year=academic_year, ayears = ayears)

# Delete Academic Year
@committee_bp.route('/academic_year/<int:academic_year_id>', methods=['DELETE'])
@permission_required('academic_year+delete')
def delete_academic_year(academic_year_id):
    try:
        # academic_year = db.session.query(AcademicYear).get(academic_year_id)
        academic_year = AcademicYear.query.filter_by(id=academic_year_id, deleted=False).first()
        # Check if any committees are assigned to this ay
        assigned_committees = AYCommittee.query.filter_by(academic_year_id=academic_year.id, deleted=False).count()
        
        if assigned_committees > 0:
            flash("Cannot delete this academic year because it is currently assigned to one or more committees.", "danger")
            return redirect(url_for('admin.roles'))
        
        if not academic_year:
            return jsonify({"success": False, "message": "Academic Year not found"})
        
        academic_year.deleted = True
        academic_year.delete_date = datetime.now()
        # db.session.delete(academic_year)
        db.session.commit()

        return jsonify({"success": True, "deleted_academic_year_id": academic_year_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

@committee_bp.route('/academic_year/<int:ay_id>/set_current', methods=['POST'])
@permission_required("academic_year+add, academic_year+edit")
# @csrf.exempt  # If CSRF is handled manually in AJAX
def set_current_academic_year(ay_id):
    ay = AcademicYear.query.filter_by(id=ay_id, deleted=False).first_or_404()
    is_current = request.form.get('is_current') == 'true'

    try:
        # Optionally unset other current years
        if is_current:
            AcademicYear.query.update({AcademicYear.is_current: False})

        ay.is_current = is_current
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=str(e))
    
# Add/List Frequency Type
@committee_bp.route('/frequency_types', methods=['GET','POST'])
@permission_required("frequency_type+add")
def frequency_types():
    form = FrequencyTypeForm()
    
    if form.validate_on_submit():
        new_ftype = FrequencyType(type=form.type.data)
        try:
            db.session.add(new_ftype)
            db.session.commit()   
            return jsonify({
                'success': True,
                'ftype': {
                    'id': new_ftype.id,
                    'type': new_ftype.type
                }
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE constraint failed" in err_msg:
                return jsonify({"success": False, "message":"Frequency Type already exists (%s)" % form.type.data})
            else:
                return jsonify({"success": False, "message":"unknown error adding frequency type."})
    ftypes = get_frequency_types()
    return render_template('committeetracker/frequency_types.html', form=form, ftypes = ftypes)

# Edit Frequency Type
@committee_bp.route("/frequency_type/<int:frequency_type_id>/", methods=["POST", "GET"])
@permission_required("frequency_type+edit")
def edit_frequency_type(frequency_type_id:int):
    ftypes = get_frequency_types()
    # ftype = db.session.query(FrequencyType).get(frequency_type_id)
    ftype = FrequencyType.query.filter_by(id=frequency_type_id, deleted=False).first()
    form = FrequencyTypeForm()
    if request.method == "POST":
        ftype.type = request.form['type']
        try:
            db.session.commit()
            return jsonify({"success":True})
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE constraint failed" in err_msg:
                return jsonify(message="Frequency Type already exists (%s)" % form.type.data)
            else:
                return jsonify(message="unknown error adding frequency type.")
    return render_template('committeetracker/frequency_types.html', form=form, ftype=ftype, ftypes = ftypes)

# Delete Frequency Type
@committee_bp.route('/frequency_type/<int:frequency_type_id>', methods=['DELETE'])
@permission_required("frequency_type+delete")
def delete_frequency_type(frequency_type_id):
    try:
        # ftype = db.session.query(FrequencyType).get(frequency_type_id)
        ftype = FrequencyType.query.filter_by(id=frequency_type_id, deleted=False).first()
            # Check if any Committee are assigned to this frequency_type
        assigned_com = Committee.query.filter_by(frequency_type_id=ftype.id, deleted=False).count()
    
        if assigned_com > 0:
            flash("Cannot delete this committee because it is currently assigned to one or more academic years.", "danger")
            return redirect(url_for('committee.base_committees'))
        
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
@committee_bp.route('/committee_types', methods=['GET','POST'])
@permission_required("committee_type+add")
def committee_types():
    form = CommitteeTypeForm()
    
    if form.validate_on_submit():
        new_ctype = CommitteeType(type=form.type.data)
        try:
            db.session.add(new_ctype)
            db.session.commit()   
            return jsonify({
                'success': True,
                'ctype': {
                    'id': new_ctype.id,
                    'type': new_ctype.type
                }
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE constraint failed" in err_msg:
                return jsonify({"success": False, "message":"Committee Type already exists (%s)" % form.type.data})
            else:
                return jsonify({"success": False, "message":"unknown error adding committee type."})
    ctypes = get_committee_types()
    return render_template('committeetracker/committee_types.html', form=form, ctypes = ctypes)

# Edit Committee Type
@committee_bp.route("/committee_type/<int:committee_type_id>/", methods=["POST", "GET"])
@permission_required("committee_type+edit")
def edit_committee_type(committee_type_id:int):
    ctypes = get_committee_types()
    # ctype = db.session.query(CommitteeType).get(committee_type_id)
    ctype = CommitteeType.query.filter_by(id=committee_type_id, deleted=False).first()
    form = CommitteeTypeForm()
    if request.method == "POST":
        ctype.type = request.form['type']
        try:
            db.session.commit()
            return jsonify({"success":True})
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE constraint failed" in err_msg:
                return jsonify(message="Committee Type already exists (%s)" % form.type.data)
            else:
                return jsonify(message="unknown error adding committee type.")
    return render_template('committeetracker/committee_types.html', form=form, ctype=ctype, ctypes = ctypes)

# Delete Committee Type
@committee_bp.route('/committee_type/<int:committee_type_id>', methods=['DELETE'])
@permission_required("committee_type+delete")
def delete_committee_type(committee_type_id):
    try:
        # ctype = db.session.query(CommitteeType).get(committee_type_id)
        ctype = CommitteeType.query.filter_by(id=committee_type_id, deleted=False).first()
        if not ctype:
            return jsonify({"success": False, "message": "Committee Type not found"})
        
        ctype.deleted = True
        ctype.delete_date = datetime.now()
        # db.session.delete(ctype)
        db.session.commit()

        return jsonify({"success": True, "deleted_committee_type_id": committee_type_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

# Add/List Member Role
@committee_bp.route('/member_roles', methods=['GET','POST'])
@permission_required("member_role+add")
def member_roles():
    form = MemberRoleForm()
    
    if form.validate_on_submit():
        # functions=form.functions.data, 
        new_role = MemberRole(role=form.role.data, description=form.description.data)
        try:
            db.session.add(new_role)
            db.session.commit()  
            return jsonify({
                'success': True,
                'role': {
                    'id': new_role.id,
                    'role': new_role.role,
                    'description': new_role.description
                }
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE constraint failed" in err_msg:
                return jsonify({"success": False, "message":"Member Role already exists (%s)" % form.role.data})
            else:
                return jsonify({"success": False, "message":"unknown error adding member role."})
    # roles = db.session.query(MemberRole).all()
    roles = MemberRole.query.filter_by(deleted=False).all()
    return render_template('committeetracker/member_roles.html', form=form, roles = roles)

# Edit Member Role
@committee_bp.route("/member_role/<int:role_id>/", methods=["POST", "GET"])
@permission_required("member_role+edit")
def edit_role(role_id:int):
    mroles = get_member_roles()
    # mrole = db.session.query(MemberRole).get(role_id)
    mrole = MemberRole.query.filter_by(id=role_id, deleted=False).first()
    form = MemberRoleForm()
    if request.method == "POST":
        mrole.role = request.form['role']
        mrole.description = request.form['description']
        try:
            db.session.commit()
            return jsonify({"success":True})
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE constraint failed" in err_msg:
                return jsonify(message="Member Role already exists (%s)" % form.role.data)
            else:
                return jsonify(message="unknown error adding member role.")

    return render_template('committeetracker/member_roles.html', form=form, role=mrole, roles = mroles)

# Delete Member Role
@committee_bp.route('/member_role/<int:role_id>', methods=['DELETE'])
@permission_required("member_role+delete")
def delete_role(role_id):
    try:
        # role = db.session.query(MemberRole).get(role_id)
        role = MemberRole.query.filter_by(id=role_id, deleted=False).first()
        if not role:
            return jsonify({"success": False, "message": "Role not found"})
        role.deleted = True
        role.delete_date = datetime.now()
        # db.session.delete(role)
        db.session.commit()

        return jsonify({"success": True, "deleted_role_id": role_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

# List Members    
@committee_bp.route('/<int:ay_committee_id>/members/', methods=['GET'])
@permission_required("ay_committee+add")
def members(ay_committee_id:int):
    memberForm = MemberForm()
    memberForm.ay_committee_id.data = ay_committee_id
    memberForm.employee_id.choices = [(['', 'Select one'])]
    memberForm.member_role_id.choices = [(['', 'Select one'])]
    for row in get_employees():
        memberForm.employee_id.choices.append([row.employee_id, row.employee_last_name+', '+row.employee_first_name])
    for row in get_member_roles():
        memberForm.member_role_id.choices.append([row.id, row.role])
    
    # aycommittee = (
    #     db.session.query(AYCommittee).filter_by(id=ay_committee_id)
    #     .options(joinedload(AYCommittee.members))
    #     .options(joinedload(AYCommittee.fileuploads))
    #     .options(joinedload(AYCommittee.meetings))
    #     .all()
    # )
    aycommittee = (
        AYCommittee.query
        .filter_by(id=ay_committee_id, deleted=False)
        .options(
            joinedload(AYCommittee.members),
            joinedload(AYCommittee.fileuploads),
            joinedload(AYCommittee.meetings),
            with_loader_criteria(Member, lambda m: m.deleted == False),
            with_loader_criteria(FileUpload, lambda f: f.deleted == False),
            with_loader_criteria(Meeting, lambda m: m.deleted == False),
        )
        .all()
    )

    for com in aycommittee:
        for member in com.members:
            # member.user = db.session.query(Employee).filter_by(employee_id=member.employee_id).first()
            # member.member_role = db.session.query(MemberRole).filter_by(id=member.member_role_id, deleted=False).first()
            member.user = Employee.query.filter_by(employee_id=member.employee_id).first()
            member.member_role = MemberRole.query.filter_by(id=member.member_role_id, deleted=False).first()

    meetingForm = MeetingForm(ay_committee_id=ay_committee_id)
    uploadForm = FileUploadForm(ay_committee_id=ay_committee_id)
    return render_template('committeetracker/members.html', memberForm = memberForm, meetingForm = meetingForm, uploadForm = uploadForm, aycommittee = aycommittee)

@committee_bp.route('/add_member', methods=['POST'])
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
            # new_member.user = db.session.query(Employee).filter_by(employee_id=new_member.employee_id).first()
            # new_member.member_role = db.session.query(MemberRole).filter_by(id=new_member.member_role_id).first()
            new_member.user = Employee.query.filter_by(employee_id=new_member.employee_id).first()
            new_member.member_role = MemberRole.query.filter_by(id=new_member.member_role_id, deleted=False).first()
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
    
@committee_bp.route('/edit_member/<int:member_id>', methods=['POST'])
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
            # member.user = db.session.query(Employee).filter_by(employee_id=member.employee_id).first()
            # member.member_role = db.session.query(MemberRole).filter_by(id=member.member_role_id).first()
            member.user = Employee.query.filter_by(employee_id=member.employee_id).first()
            member.member_role = MemberRole.query.filter_by(id=member.member_role_id, deleted=False).first()
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

@committee_bp.route('/delete_member/<int:member_id>', methods=['POST'])
@permission_required("member+delete")
def delete_member(member_id:int):
    # member = db.session.query(Member).get(member_id)
    member = Member.query.filter_by(id=member_id, deleted=False).first()
    # user = db.session.query(Employee).filter_by(employee_id=member.employee_id).first()
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

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@permission_required("member+add, member+edit")
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@permission_required("document+add, document+edit")
@committee_bp.route("/upload", methods=["POST"])
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

@committee_bp.route("/<int:ay_committee_id>/uploaded_files", methods=["GET"])
@permission_required("document+view, document+add, document+edit, document+delete")
def uploaded_files(ay_committee_id:int):
    allfiles = FileUpload.query.filter_by(ay_committee_id=ay_committee_id, deleted=False).all()
    files = [{"ay_committee_id": f.ay_committee_id, "name": f.filename, "size": os.path.getsize(os.path.join(UPLOAD_FOLDER, f.filename)), "id": f.id} for f in allfiles]
    # print(files)
    return jsonify({"files": files})

# Delete File
@committee_bp.route('/delete_file/<int:file_id>', methods=['POST'])
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
    meetings = [{"title": row.title, "date": row.data, "start_time": row.start_time, "end_time": row.end_time, "location": row.location, \
                "notes": row.notes, "id": row.id} for row in allMeetings]
    return jsonify({"meetings": meetings})

@committee_bp.route("/save_meeting", methods=["POST"])
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
        meeting.start_time = request.form["start_time"]
        meeting.end_time = request.form["end_time"]
        meeting.location = request.form["location"]
        meeting.notes = request.form["notes"]

        db.session.add(meeting)
        db.session.commit()

        # allMeetings = db.session.query(Meeting).filter_by(ay_committee_id=meeting.ay_committee_id).all()
        allMeetings = Meeting.query.filter_by(ay_committee_id=meeting.ay_committee_id, deleted=False).all()
        meetings = [{"title": row.title, "date": row.date.strftime('%Y-%m-%d'), "start_time": row.start_time.strftime('%H:%M'), "end_time": row.end_time.strftime('%H:%M'), "location": row.location, \
                "notes": row.notes, "id": row.id} for row in allMeetings]
        return jsonify({"meetings": meetings})
    else:
        print("error")
        return jsonify({"error": "Invalid data"}), 400

@committee_bp.route("/delete_meeting", methods=["POST"])
@permission_required("meeting+delete")
def delete_meeting():
    data = request.json
    meeting_id = data.get("meeting_id")
    # meeting = db.session.query(Meeting).get(meeting_id)
    meeting = Meeting.query.filter_by(id=meeting_id, deleted=False).first()

    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    meeting.delete_date = datetime.now()
    meeting.deleted = True
    # db.session.delete(meeting)
    db.session.commit()

    return jsonify({"success": True})

@permission_required("academic_year+view, academic_year+add, academic_year+edit, academic_year+delete")
def get_academic_years():
    # ayears = db.session.query(AcademicYear).order_by(AcademicYear.year.desc()).all()
    ayears = AcademicYear.query.filter_by(deleted=False).order_by(AcademicYear.year.desc()).all()
    return ayears

@permission_required("frequency_type+view, frequency_type+add, frequency_type+edit, frequency_type+delete")
def get_frequency_types():
    ftypes = FrequencyType.query.filter_by(deleted=False).order_by(FrequencyType.type).all()
    return ftypes

@permission_required("committee_type+view, committee_type+add, committee_type+edit, committee_type+delete")
def get_committee_types():
    ctypes = CommitteeType.query.filter_by(deleted=False).order_by(CommitteeType.type).all()
    return ctypes

@permission_required("member_role+view, member_role+add, member_role+edit, member_role+delete")
def get_member_roles():
    mroles = MemberRole.query.filter_by(deleted=False).order_by(MemberRole.role).all()
    return mroles

@committee_bp.route("/get_all_committees", methods=["GET"])
@permission_required("committee_report+view")
def get_all_committees():

    # show_mission = request.args.get("mission", type=int)
    # show_members = request.args.get("members", type=int)    
    # show_meetings = request.args.get("meetings", type=int)
    # show_documents = request.args.get("documents", type=int)

    # sort_by_role = request.args.get("sortRole", type=int)

    query = AYCommittee.query.options(
        selectinload(AYCommittee.academic_year),
        selectinload(AYCommittee.committee).joinedload(Committee.committee_type),
        selectinload(AYCommittee.members).joinedload(Member.employee),
        selectinload(AYCommittee.members).joinedload(Member.member_role),
        selectinload(AYCommittee.meetings),
        selectinload(AYCommittee.fileuploads),
        with_loader_criteria(Member, lambda m: m.deleted == False),
        with_loader_criteria(Meeting, lambda m: m.deleted == False),
        with_loader_criteria(FileUpload, lambda f: f.deleted == False),
        with_loader_criteria(AcademicYear, lambda ay: ay.deleted == False),
        with_loader_criteria(CommitteeType, lambda ct: ct.deleted == False),
    ).filter(AYCommittee.deleted == False)

    # Explicitly join and filter academic_year and committee to ensure it's not None
    query = query.join(AYCommittee.academic_year).filter(AcademicYear.deleted == False)
    query = query.join(AYCommittee.committee).filter(Committee.deleted == False)
    query = query.join(Committee.committee_type).filter(CommitteeType.deleted == False)

    # Apply filters only if the lists are not empty
    filter_user = request.args.get("users", "")
    if filter_user != "0":
        query = query.filter(Member.employee_id == int(filter_user))

    filter_year_ids = request.args.get("years", "")
    if filter_year_ids != "0":
        year_ids = [int(y) for y in filter_year_ids.split(",")]
        query = query.filter(AYCommittee.academic_year_id.in_(year_ids))
    
    filter_committees = request.args.get("committees", "")
    if filter_committees != "0":
        committee_ids = [int(c) for c in filter_committees.split(",")]
        query = query.filter(AYCommittee.committee_id.in_(committee_ids))

    filter_types = request.args.get("types")
    if filter_types and filter_types != "0":
        type_ids = [int(t) for t in filter_types.split(",")]
        query = query.join(AYCommittee.committee).filter(Committee.committee_type_id.in_(type_ids))

    # Fetch results    
    aycommittees = query.all()

    # Sort members by role default_order
    for committee in aycommittees:
            committee.members.sort(key=lambda m: m.member_role.default_order if m.member_role else "")

    # if sort_by_role: # Sort members by role default_order
    #     for committee in aycommittees:
    #         committee.members.sort(key=lambda m: m.member_role.default_order if m.member_role else "")
    # else: # Sort members by name
    #     for committee in aycommittees:
    #         committee.members.sort(key=lambda m: m.employee.employee_name)

    # Build results
    committees = []
    for com in aycommittees:
        committee_data = {
            "academic_year": com.academic_year.year,
            "id": com.id,
            "name": com.committee.name + (f" ({com.committee.short_name})" if com.committee.short_name else ""),
            "mission": com.committee.mission,
            "members": [
                f"{member.employee.employee_name} ({member.member_role.role}) ({member.employee.job_code_description})"
                for member in com.members
            ],
            "meetings": [
                f"{meeting.title} ({meeting.date.strftime('%Y-%m-%d')})"
                for meeting in com.meetings
            ],
            "documents": [doc.filename for doc in com.fileuploads],
        }
        committees.append(committee_data)

    return jsonify(committees)

    results = []
    committees = []
    for com in aycommittees:
        committee_data = {
            "academic_year": com.academic_year.year,
            "id": com.id,
            "name": com.committee.name + ( " (" + com.committee.short_name + ") " if com.committee.short_name else "" )
        }
        committee_data["mission"] = com.committee.mission
        committee_data["members"] = [member.employee.employee_name+"("+member.member_role.role+")"+"("+member.employee.job_code_description+")" for member in com.members]
        committee_data["meetings"] = [meeting.title+" ("+meeting.date.strftime('%Y-%m-%d')+")" for meeting in com.meetings]
        committee_data["documents"] = [doc.filename for doc in com.fileuploads]
        # if show_mission:
        #     committee_data["mission"] = com.committee.mission
        # if show_members:
        #     committee_data["members"] = [member.employee.employee_name+"("+member.member_role.role+")"+"("+member.employee.job_code_description+")" for member in com.members]
        # if show_meetings:
        #     committee_data["meetings"] = [meeting.title+" ("+meeting.date.strftime('%Y-%m-%d')+")" for meeting in com.meetings]
        # if show_documents:
        #     committee_data["documents"] = [doc.filename for doc in com.fileuploads]
            
        committees.append(committee_data)
    results.append(committees)

    return jsonify(results)

@committee_bp.route("/get_committees_by_member", methods=["GET"])
@permission_required("committee_report+view")
def get_committees_by_member():

    query = Member.query.join(Member.ay_committee)\
                .join(AYCommittee.committee)\
                .join(AYCommittee.academic_year)\
                .join(Committee.committee_type)
    query = query.filter(
        Member.deleted == False,
        AYCommittee.deleted == False,
        Committee.deleted == False,
        CommitteeType.deleted == False,
        AcademicYear.deleted == False
    )

    # Filter by employee_id if provided
    filter_user = request.args.get("users", "")
    if filter_user and filter_user != "0":
        query = query.filter(Member.employee_id == int(filter_user))

    # Filter by academic_year_ids if provided
    filter_year_ids = request.args.get("years", "")
    if filter_year_ids and filter_year_ids != "0":
        year_ids = [int(y) for y in filter_year_ids.split(",")]
        query = query.filter(AYCommittee.academic_year_id.in_(year_ids))

    # Filter by committee_ids if provided
    filter_committee_ids = request.args.get("committees", "")
    if filter_committee_ids and filter_committee_ids != "0":
        committee_ids = [int(c) for c in filter_committee_ids.split(",")]
        query = query.filter(AYCommittee.committee_id.in_(committee_ids))

    # Filter by committee_type_ids if provided
    filter_committee_type = request.args.get("types", "")
    if filter_committee_type != "0":
        query = query.filter(Committee.committee_type_id == int(filter_committee_type))

    # Fetch results
    members = query.all()

    member_data = defaultdict(lambda: {
        "employee_id": None,
        "first_name": None,
        "last_name": None,
        "job_code": None,
        "years": set(),
        "committees": defaultdict(lambda: {"id": "", "name": "", "short_name": "", "roles": {}})
    })

    for row in members:
        employee_id = row.employee_id
        role = row.member_role.role
        first_name = row.employee.employee_first_name
        last_name = row.employee.employee_last_name
        job_code = row.employee.job_code_description
        committee = row.ay_committee.committee
        academic_year = row.ay_committee.academic_year.year

        member = member_data[employee_id]
        member["employee_id"] = employee_id
        member["first_name"] = first_name
        member["last_name"] = last_name
        member["job_code"] = job_code
        member["years"].add(academic_year)
    
        committee_data = member["committees"][committee.id]
        committee_data["id"] = committee.id
        committee_data["name"] = committee.name
        committee_data["short_name"] = committee.short_name    
        committee_data["roles"][academic_year] = role

    # Finalize JSON structure
    results = []
    for member in member_data.values():
        results.append({
            "employee_id": member["employee_id"],
            "first_name": member["first_name"],
            "last_name": member["last_name"],
            "job_code": member["job_code"],
            "years": sorted(member["years"]),
            "committees": list(member["committees"].values())
        })
    
    # Sort by last_name (case-insensitive)
    results.sort(key=lambda x: x["last_name"].lower())

    return results

@committee_bp.route("/get_committees_by_assignment", methods=["GET"])
@permission_required("committee_report+view")
def get_committees_by_assignment():

    query = Member.query.join(Member.ay_committee)\
                .join(AYCommittee.committee)\
                .join(AYCommittee.academic_year)\
                .join(Committee.committee_type)
    query = query.filter(
        Member.deleted == False,
        AYCommittee.deleted == False,
        Committee.deleted == False,
        CommitteeType.deleted == False,
        AcademicYear.deleted == False
    )

    # Apply filters only if the lists are not empty
    filter_user = request.args.get("users", "")
    if filter_user != "0":
        query = query.filter(Member.employee_id == int(filter_user))

    filter_year_ids = request.args.get("years", "")
    if filter_year_ids != "0":
        year_ids = [int(y) for y in filter_year_ids.split(",")]
        query = query.filter(AYCommittee.academic_year_id.in_(year_ids))
    
    filter_committees = request.args.get("committees", "")
    if filter_committees != "0":
        committee_ids = [int(c) for c in filter_committees.split(",")]
        query = query.filter(AYCommittee.committee_id.in_(committee_ids))

    filter_committee_type = request.args.get("types", "")
    if filter_committee_type != "0":
        query = query.filter(Committee.committee_type_id == int(filter_committee_type))

    # Fetch results
    members = query.all()

    committee_data = defaultdict(lambda: {
        "committee_id": None,
        "name": None,
        "short_name": None,
        "description": None,
        "mission": None,
        "reporting_start": None,
        "committee_type": None,
        "frequency_type": None,
        "years": set(),
        "members": defaultdict(lambda: {"employee_id": "", "first_name": "", "last_name": "", "job_code" : "", "roles": {}})
    })

    for mem in members:
        com = mem.ay_committee
        committee = com.committee
        year = com.academic_year

        cdata = committee_data[committee.id]
        cdata["committee_id"] = committee.id
        cdata["name"] = committee.name
        cdata["short_name"] = committee.short_name or ""
        cdata["description"] = committee.description or ""
        cdata["mission"] = committee.mission or ""
        cdata["committee_type"] = committee.committee_type.type if committee.committee_type_id else ""
        cdata["years"].add(year.year)

        emp = mem.employee
        mrole = mem.member_role.role

        member = cdata["members"][emp.employee_id]
        member["employee_id"] = emp.employee_id
        member["first_name"] = emp.employee_first_name
        member["last_name"] = emp.employee_last_name
        member["job_code"] = emp.job_code_description
        member["roles"][year.year] = mrole

    # Finalize JSON structure
    results = []
    for committee in committee_data.values():
        results.append({
            "committee_id": committee["committee_id"],
            "name": committee["name"],
            "short_name": committee["short_name"],
            "description": committee["description"],
            "mission": committee["mission"],
            "reporting_start": committee["reporting_start"],
            "committee_type": committee["committee_type"],
            "frequency_type": committee["frequency_type"],
            "years": sorted(committee["years"]),
            "members": list(committee["members"].values())
        })
    
    # Sort by name (case-insensitive)
    results.sort(key=lambda x: x["name"].lower())
    
    return results

@committee_bp.route('/generate_pdf', methods=['POST'])
@permission_required("committee_report+view")
def generate_pdf():
    html_content = request.form.get('html_data')

    # Check if html_content is None and return an error
    if not html_content:
        return "Error: No HTML data received", 400

    pdf_file = convert_html_to_pdf(html_content)
    if pdf_file:
        return send_file(pdf_file, download_name=request.form.get('filename')+".pdf", as_attachment=True)
    return "Error generating PDF", 500

@permission_required("committee_report+view")
def convert_html_to_pdf(html_content):
    """Converts HTML content to a PDF file in memory."""
    pdf_file = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.BytesIO(html_content.encode("utf-8")), pdf_file)

    if pisa_status.err:
        return None
    pdf_file.seek(0)
    return pdf_file

# @permission_required("committees+view, committees+add, committees+edit, committees+delete")
def get_committees():
    data = Committee.query.filter_by(deleted=False).order_by(Committee.name).all()
    return data

# @permission_required("member+view, member+add, member+edit, member+delete")
def get_employees():
    data = Employee.query.order_by(Employee.employee_last_name,Employee.employee_first_name).all()
    return data

@committee_bp.route('/report_all_committees/')
@permission_required("committee_report+view")
def report_all_committees():
    form=CommitteeReportForm()

    form.academic_year.choices = [[0, "All"]]
    for row in get_academic_years():
        form.academic_year.choices.append([row.id, row.year])   

    form.committee.choices = [[0, "All"]]
    for row in get_committees():
        form.committee.choices.append([row.id, row.name]) 
    
    form.committee_type.choices = [[0, "All"]]
    for row in get_committee_types():
        form.committee_type.choices.append([row.id, row.type]) 
    
    form.users.choices = [[0, "All"]]
    for row in get_employees():
        form.users.choices.append([row.employee_id, row.employee_last_name+', '+row.employee_first_name])

    return render_template('committeetracker/report_all_committees.html', form=form)

@committee_bp.route('/member_report/')
@permission_required("committee_report+view")
def member_report():
    form=CommitteeReportForm()

    form.academic_year.choices = [[0, "All"]]
    for row in get_academic_years():
        form.academic_year.choices.append([row.id, row.year])   

    form.committee.choices = [[0, "All"]]
    for row in get_committees():
        form.committee.choices.append([row.id, row.name]) 
    
    form.committee_type.choices = [[0, "All"]]
    for row in get_committee_types():
        form.committee_type.choices.append([row.id, row.type]) 
        
    form.users.choices = [[0, "All"]]
    for row in get_employees():
        form.users.choices.append([row.employee_id, row.employee_last_name+', '+row.employee_first_name])

    return render_template('committeetracker/report_by_member.html', form=form)

@committee_bp.route('/assignment_report/')
@permission_required("committee_report+view")
def assignment_report():
    form=CommitteeReportForm()

    form.academic_year.choices = [[0, "All"]]
    for row in get_academic_years():
        form.academic_year.choices.append([row.id, row.year])   

    form.committee.choices = [[0, "All"]]
    for row in get_committees():
        form.committee.choices.append([row.id, row.name]) 

    form.committee_type.choices = [[0, "All"]]
    for row in get_committee_types():
        form.committee_type.choices.append([row.id, row.type]) 
    
    form.users.choices = [[0, "All"]]
    for row in get_employees():
        form.users.choices.append([row.employee_id, row.employee_last_name+', '+row.employee_first_name])

    return render_template('committeetracker/report_by_assignment.html', form=form)