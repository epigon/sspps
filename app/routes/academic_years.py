from app.utils import admin_required, permission_required, has_permission
from app.models import db, AcademicYear, AYCommittee, Committee, Member, MemberRole, FrequencyType, CommitteeType, Employee, Meeting, FileUpload, MemberType, User, Role, Permission
from app.forms import AcademicYearForm, AYCommitteeForm, CommitteeForm, CommitteeReportForm, MemberForm, MemberRoleForm, MemberTypeForm, MeetingForm, FileUploadForm, FrequencyTypeForm, CommitteeTypeForm
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, jsonify, Blueprint, send_file, abort, make_response
from flask_login import login_required, current_user
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

bp = Blueprint('academic_years', __name__, url_prefix='/academic_years')

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

def get_academic_years():
    ayears = AcademicYear.query.filter_by(deleted=False).order_by(AcademicYear.year.desc()).all()
    return ayears

# List Academic Year
@bp.route('/', methods=['GET'])
@permission_required('academic_year+view, academic_year+add, academic_year+edit, academic_year+delete')
def list():
    form = AcademicYearForm()
    ayears = get_academic_years()
    ayears_data = [{"id": ay.id, "year": ay.year, "is_current": ay.is_current} for ay in ayears]
    return render_template('academic_years/list_academic_years.html', form=form, ayears = ayears_data)

# Edit Academic Year
@bp.route("/new/", methods=["POST", "GET"])
@bp.route("/<int:academic_year_id>/", methods=["POST", "GET"])
@permission_required('academic_year+add, academic_year+edit')
def edit_academic_year(academic_year_id:int=None):
    ayears = get_academic_years()
    academic_year = AcademicYear.query.filter_by(id=academic_year_id, deleted=False).first() if academic_year_id else AcademicYear()
    form = AcademicYearForm()
    if request.method == "POST":
        academic_year.year = request.form['year']
        if academic_year_id:
            academic_year.modify_date = datetime.now()
            academic_year.modify_by =  current_user.id
        else:
            academic_year.create_date = datetime.now()
            academic_year.create_by =  current_user.id
        try:
            db.session.add(academic_year)
            db.session.commit()
            return jsonify(success=True, academic_year={
                "id": academic_year.id,
                "year": academic_year.year,
                "is_current": academic_year.is_current 
            })
        except IntegrityError as err:
            db.session.rollback()
            err_msg = err.args[0]
            if "UNIQUE KEY constraint" in err_msg:
                return jsonify(success=False, message="Academic Year already exists (%s)" % form.year.data)
            else:
                return jsonify(success=False, message="unknown error adding academic year.")
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": str(e)})
    return render_template('academic_years/list_academic_years.html', form=form, ayears = ayears)

# Delete Academic Year
@bp.route('/<int:academic_year_id>', methods=['DELETE'])
@permission_required('academic_year+delete')
def delete_academic_year(academic_year_id):
    try:
        academic_year = AcademicYear.query.filter_by(id=academic_year_id, deleted=False).first()
        # Check if any committees are assigned to this ay
        assigned_committees = AYCommittee.query.filter_by(academic_year_id=academic_year.id, deleted=False).count()
        
        if assigned_committees > 0:
            return jsonify({"success": False, "message": "Cannot delete this academic year because it is currently assigned to one or more committees."})
        
        if not academic_year:
            return jsonify({"success": False, "message": "Academic Year not found"})
        
        academic_year.deleted = True
        academic_year.delete_date = datetime.now()
        academic_year.delete_by = current_user.id

        db.session.commit()

        return jsonify({"success": True, "deleted_academic_year_id": academic_year_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

@bp.route('/<int:ay_id>/set_current', methods=['POST'])
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
        ay.modify_date = datetime.now()
        ay.modify_by =  current_user.id
        
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=str(e))
    