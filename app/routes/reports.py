from app.utils import permission_required
from app.models import db, AcademicYear, Attendance, AYCommittee, Committee, Member, MemberRole, FrequencyType, CommitteeType, Employee, Meeting, FileUpload, MemberType, User, Role, Permission
from app.forms import CommitteeReportForm
from app.routes.academic_years import get_academic_years
from app.routes.committee_tracker import get_committees, get_committee_types, get_employees
from collections import defaultdict
from flask import render_template, request, jsonify, Blueprint, send_file
from flask_login import login_required
from sqlalchemy import case, func, and_
from sqlalchemy.orm import selectinload, with_loader_criteria
from sqlalchemy.sql import func
from xhtml2pdf import pisa
import io
import os

bp = Blueprint('reports', __name__, url_prefix='/reports')

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

@bp.route("/get_all_committees", methods=["GET"])
@permission_required("committee_report+view")
def get_all_committees():
    
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
    query = query.join(AYCommittee.members).filter(Member.deleted == False).join(Member.employee)

    # Filter by employee_id if provided
    filter_user = request.args.get("users", "")
    if filter_user and filter_user != "0":
        employee_ids = [int(id) for id in filter_user.split(",")]
        query = query.filter(Member.employee_id.in_(employee_ids))

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
    if filter_committee_type and filter_committee_type != "0":
        type_ids = [int(ct) for ct in filter_committee_type.split(",")]
        query = query.filter(Committee.committee_type_id.in_(type_ids))

    # Fetch results    
    aycommittees = query.all()

    # Only show filtered members
    if filter_user and filter_user != "0":
        for committee in aycommittees:
            committee.members = [m for m in committee.members if m.employee_id in employee_ids]

    # Sort members by role default_order
    for committee in aycommittees:
        committee.members.sort(key=lambda m: m.member_role.default_order if m.member_role and m.member_role.default_order is not None else 999)

    # Build results
    committees = []
    for com in aycommittees:
        if com.meeting_frequency_type:
            duration = com.meeting_duration_in_minutes or 0
            supplemental = com.supplemental_minutes_per_frequency or 0
            expected_minutes = com.meeting_frequency_type.multiplier * (duration + supplemental)
            total_expected_hours = round(expected_minutes / 60.0, 2)
        else:
            total_expected_hours = 0

        committee_data = {
            "academic_year": com.academic_year.year,
            "id": com.id,
            "name": com.committee.name + (f" ({com.committee.short_name})" if com.committee.short_name else ""),
            "mission": com.committee.mission,
            "total_expected_hours": total_expected_hours,
            # "members": [
            #     f"{member.employee.employee_name} ({member.member_role.role}) ({member.employee.job_code_description})"
            #     for member in com.members
            # ],
            "members": [
                # f"{member.employee.employee_name} ({member.member_role.role}) ({member.employee.job_code_description})"
                {
                    "first_name": member.employee.employee_first_name,
                    "last_name": member.employee.employee_last_name,
                    "job_code": member.employee.job_code_description,
                    "role": member.member_role.role
                }
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

@bp.route("/get_committees_by_member", methods=["GET"])
@permission_required("committee_report+view")
def get_committees_by_member():
    
    # Base selectable with safe outer joins
    query = (db.session.query(
            Member.employee_id.label("employee_id"),
            Employee.employee_first_name.label("first_name"),
            Employee.employee_last_name.label("last_name"),
            Employee.job_code_description.label("job_code"),
            Committee.id.label("committee_id"),
            Committee.name.label("committee_name"),
            Committee.short_name.label("committee_short_name"),            
            CommitteeType.type.label("committee_type"),
            AcademicYear.year.label("ay_year"),
            MemberRole.role.label("role"),
            # Raw building blocks
            func.coalesce(FrequencyType.multiplier, 0).label("freq_mult"),
            func.coalesce(AYCommittee.meeting_duration_in_minutes, 0).label("duration"),
            func.coalesce(AYCommittee.supplemental_minutes_per_frequency, 0).label("supp_per_freq"),
            # Meetings attended (count via CASE)
            func.coalesce(func.sum(case((Attendance.status == "Present", 1), else_=0)), 0).label("meetings_attended"),
            # Actual minutes (sum duration for each 'Present')
            func.coalesce(func.sum(case((
                Attendance.status == "Present",
                    func.coalesce(AYCommittee.meeting_duration_in_minutes, 0) +
                    func.coalesce(AYCommittee.supplemental_minutes_per_frequency, 0)), else_=0)), 0).label("actual_minutes"),
            func.count(Meeting.id).label("meetings_total"),
            func.coalesce(func.sum(case((Attendance.status == "Excused", 1), else_=0)), 0).label("meetings_excused"),
        )
        .select_from(Member)
        .join(Member.ay_committee)
        .join(AYCommittee.committee)
        .join(AYCommittee.academic_year)
        .join(Committee.committee_type)
        .join(Member.employee)
        .join(Member.member_role)
        # frequency type is optional
        .outerjoin(AYCommittee.meeting_frequency_type)
        # outer join meetings & attendance with ON-clause filters so we don't drop rows
        .outerjoin(Meeting, and_(Meeting.ay_committee_id == AYCommittee.id, Meeting.deleted == False))
        .outerjoin(Attendance, and_(Attendance.meeting_id == Meeting.id,
                                    Attendance.member_id == Member.id,
                                    Attendance.deleted == False))
        .filter(
            Member.deleted == False,
            AYCommittee.deleted == False,
            Committee.deleted == False,
            CommitteeType.deleted == False,
            AcademicYear.deleted == False
        ))
   
    # Filter by employee_id if provided
    filter_user = request.args.get("users", "")
    if filter_user and filter_user != "0":
        employee_ids = [int(id) for id in filter_user.split(",")]
        query = query.filter(Member.employee_id.in_(employee_ids))

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
    if filter_committee_type and filter_committee_type != "0":
        type_ids = [int(ct) for ct in filter_committee_type.split(",")]
        query = query.filter(Committee.committee_type_id.in_(type_ids))

    # Grouping (member + committee + academic year)
    query = query.group_by(
        Committee.id, Committee.name, Committee.short_name, CommitteeType.type,
        AcademicYear.year,
        Member.employee_id, Employee.employee_first_name, Employee.employee_last_name, Employee.job_code_description,
        MemberRole.role,
        FrequencyType.multiplier, AYCommittee.meeting_duration_in_minutes, AYCommittee.supplemental_minutes_per_frequency
    )
    rows = query.all()

    # Build response with per-year stats
    member_data = defaultdict(lambda: {
        "employee_id": None,
        "first_name": None,
        "last_name": None,
        "job_code": None,
        "years": set(),
        # committees keyed by base committee id (with per-year roles & stats)
        "committees": defaultdict(lambda: {"id": "", "name": "", "short_name": "", "roles": {}, "stats": {}})
    })

    for r in rows:
        meeting_length = (r.duration or 0) + (r.supp_per_freq or 0)
        expected_minutes = ((r.meetings_total or 0) - (r.meetings_excused or 0)) * meeting_length

        total_expected_hours = round((expected_minutes or 0) / 60.0, 2)
        actual_hours = round((r.actual_minutes or 0) / 60.0, 2)
        percent_commitment = round(((r.actual_minutes or 0) / expected_minutes * 100) if expected_minutes > 0 else 100.0, 2)

        m = member_data[r.employee_id]
        m["employee_id"] = r.employee_id
        m["first_name"] = r.first_name
        m["last_name"] = r.last_name
        m["job_code"] = r.job_code
        m["years"].add(r.ay_year)

        c = m["committees"][r.committee_id]
        c["id"] = r.committee_id
        c["name"] = r.committee_name
        c["short_name"] = r.committee_short_name or ""

        # per-year fields
        c["roles"][r.ay_year] = r.role or ""
        c["stats"][r.ay_year] = {
            "total_expected_hours": total_expected_hours,
            "meetings_attended": int(r.meetings_attended or 0),
            "actual_hours": actual_hours,
            "percent_commitment": percent_commitment,
        }
        # accumulate totals
        if "year_totals" not in m:
            m["year_totals"] = defaultdict(lambda: {"annual_actual_hours": 0.0, "annual_expected_hours": 0.0})
        m["year_totals"][r.ay_year]["annual_actual_hours"] += actual_hours
        m["year_totals"][r.ay_year]["annual_expected_hours"] += total_expected_hours

        # ensure all years in m["years"] exist in m["year_totals"]
        for y in m["years"]:
            if y not in m["year_totals"]:
                m["year_totals"][y] = {
                    "annual_actual_hours": 0.0,
                    "annual_expected_hours": 0.0
                }

    # Finalize JSON
    results = []
    for m in member_data.values():
        results.append({
            "employee_id": m["employee_id"],
            "first_name": m["first_name"],
            "last_name": m["last_name"],
            "job_code": m["job_code"],
            "years": sorted(m["years"]),
            "committees": list(m["committees"].values()),
            "year_totals": {
                y: {
                    "annual_actual_hours": round(v["annual_actual_hours"], 2),
                    "annual_expected_hours": round(v["annual_expected_hours"], 2),
                    "annual_percent_commitment": round(
                        (v["annual_actual_hours"] / v["annual_expected_hours"] * 100)
                        if v["annual_expected_hours"] > 0 else 100.0, 2
                    )
                }
                for y, v in m["year_totals"].items()
            }
        })

    results.sort(key=lambda x: x["last_name"].lower())
    return results

@bp.route("/get_committees_by_assignment", methods=["GET"])
@permission_required("committee_report+view")
def get_committees_by_assignment():
    from sqlalchemy import func, case, and_, Float, cast

    # Base selectable with safe outer joins
    q = (db.session.query(
            Member.employee_id.label("employee_id"),
            Employee.employee_first_name.label("first_name"),
            Employee.employee_last_name.label("last_name"),
            Employee.job_code_description.label("job_code"),
            Committee.id.label("committee_id"),
            Committee.name.label("committee_name"),
            Committee.short_name.label("committee_short_name"),            
            CommitteeType.type.label("committee_type"),
            AcademicYear.year.label("ay_year"),
            MemberRole.role.label("role"),
            # Raw building blocks
            func.coalesce(FrequencyType.multiplier, 0).label("freq_mult"),
            func.coalesce(AYCommittee.meeting_duration_in_minutes, 0).label("duration"),
            func.coalesce(AYCommittee.supplemental_minutes_per_frequency, 0).label("supp_per_freq"),
            # Meetings attended (count via CASE)
            func.coalesce(func.sum(case((Attendance.status == "Present", 1), else_=0)), 0).label("meetings_attended"),
            # Actual minutes (sum duration for each 'Present')
            func.coalesce(func.sum(case((
                Attendance.status == "Present",
                    func.coalesce(AYCommittee.meeting_duration_in_minutes, 0) +
                    func.coalesce(AYCommittee.supplemental_minutes_per_frequency, 0)), else_=0)), 0).label("actual_minutes"),
            func.count(Meeting.id).label("meetings_total"),
            func.coalesce(func.sum(case((Attendance.status == "Excused", 1), else_=0)), 0).label("meetings_excused"),
        )
        .select_from(Member)
        .join(Member.ay_committee)
        .join(AYCommittee.committee)
        .join(AYCommittee.academic_year)
        .join(Committee.committee_type)
        .join(Member.employee)
        .join(Member.member_role)
        # frequency type is optional
        .outerjoin(AYCommittee.meeting_frequency_type)
        # outer join meetings & attendance with ON-clause filters so we don't drop rows
        .outerjoin(Meeting, and_(Meeting.ay_committee_id == AYCommittee.id, Meeting.deleted == False))
        .outerjoin(Attendance, and_(Attendance.meeting_id == Meeting.id,
                                    Attendance.member_id == Member.id,
                                    Attendance.deleted == False))
        .filter(
            Member.deleted == False,
            AYCommittee.deleted == False,
            Committee.deleted == False,
            CommitteeType.deleted == False,
            AcademicYear.deleted == False
        ))
    
    # Filters (same as before)
    filter_user = request.args.get("users", "")
    if filter_user and filter_user != "0":
        employee_ids = [int(i) for i in filter_user.split(",")]
        q = q.filter(Member.employee_id.in_(employee_ids))

    filter_year_ids = request.args.get("years", "")
    if filter_year_ids and filter_year_ids != "0":
        year_ids = [int(y) for y in filter_year_ids.split(",")]
        q = q.filter(AYCommittee.academic_year_id.in_(year_ids))

    filter_committee_ids = request.args.get("committees", "")
    if filter_committee_ids and filter_committee_ids != "0":
        committee_ids = [int(c) for c in filter_committee_ids.split(",")]
        q = q.filter(AYCommittee.committee_id.in_(committee_ids))

    filter_committee_type = request.args.get("types", "")
    if filter_committee_type and filter_committee_type != "0":
        type_ids = [int(ct) for ct in filter_committee_type.split(",")]
        q = q.filter(Committee.committee_type_id.in_(type_ids))

    q = q.group_by(
        Committee.id, Committee.name, Committee.short_name, CommitteeType.type,
        AcademicYear.year,
        Member.employee_id, Employee.employee_first_name, Employee.employee_last_name, Employee.job_code_description,
        MemberRole.role,
        FrequencyType.multiplier, AYCommittee.meeting_duration_in_minutes, AYCommittee.supplemental_minutes_per_frequency
    )

    rows = q.all()

    committee_data = defaultdict(lambda: {
        "committee_id": None,
        "name": None,
        "short_name": None,
        "committee_type": None,
        "years": set(),
        # members keyed by employee id
        "members": defaultdict(lambda: {"employee_id": "", "first_name": "", "last_name": "", "job_code": "", "roles": {}, "stats": {}})
    })

    for r in rows:
        meeting_length = (r.duration or 0) + (r.supp_per_freq or 0)
        expected_minutes = ((r.meetings_total or 0) - (r.meetings_excused or 0)) * meeting_length
        total_expected_hours = round(expected_minutes / 60.0, 2)
        actual_hours = round((r.actual_minutes or 0) / 60.0, 2)
        percent_commitment = round((actual_hours / (expected_minutes / 60.0) * 100) if expected_minutes > 0 else 100.0, 2)

        c = committee_data[r.committee_id]
        c["committee_id"] = r.committee_id
        c["name"] = r.committee_name
        c["short_name"] = r.committee_short_name or ""
        c["committee_type"] = r.committee_type or ""
        c["years"].add(r.ay_year)

        m = c["members"][r.employee_id]
        m["employee_id"] = r.employee_id
        m["first_name"] = r.first_name
        m["last_name"] = r.last_name
        m["job_code"] = r.job_code
        m["roles"][r.ay_year] = r.role or ""
        m["stats"][r.ay_year] = {
            "total_expected_hours": total_expected_hours,
            "meetings_attended": int(r.meetings_attended or 0),
            "actual_hours": actual_hours,
            "percent_commitment": percent_commitment,
        }

    # Finalize JSON structure
    results = []
    for c in committee_data.values():
        results.append({
            "committee_id": c["committee_id"],
            "name": c["name"],
            "short_name": c["short_name"],
            "committee_type": c["committee_type"],
            "years": sorted(c["years"]),
            "members": list(c["members"].values()),
        })

    results.sort(key=lambda x: x["name"].lower())
    return results

@bp.route('/generate_pdf', methods=['POST'])
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

def convert_html_to_pdf(html_content):
    """Converts HTML content to a PDF file in memory."""
    pdf_file = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.BytesIO(html_content.encode("utf-8")), pdf_file)

    if pisa_status.err:
        return None
    pdf_file.seek(0)
    return pdf_file

@bp.route('/report_all_committees/')
@permission_required("committee_report+view")
def report_all_committees():
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
    form.users.choices = [(0, "All")]
    form.users.choices += [(row.employee_id, f"{row.employee_last_name}, {row.employee_first_name}") for row in get_employees()]
    form.users.data = [0]

    return render_template('reports/report_all_committees.html', form=form)

@bp.route('/member_report/')
@permission_required("committee_report+view")
def member_report():
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
    form.users.choices = [(0, "All")]
    form.users.choices += [(row.employee_id, f"{row.employee_last_name}, {row.employee_first_name}") for row in get_employees()]
    form.users.data = [0]

    return render_template('reports/report_by_member.html', form=form)

@bp.route('/assignment_report/')
@permission_required("committee_report+view")
def assignment_report():
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
    form.users.choices = [(0, "All")]
    form.users.choices += [(row.employee_id, f"{row.employee_last_name}, {row.employee_first_name}") for row in get_employees()]
    form.users.data = [0]

    return render_template('reports/report_by_assignment.html', form=form)