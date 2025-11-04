from app.forms import StudentForm, CSRFOnlyForm
from app.models import db, Employee
from app.utils import permission_required
from .canvas import get_enrollment_terms, get_canvas_courses, get_canvas_users, get_enrollments, get_canvas_courses_by_term, get_terms_with_courses
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, jsonify, Blueprint, send_file, abort, make_response, Response
from flask_login import login_required, current_user
from io import BytesIO
from PIL import UnidentifiedImageError
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Image, Spacer, Table, TableStyle, Paragraph
from werkzeug.utils import secure_filename
import chardet
import os
import pandas as pd

bp = Blueprint('employees', __name__, url_prefix='/employees')

UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

PHOTO_UPLOAD_FOLDER = os.path.join('app', 'static', 'photos')
if not os.path.exists(PHOTO_UPLOAD_FOLDER):
    os.makedirs(PHOTO_UPLOAD_FOLDER)

ALLOWED_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# TEMPLATE_COLUMNS = [
#     'pid', 'username', 'email', 'first_name', 'last_name',
#     'middle_name', 'suffix', 'pronoun', 'loa',
#     'phonetic_first_name', 'phonetic_last_name',
#     'lived_first_name', 'lived_last_name',
#     'class_of', 'photo_url'
# ]

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

@bp.route('/enroll')
@permission_required('canvas_enrollments+add')
def enroll_employees():
    # selected_department = request.args.get('department', '')
    terms = get_enrollment_terms()
    terms_with_courses = get_terms_with_courses()

    for term in terms_with_courses:
        term['id'] = str(term['id'])
        for course in term.get('courses', []):
            course['id'] = str(course['id'])
            course['course_code'] = course.get('course_code') or ""

    # if selected_department:
    #     employees = Employee.query.filter_by(department=selected_department, deleted=False)
    # else:
    # employees = Employee.query.filter_by(deleted=False)

    # employees = Employee.query.order_by(Employee.employee_last_name, Employee.employee_first_name).all()
    employees = get_canvas_users(account="SSPPS")
    print(employees)
    # departments = db.session.query(Employee.department).distinct().filter(Employee.department != '').all()

    return render_template(
        'employees/canvas_enroll.html',
        employees=employees,
        # departments=[d[0] for d in departments],
        # selected_department=selected_department,
        terms=terms,
        terms_with_courses=terms_with_courses
    )
