from app.forms import StudentForm, CSRFOnlyForm
from app.models import db, Student
from app.utils import permission_required
from .canvas import get_enrollment_terms, get_canvas_courses, get_enrollments, get_canvas_courses_by_term, get_terms_with_courses
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

bp = Blueprint('students', __name__, url_prefix='/students')

UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

PHOTO_UPLOAD_FOLDER = os.path.join('app', 'static', 'photos')
if not os.path.exists(PHOTO_UPLOAD_FOLDER):
    os.makedirs(PHOTO_UPLOAD_FOLDER)

ALLOWED_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg'}

TEMPLATE_COLUMNS = [
    'pid', 'username', 'email', 'first_name', 'last_name',
    'middle_name', 'suffix', 'pronoun', 'loa',
    'phonetic_first_name', 'phonetic_last_name',
    'lived_first_name', 'lived_last_name',
    'class_of', 'photo_url'
]

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

@bp.route('/uploadform')
@permission_required('students+add, students+edit')
def upload_form():
    custom_breadcrumbs = [
        {'name': 'Students', 'url': '/students/'},
        {'name': 'Upload Form', 'url': '/students/uploadform'}
    ]
    return render_template('students/upload.html',breadcrumbs=custom_breadcrumbs)

@bp.route('/template')
@permission_required('students+add, students+edit')
def download_template():
    # Create empty DataFrame with header only
    df = pd.DataFrame(columns=TEMPLATE_COLUMNS)

    # Convert to CSV string
    csv_data = df.to_csv(index=False)

    # Return as downloadable file
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename=student_template.csv'
        }
    )

def safe_str(value, max_len=None):
    """Converts NaN or non-string to empty string, optionally truncates."""
    if pd.isna(value):
        return ''
    s = str(value).strip()
    return s[:max_len] if max_len else s

@bp.route('/upload', methods=['POST'])
@permission_required('students+add, students+edit')
def upload_csv():

    file = request.files.get('file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'info')
        return redirect(url_for('students.upload_form'))

    # Collect uploaded photos into a dict
    uploaded_photos = request.files.getlist('photos')
    photo_dict = {photo.filename: photo for photo in uploaded_photos if allowed_photo(photo.filename)}

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    errors = []
    existing_pids = {s.pid for s in Student.query.filter_by(deleted=False).with_entities(Student.pid).all()}
    existing_usernames = {s.username for s in Student.query.filter_by(deleted=False).with_entities(Student.username).all()}
    existing_emails = {s.email for s in Student.query.filter_by(deleted=False).with_entities(Student.email).all()}
    uploaded_pids = set()

    photo_dict = {
        secure_filename(photo.filename): photo
        for photo in uploaded_photos
        if allowed_photo(photo.filename)
    }

    try:
        with open(filepath, 'rb') as f:
            result = chardet.detect(f.read(10000))  # sample first 10KB
            encoding = result['encoding']

        df = pd.read_csv(filepath, encoding=encoding)
        
        required = ['pid', 'username', 'email', 'first_name', 'last_name', 'loa']
        for col in required:
            if col not in df.columns:
                errors.append(f"Missing required column: {col}")
        if errors:
            return render_template('students/upload.html', errors=errors)

        # Replace NaN with empty string only for object (i.e., string) columns
        str_cols = df.select_dtypes(include=['object']).columns
        df[str_cols] = df[str_cols].fillna('')
        df['deleted'] = False
        df['create_date'] = pd.to_datetime('now')
        df['create_by'] = int(current_user.id)

        print(df)

        students = []
        # errors = []
        valid_loa = {'yes', 'no'}

        for i, row in df.iterrows():
            try:
                photo_filename = safe_str(row.get('photo_url'), 50)

                # ✅ Skip row if photo is expected but missing from uploaded files
                if photo_filename and photo_filename not in photo_dict:
                    errors.append(f"Row {i+2}: Photo file '{photo_filename}' is not included in the upload.")
                    continue

                # ✅ Save photo if provided
                if photo_filename:
                    photo_file = photo_dict[photo_filename]
                    photo_path = os.path.join(PHOTO_UPLOAD_FOLDER, photo_filename)
                    photo_file.save(photo_path)

                loa_value = str(row.get('loa', '')).strip().lower()
                if loa_value in valid_loa:
                    loa_bool = loa_value == 'yes'
                else:
                    errors.append(f"Row {i+2}: Invalid 'loa' value '{row.get('loa')}'. Use 'yes' or 'no'.")
                    continue

                pid = safe_str(row.get('pid'), 50)

                # Check for duplicates in DB
                if pid in existing_pids:
                    errors.append(f"Row {i+2}: Duplicate PID '{pid}' already exists in the database.")
                    continue

                # Check for duplicates in current upload
                if pid in uploaded_pids:
                    errors.append(f"Row {i+2}: Duplicate PID '{pid}' appears more than once in this file.")
                    continue

                uploaded_pids.add(pid)

                username = safe_str(row.get('username'), 50)
                email = safe_str(row.get('email'), 255)

                if username in existing_usernames:
                    errors.append(f"Row {i+2}: Username '{username}' already exists.")
                    continue

                if email in existing_emails:
                    errors.append(f"Row {i+2}: Email '{email}' already exists.")
                    continue

                student = Student(
                    pid=safe_str(row['pid'], 50),
                    username=safe_str(row['username'], 50),
                    email=safe_str(row['email'], 255),
                    first_name=safe_str(row['first_name'], 50),
                    last_name=safe_str(row['last_name'], 50),
                    middle_name=safe_str(row.get('middle_name', ''), 50),
                    suffix=safe_str(row.get('suffix', ''), 50),
                    pronoun=safe_str(row.get('pronoun', ''), 50),
                    loa=loa_bool,  # still from "yes"/"no" parsing
                    phonetic_first_name=safe_str(row.get('phonetic_first_name', ''), 50),
                    phonetic_last_name=safe_str(row.get('phonetic_last_name', ''), 50),
                    lived_first_name=safe_str(row.get('lived_first_name', ''), 50),
                    lived_last_name=safe_str(row.get('lived_last_name', ''), 50),
                    class_of=safe_str(row.get('class_of', ''), 50),
                    photo_url=safe_str(photo_filename, 50),
                    create_date=datetime.now(),
                    create_by=int(current_user.id),
                    deleted=False
                )
                students.append(student)

            except Exception as e:
                errors.append(f"Row {i+2}: {str(e)}")

        # ✅ Save only good records
        if students:
            db.session.bulk_save_objects(students)
            db.session.commit()
            flash(f"{len(students)} students uploaded.", 'success')

        # Show errors if any
        if errors:
            flash(f"{len(errors)} row(s) had issues.", 'danger')
            return render_template('students/upload.html', errors=errors)
        else:
            return redirect(url_for('students.upload_form'))

    except Exception as e:
        db.session.rollback()
        flash(f'Upload failed: {str(e)}', 'danger')

    return redirect(url_for('students.upload_form'))

def allowed_photo(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS

@bp.route('/')
@permission_required('students+view, students+add, students+edit, students+delete')
def list_students():
    form = CSRFOnlyForm()
    selected_class = request.args.get('class_of', '')
    selected_term = request.args.get('term', '')
    selected_course = request.args.get('course_id', '')
    # print(selected_course)
    pdf_title = request.args.get('pdf_title', '')  # optional: if you want to preserve it in URL or store elsewhere

    # Get class years for dropdown
    class_years = db.session.query(Student.class_of).distinct().filter(Student.class_of != '').order_by(Student.class_of).all()

    # Fetch terms from Canvas API
    terms = get_enrollment_terms()  # or as appropriate

    terms_with_courses = get_terms_with_courses()  # should return a list of dicts

    # Ensure data is serializable
    for term in terms_with_courses:
        term['id'] = str(term['id'])  # Optional: stringify if needed
        for course in term.get('courses', []):
            course['id'] = str(course['id'])
            course['course_code'] = course.get('course_code') or ""


    # Fetch courses filtered by term if term selected
    if selected_term:
        courses = get_canvas_courses_by_term(selected_term)  # your function to fetch courses by term
    else:
        courses = get_canvas_courses(account="SSPPS")
    
    # Filter students by class_of, course_id, etc.
    students = Student.query  # start query

    if selected_class:
        students = students.filter(Student.class_of == selected_class)

    if selected_course:
        enrollments = get_enrollments(course_id=int(selected_course))        
        enrolled_student_ids = [e['user']['sis_user_id'] for e in enrollments if 'user' in e and 'id' in e['user']]
        students = students.filter(Student.pid.in_(enrolled_student_ids))

    students = students.filter(Student.deleted == False).order_by(Student.last_name, Student.first_name).all()
    
    return render_template('students/list_students.html',
                           students=students,
                           class_years=[c[0] for c in class_years],
                           selected_class=selected_class, 
                           terms_with_courses=terms_with_courses,
                           terms=terms,
                           selected_term=selected_term,
                           courses=courses,
                           selected_course=selected_course,
                           pdf_title=pdf_title,
                           form=form)

@bp.route('/edit/<int:student_id>', methods=['GET', 'POST'])
@permission_required('students+add, students+edit')
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    form = StudentForm(obj=student)

    if form.validate_on_submit():
        student.update_date=datetime.now()
        student.update_by=int(current_user.id)
        form.populate_obj(student)
        
        # Handle photo upload
        file = form.photo_file.data
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(PHOTO_UPLOAD_FOLDER, filename))
            student.photo_url = filename

        db.session.commit()
        flash("Student updated successfully.", 'success')
        return redirect(url_for('students.list_students'))

    return render_template('students/edit_student.html', form=form, student=student)

@permission_required('students+delete')
@bp.route('/<int:student_id>/delete', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.deleted = True
    student.delete_date = datetime.now()
    student.delete_by = current_user.id
    db.session.commit()
    return jsonify({'success': True, 'message': 'Student deleted'})

def add_page_header(canvas, doc, title, header):
    canvas.saveState()
    width, height = LETTER

    # 1) Date on upper-right
    date_str = datetime.now().strftime("%B %d, %Y")
    canvas.setFont("Helvetica", 10)
    canvas.drawRightString(width - doc.rightMargin, height - 0.4*inch, date_str)

    # 2) Header on upper-left
    canvas.setFont("Helvetica", 10)
    canvas.drawString(doc.leftMargin, height - 0.4*inch, header)

    # 3) Main title on center
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawCentredString(width / 2, height - 0.9 * inch, title)

    canvas.restoreState()

@bp.route('/generate_photo_cards', methods=['POST'])
@permission_required('students+view, students+add, students+edit, students+delete')
def generate_photo_cards():
    ids = list(set(request.form.getlist('student_ids')))

    if not ids:
        flash("No students selected.", 'danger')
        return redirect(url_for('students.list_students'))

    pdf_title = request.form.get('pdf_title', '').strip()
    filter_class_of = request.form.get('class_of', '').strip()
        
    pdf_header = "UC San Diego Skaggs School of Pharmacy & Pharmaceutical Sciences"
    pdf_filename = request.form.get('pdf_filename', '').strip() or "photo_cards"

    students = Student.query.filter(Student.id.in_(ids), Student.deleted == False).order_by(Student.last_name, Student.first_name).all()

    if not students:
        flash("No matching students found.", 'danger')
        return redirect(url_for('students.list_students'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.25 * inch,
        rightMargin=0.25 * inch,
        topMargin=0.9 * inch,  # extra space for repeated header
        bottomMargin=0.25 * inch
    )

    styles = getSampleStyleSheet()
    info_style = styles['Normal'].clone('small_centered')
    info_style.fontSize = 8  # or 9 if you want slightly larger
    info_style.leading = 10  # line spacing
    info_style.alignment = 1  # center

    elements = []
    row = []
    card_rows = []

    for student in students:
        # Image
        photo_path = os.path.join(PHOTO_UPLOAD_FOLDER, student.photo_url or '')

        try:
            if os.path.exists(photo_path):
                img_reader = ImageReader(photo_path)
                iw, ih = img_reader.getSize()
                max_img_width = 1.7 * inch  # Just under card width
                max_img_height = 2.2 * inch

                aspect = ih / iw
                target_width = max_img_width
                target_height = target_width * aspect

                if target_height > max_img_height:
                    target_height = max_img_height
                    target_width = target_height / aspect

                img = Image(photo_path, width=target_width, height=target_height)
            else:
                raise FileNotFoundError()
        except (UnidentifiedImageError, FileNotFoundError):
            img = Spacer(1.5 * inch, 1.5 * inch)

        # Info
        info_lines = []
        info_lines.append(f"{student.first_name} {student.last_name}")
        if not filter_class_of and student.class_of:
            info_lines.append(f"Class of {student.class_of}")
        if student.email:
            info_lines.append(f"<font color='blue'>{student.email}</font>")
        if student.pronoun:
            info_lines.append(f"<font color='#333333'>{student.pronoun}</font>")
        if student.phonetic_last_name or student.phonetic_first_name:
            phonetic = f"<font color='#333333'><i>{student.phonetic_last_name} {student.phonetic_first_name}</i></font>".strip()
            info_lines.append(phonetic)
        
        # Join with line breaks
        info = "<br/>".join(info_lines)
        info_paragraph = Paragraph(info, info_style)

        # Card = image + text
        card_table = Table(
            [[img], [Spacer(1, 0.01 * inch)], [info_paragraph]],
            colWidths=[1.9 * inch]
        )
        card_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
        ]))

        row.append(card_table)

        if len(row) == 4:
            card_rows.append(row)
            row = []

    if row:
        card_rows.append(row)

    for card_row in card_rows:
        t = Table([card_row], colWidths=[1.95 * inch] * len(card_row))
        t.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))

        elements.append(t)
        elements.append(Spacer(1, 0.05 * inch))  # smaller space between rows

    try:
        print("Calling doc.build()...", flush=True)
        doc.build(
            elements,
            onFirstPage=lambda c, d: add_page_header(c, d, pdf_title, pdf_header),
            onLaterPages=lambda c, d: add_page_header(c, d, pdf_title, pdf_header)
        )
        print("Finished doc.build()", flush=True)
    except Exception as ex:
        print("PDF generation failed:", ex)
        flash("There was a problem generating the PDF.", "danger")
        return redirect(url_for('students.list_students'))
    
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{pdf_filename}.pdf",
        mimetype='application/pdf'
    )

@bp.route('/enroll')
@permission_required('students+view, students+add, students+edit, students+delete')
def enroll_students():
    context = get_filtered_students_context()
    return render_template('students/enroll.html', **context)

@bp.route('/photo_cards')
@permission_required('students+view, students+add, students+edit, students+delete')
def photo_cards():
    context = get_filtered_students_context()
    return render_template('students/photo_cards.html', **context)


def get_filtered_students_context():
    form = CSRFOnlyForm()
    selected_class = request.args.get('class_of', '')
    selected_term = request.args.get('term', '')
    selected_course = request.args.get('course_id', '')
    pdf_title = request.args.get('pdf_title', '')

    class_years = db.session.query(Student.class_of).distinct().filter(Student.class_of != '').order_by(Student.class_of).all()
    terms = get_enrollment_terms()
    terms_with_courses = get_terms_with_courses()

    for term in terms_with_courses:
        term['id'] = str(term['id'])
        for course in term.get('courses', []):
            course['id'] = str(course['id'])
            course['course_code'] = course.get('course_code') or ""

    if selected_term:
        courses = get_canvas_courses_by_term(selected_term)
    else:
        courses = get_canvas_courses(account="SSPPS")

    print("courses",courses)
    # print("terms_with_courses",terms_with_courses)

    students = Student.query

    if selected_class:
        students = students.filter(Student.class_of == selected_class)

    if selected_course:
        enrollments = get_enrollments(course_id=int(selected_course))
        enrolled_student_ids = [e['user']['sis_user_id'] for e in enrollments if 'user' in e and 'id' in e['user']]
        students = students.filter(Student.pid.in_(enrolled_student_ids))

    students = students.filter(Student.deleted == False).order_by(Student.last_name, Student.first_name).all()

    return {
        'form': form,
        'students': students,
        'class_years': [c[0] for c in class_years],
        'selected_class': selected_class,
        'terms': terms,
        'terms_with_courses': terms_with_courses,
        'selected_term': selected_term,
        'courses': courses,
        'selected_course': selected_course,
        'pdf_title': pdf_title,
    }
