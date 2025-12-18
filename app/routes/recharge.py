from app import db
from app import config
from app.cred import GOOGLE_RECAPTCHA_SECRET, GOOGLE_RECAPTCHA_SITEKEY
from app.forms import InstrumentRequestForm
from app.models import Department, Employee, InstrumentRequest, Instrument, ProjectTaskCode, User, InstrumentCalendarEvent as CalendarEvent
from app.utils import permission_required, has_permission
from datetime import datetime, timezone
from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for, render_template_string
from flask_login import login_required, current_user
from PIL import Image, ImageDraw, ImageFont
import hashlib
import os
import qrcode
import subprocess
import requests
import tempfile

bp = Blueprint('recharge', __name__, url_prefix='/recharge')

UCSD_COLORS = [
    "#182B49",  # UCSD Blue (Primary)
    "#00629B",  # Blue
    "#C69214",  # UCSD Gold (Primary)
    "#6E963B",  # Green
    "#691635",  # Magenta
    "#00C6D7",  # Turquoise
    "#FC8900",  # Orange    
    "#747678",  # Cool Gray
    ]

RECAPTCHA_SECRET = GOOGLE_RECAPTCHA_SECRET
RECAPTCHA_SITEKEY = GOOGLE_RECAPTCHA_SITEKEY

# @bp.before_request
# def before_request():
#     excluded_endpoints = ['recharge.request_instrument','recharge.calendar','recharge.get_events']  # full endpoint name: blueprint_name.view_function_name
#     if request.endpoint in excluded_endpoints:
#         return  # Skip login_required check
#     return login_required(lambda: None)()  # Call login_required manually

def aligned_to_15(dt: datetime) -> bool:
    return dt.minute % 15 == 0 and dt.second == 0 and dt.microsecond == 0


def get_all_machines_from_db():
    machines_list = Instrument.query.filter_by(flag=True).order_by(Instrument.machine_name).all()

    return machines_list

def assign_machine_colors(machines):
    """
    Assign each machine a unique color from UCSD_COLORS.
    Returns a dict: {machine_name: color}
    """
    assigned = {}
    used_colors = set()

    for machine in machines:
        # Hash machine name to pick initial index
        h = hashlib.md5(machine.machine_name.encode("utf-8")).hexdigest()
        index = int(h[:8], 16) % len(UCSD_COLORS)
        color = UCSD_COLORS[index]

        # Avoid duplicates
        attempts = 0
        while color in used_colors and attempts < len(UCSD_COLORS):
            index = (index + 1) % len(UCSD_COLORS)
            color = UCSD_COLORS[index]
            attempts += 1

        assigned[machine.machine_name] = color
        used_colors.add(color)

    return assigned

@bp.route("/api/machine-colors")
def get_machine_colors():
    machines = get_all_machines_from_db()
    return jsonify(assign_machine_colors(machines))

def parse_iso_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

def verify_captcha(captcha_response):
    r = requests.post(
        "https://www.google.com/recaptcha/api/siteverify",
        data={"secret": RECAPTCHA_SECRET, "response": captcha_response}
    )
    print(r.json())
    return r.json().get("success", False)

# --- Requestor form ---
@bp.route("/request_instrument/", methods=["GET", "POST"])
def request_instrument():
    form = InstrumentRequestForm()
    request_data = None

    if form.validate_on_submit():
        machine = Instrument.query.get(form.machine.data)
        
        req = InstrumentRequest(
            machine_name=machine.machine_name,
            department_code=form.department_code.data,
            pi_name=form.pi_name.data,
            pi_email=form.pi_email.data,
            pi_phone=form.pi_phone.data,
            requestor_name=form.requestor_name.data,
            requestor_position=form.requestor_position.data,
            requestor_email=form.requestor_email.data,
            requestor_phone=form.requestor_phone.data,
            had_training=True if form.had_training.data.lower()=="yes" else False,
            project_task_code=form.project_task_code.data,
            funding_source_code=form.funding_source.data
        )
        db.session.add(req)
        db.session.commit()

        request_data = {
            "Instrument": machine.machine_name,
            "PI Name": form.pi_name.data,
            "PI Email": form.pi_email.data,
            "PI Phone": form.pi_phone.data,
            "Requestor Name": form.requestor_name.data,
            "Requestor Position": form.requestor_position.data,
            "Requestor Email": form.requestor_email.data,
            "Requestor Phone": form.requestor_phone.data,
            "Project Task Code": form.project_task_code.data,
            "Funding Source": form.funding_source.data,
            "Had Training": "Yes" if form.had_training.data.lower()=="yes" else "No",
        }

        # Convert to an HTML table for email
        subject = f"New {req.machine_name} Request Submitted"
        recipients = "screeningcore@health.ucsd.edu"
        cc = req.pi_email
        sender = req.requestor_email
        # Build the full link using the current host
        review_url = request.url_root.rstrip("/") + url_for("recharge.review_requests", status="Pending")

        body_template = """
        <h3>New Instrument Request Submitted</h3>
        <table border="1" cellspacing="0" cellpadding="6" style="border-collapse: collapse; width: 100%;">
            {% for key, value in request_data.items() %}
            <tr>
                <td style="background-color:#f5f5f5; font-weight:bold;">{{ key }}</td>
                <td>{{ value }}</td>
            </tr>
            {% endfor %}
        </table>
        <p>Please review and process the request accordingly.  
           <a href="{{ review_url }}">Review all pending requests here.</a>
        </p>
        <p>Thank you!</p>
        """

        # Render it with data
        body_html = render_template_string(body_template, request_data=request_data, review_url=review_url)

        send_email_via_powershell(recipients, cc, sender, subject, body_html)

    return render_template("recharge/request_instrument.html", form=form, request_data=request_data)

# --- Reviewer list ---
@bp.route("/review_requests")
@login_required
@permission_required('screeningcore_approve+add')
def review_requests():

    # print(current_user.can("screeningcore_approve", "add"))
    status = request.args.get("status")
    machine = request.args.get("machine")
    print("machine",request.args.get('machine'))
    query = InstrumentRequest.query

    if status:
        query = query.filter_by(status=status)
        
    if machine:
        query = query.filter_by(machine_name=machine)

    requests_list = query.order_by(InstrumentRequest.created_at.desc()).all()
    machines_list = Instrument.query.filter_by(flag=True).order_by(Instrument.machine_name).all()

    return render_template("recharge/review_requests.html", requests=requests_list, machines=machines_list)

@bp.route('/handle_request/<string:request_id>', methods=['POST'])
@login_required
@permission_required('screeningcore_approve+add')
def handle_request(request_id):
    notes = request.form.get('notes')
    action = request.form.get('action')
    req = InstrumentRequest.query.get_or_404(request_id)
    req.approved_at = datetime.now()
    req.approved_by = current_user.username
    req.notes = req.notes+", "+request.form.get("notes") if req.notes else request.form.get("notes")

    if action == 'approve':
        # Update status
        req.status = "Approved"
        db.session.commit()

        # Reuse the email function
        email_request_barcode(request_id)

        flash(f"Request #{req.id} approved and barcode emailed to {req.requestor_email}.", "success")

    elif action == 'deny':
        # Update status
        req.status = "Denied"
        db.session.commit()

        flash(f"Request #{req.id} denied.", "success")

    return redirect(url_for("recharge.review_requests"))

@login_required
def email_request(request_id):

    """Generates barcode and sends it via email."""
    req = InstrumentRequest.query.get_or_404(request_id)
    machine = Instrument.query.filter_by(machine_name=req.machine_name).first()

    user = User.query.filter_by(id=current_user.id, deleted=False).first()
    approver = Employee.query.filter_by(employee_id=user.employee_id).first()

    # Create barcode image in memory
    payload = f"{req.id}"
    print("Payload:", payload, type(payload))    

    # Generate QR code image
    qr_img = qrcode.make(payload).convert("RGB")
    print("QR size:", qr_img.size)

    # Pick a font (falls back if not found)
    try:
        font = ImageFont.truetype("arial.ttf", 30)  # You can adjust font + size
    except:
        font = ImageFont.load_default()
    
    title_text = f"{req.requestor_name} - {req.machine_name}"

    # Measure text size
    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    print("Measuring text...")
    try:
        bbox = dummy_draw.textbbox((0, 0), title_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
        # For older Pillow
        text_width, text_height = dummy_draw.textsize(title_text, font=font)
    print("Text size:", text_width, text_height)

    # Create canvas
    qr_width, qr_height = qr_img.size
    padding = 20
    new_height = qr_height + text_height + padding
    new_img = Image.new("RGB", (qr_width, new_height), "white")

    # Draw title
    draw = ImageDraw.Draw(new_img)
    text_x = (qr_width - text_width) // 2
    draw.text((text_x, 5), title_text, fill="black", font=font)

    # Paste QR
    new_img.paste(qr_img, (0, text_height + padding))

    # ✅ Force save to a known writable location
    filename = os.path.join(tempfile.gettempdir(), f"{req.id}.png")
    print("Saving QR to:", filename)

    try:
        new_img.save(filename, "PNG")
        print("Exists after save?", os.path.exists(filename))
        print("QR saved:", filename)
    except Exception as e:
        print("Error saving QR:", str(e))

    # Send email with barcode
    subject = f"{req.machine_name} Request Approved"
    recipients = req.requestor_email
    cc = req.pi_email
    sender = approver.email

    body_html = f"""
    <p>Dear {req.requestor_name},</p>

    <p>Your instrument request for <strong>{req.machine_name}</strong> has been approved.<br>
    Your <strong>barcode is attached</strong> - <u>you will need it to access the instrument</u>.</p>

    <p>To help ensure smooth scheduling and fair use, please note the following guidelines:</p>
    <ul>
        <li><strong>Minimum usage time:</strong> {machine.min_duration} {machine.duration_type}.</li>
        <li><strong>Billing increments:</strong> Time is billed in {machine.min_increment}-{machine.increment_type} increments after the minimum usage time ({machine.min_duration} {machine.duration_type}).</li>
        <li><strong>Logout requirement:</strong> Please log out at the end of your session. Billing continues until logout is completed.</li>
        <li><strong>Booking:</strong> All sessions must be reserved in advance through the instrument booking calendar.  Calendar link will be sent shortly.</li>
    </ul>

    <p>Thank you for your cooperation, and we look forward to supporting your work!</p>

    <p>Best regards,<br>
    Screening Core</p>
    """
    # : <a href="{machine.calendar_url}">Calendar Link</a>
    send_email_via_powershell(recipients, cc, sender, subject, body_html, filename)

    # Delete barcode file
    try:
        os.remove(filename)
    except OSError as e:
        print(f"Error deleting file {filename}: {e}")

    return req

@bp.route("/email-request-barcode/<string:request_id>")
@login_required
@permission_required('screeningcore_approve+add')
def email_request_barcode(request_id):

    """Generates barcode and sends it via email."""
    req = InstrumentRequest.query.get_or_404(request_id)
    machine = Instrument.query.filter_by(machine_name=req.machine_name).first()

    user = User.query.filter_by(id=current_user.id, deleted=False).first()
    approver = Employee.query.filter_by(employee_id=user.employee_id).first()

    # Create barcode image in memory
    payload = f"{req.id}"
    print("Payload:", payload, type(payload))    

    # Generate QR code image
    qr_img = qrcode.make(payload).convert("RGB")
    print("QR size:", qr_img.size)

    # Pick a font (falls back if not found)
    try:
        font = ImageFont.truetype("arial.ttf", 30)  # You can adjust font + size
    except:
        font = ImageFont.load_default()
    
    title_text = f"{req.requestor_name} - {req.machine_name}"

    # Measure text size
    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    print("Measuring text...")
    try:
        bbox = dummy_draw.textbbox((0, 0), title_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
        # For older Pillow
        text_width, text_height = dummy_draw.textsize(title_text, font=font)
    print("Text size:", text_width, text_height)

    # Create canvas
    qr_width, qr_height = qr_img.size
    padding = 20
    new_height = qr_height + text_height + padding
    new_img = Image.new("RGB", (qr_width, new_height), "white")

    # Draw title
    draw = ImageDraw.Draw(new_img)
    text_x = (qr_width - text_width) // 2
    draw.text((text_x, 5), title_text, fill="black", font=font)

    # Paste QR
    new_img.paste(qr_img, (0, text_height + padding))

    # ✅ Force save to a known writable location
    filename = os.path.join(tempfile.gettempdir(), f"{req.id}.png")
    print("Saving QR to:", filename)

    try:
        new_img.save(filename, "PNG")
        print("Exists after save?", os.path.exists(filename))
        print("QR saved:", filename)
    except Exception as e:
        print("Error saving QR:", str(e))

    # Send email with barcode
    subject = f"{req.machine_name} Request Approved"
    recipients = req.requestor_email
    cc = req.pi_email
    sender = approver.email

    body_html = f"""
    <p>Dear {req.requestor_name},</p>

    <p>Your instrument request for <strong>{req.machine_name}</strong> has been approved.<br>
    Your <strong>barcode is attached</strong> - <u>you will need it to access the instrument</u>.</p>

    <p>To help ensure smooth scheduling and fair use, please note the following guidelines:</p>
    <ul>
        <li><strong>Minimum usage time:</strong> {machine.min_duration} {machine.duration_type}.</li>
        <li><strong>Billing increments:</strong> Time is billed in {machine.min_increment}-{machine.increment_type} increments after the minimum usage time ({machine.min_duration} {machine.duration_type}).</li>
        <li><strong>Logout requirement:</strong> Please log out at the end of your session. Billing continues until logout is completed.</li>
        <li><strong>Booking:</strong> All sessions must be reserved in advance through the instrument booking calendar.  Calendar link will be sent shortly.</li>
    </ul>

    <p>Thank you for your cooperation, and we look forward to supporting your work!</p>

    <p>Best regards,<br>
    Screening Core</p>
    """
    # : <a href="{machine.calendar_url}">Calendar Link</a>
    send_email_via_powershell(recipients, cc, sender, subject, body_html, filename)

    # Delete barcode file
    try:
        os.remove(filename)
    except OSError as e:
        print(f"Error deleting file {filename}: {e}")

    return req

@bp.route("/resend-email/<string:request_id>")
@login_required
@permission_required('screeningcore_approve+add')
def resend_email(request_id):
    req = InstrumentRequest.query.get_or_404(request_id)
    try:
        email_request_barcode(request_id)
    except Exception as e:
        flash(f"Error resending email: {str(e)}", "danger")
        return redirect(url_for("recharge.review_requests"))
    flash(f"Request #{req.id} barcode emailed to {req.requestor_email}.", "success")
    return redirect(url_for("recharge.review_requests"))

@login_required
def send_email_via_powershell(to_address, to_cc=None, from_address=None, subject=None, body=None, attachment_path=None):
    """Sends email using PowerShell's Send-MailMessage cmdlet."""

    # Escape double quotes in the body so HTML isn’t broken
    safe_body = body.replace('"', '`"') if body else ""

    if attachment_path:
        ps_script = f'Send-MailMessage -From "{from_address}" -To "{to_address}" -Cc ("{to_cc}","{from_address}","screeningcore@health.ucsd.edu","jlagedesiqueiraneto@health.ucsd.edu") -Subject "{subject}" -Body "{safe_body}" -BodyAsHtml -Attachments "{attachment_path}" -SmtpServer "{config.MAIL_SERVER}" -UseSsl'
    else:
        ps_script = f'Send-MailMessage -From "{from_address}" -To "{to_address}" -Cc ("{to_cc}","{from_address}","screeningcore@health.ucsd.edu","jlagedesiqueiraneto@health.ucsd.edu") -Subject "{subject}" -Body "{safe_body}" -BodyAsHtml -SmtpServer "{config.MAIL_SERVER}" -UseSsl'
        
    completed = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    if completed.returncode != 0:
        print("Error sending mail:", completed.stderr)
    else:
        print("Mail sent successfully")

def is_admin():
    return current_user.is_authenticated and has_permission("screeningcore_approve+add")

@bp.route("/calendar")
@bp.route("/calendar/<string:request_id>")
def calendar(request_id=None):
    # print("In calendar route", request)
    # request_id = request.args.get("request_id")
    # print("Request ID from args:", request_id)
    # request_id = request.args.get("request_id")

    if request_id:
        req = InstrumentRequest.query.get(request_id)

        # ❌ Invalid or missing request or ❌ Not approved
        if not req or req.status != "Approved":
            flash(
                "Invalid request. Please submit a request to schedule an instrument.",
                "warning"
            )
            return redirect(url_for("recharge.public_calendar"))

    return render_template(
        "recharge/calendar.html",
        request_id=request_id,
        admin=is_admin(),
        public=False,
        recaptcha_site_key=RECAPTCHA_SITEKEY
    )


@bp.route("/calendar/public")
def public_calendar():
    return render_template(
        "recharge/calendar.html",
        request_id=None,
        admin=False,
        public=True
    )


"""
Get Instrument Request (Locking + Context)
"""
@bp.route("/api/instrument-request/<string:request_id>")
def get_instrument_request(request_id):
    req = InstrumentRequest.query.get_or_404(request_id)

    return jsonify({
        "id": req.id,
        "requestor_name": req.requestor_name,
        "machine_name": req.machine_name,
        "status": req.status
    })


"""
Get ALL Events (Multi-Machine Combined View)
"""
@bp.route("/api/events")
def get_events():
    machines = request.args.getlist("machine")

    query = CalendarEvent.query.filter_by(deleted=False)
    if machines:
        query = query.filter(CalendarEvent.machine_name.in_(machines))

    events = query.all()
    for e in events:
        print("Event:", e.id, e.title, e.start, e.end, e.machine_name, e.request_id)

    all_machines = get_all_machines_from_db()
    machine_colors = assign_machine_colors(all_machines)

    for e in events:
        if e.request_id:
            req = InstrumentRequest.query.get_or_404(e.request_id)
            e.requestor_name = req.requestor_name

    event_list = []
    for e in events:
        if e.request_id:
            req = InstrumentRequest.query.get_or_404(e.request_id)
            e.requestor_name = req.requestor_name
        machine = e.machine_name
        event_list.append({
            "id": e.id,
            "title": e.title,
            "start": e.start.replace(tzinfo=timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z"),
            "end": e.end.replace(tzinfo=timezone.utc)
                          .isoformat()
                          .replace("+00:00", "Z"),
            "extendedProps": {
                "machine_name": machine,
                "request_id": e.request_id,
                "requestor_name": e.requestor_name
            },
            "backgroundColor": machine_colors.get(machine, "#000000"),
            "borderColor": machine_colors.get(machine, "#000000")
        })

    # Include machine-color mapping for filter/legend
    response = {
        "events": event_list,
        "machines": [{"name": m.machine_name, "color": machine_colors[m.machine_name]} for m in all_machines]
    }

    return jsonify(response)


"""
List Machines for Filters
"""
@bp.route("/api/machines")
def get_machines():
    machines = (
        db.session.query(CalendarEvent.machine_name)
        .distinct()
        .order_by(CalendarEvent.machine_name)
        .all()
    )

    return jsonify([m[0] for m in machines])


@bp.route("/api/approved-requests")
@login_required
@permission_required('screeningcore_approve+add')
def approved_requests():
    requests = (
        InstrumentRequest.query
        .filter(InstrumentRequest.status == "Approved")
        .order_by(InstrumentRequest.machine_name, InstrumentRequest.requestor_name)
        .all()
    )

    return jsonify([
        {
            "id": r.id,
            "machine_name": r.machine_name,
            "requestor_name": r.requestor_name,
            "pi_name": r.pi_name
        }
        for r in requests
    ])


"""
Add Event (Machine-Specific Conflict Rule)
"""
@bp.route("/api/events", methods=["POST"])
def add_event():
    data = request.get_json()

    if not verify_captcha(data.get("recaptcha_token", "")):
        return jsonify({"error": "CAPTCHA verification failed"}), 400

    title = data.get("title")
    machine_name = data.get("machine_name")
    request_id = data.get("request_id")

    start = parse_iso_utc(data["start"])
    end = parse_iso_utc(data["end"])

    override = bool(data.get("override", False))
    admin = is_admin()

    # ----------------------------------
    # ✅ REQUEST VALIDATION GOES HERE
    # ----------------------------------
    if request_id:
        req = InstrumentRequest.query.get_or_404(request_id)

        if req.status != "Approved":
            return jsonify({"error": "Request is not approved."}), 400

        if req.machine_name != machine_name:
            return jsonify({"error": "Machine mismatch."}), 400

    # ----------------------------------
    # CONFLICT CHECK
    # ----------------------------------
    if not (admin and override):
        conflicts = (
            CalendarEvent.query
            .filter(
                CalendarEvent.machine_name == machine_name,
                CalendarEvent.start < end,
                CalendarEvent.end > start,
                CalendarEvent.deleted == False
            )
            .all()
        )

        if conflicts:
            return jsonify({
                "error": "This machine is already booked.",
                "conflict": True
            }), 400

    # ----------------------------------
    # CREATE EVENT
    # ----------------------------------
    event = CalendarEvent(
        title=title,
        machine_name=machine_name,
        start=start,
        end=end,
        request_id=request_id
    )

    db.session.add(event)
    db.session.commit()
    
    all_machines = get_all_machines_from_db()
    machine_colors = assign_machine_colors(all_machines)

    return jsonify({
        "id": event.id,
        "title": f"{title}",
        "start": event.start.replace(tzinfo=timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z"),
        "end": event.end.replace(tzinfo=timezone.utc)
                          .isoformat()
                          .replace("+00:00", "Z"),
        "backgroundColor": machine_colors.get(event.machine_name, "#000000"),
        "extendedProps": {
            "machine_name": event.machine_name,
            "request_id": event.request_id,
            "requestor_name": req.requestor_name
        }
    })


"""
Update Event (Machine-Specific Conflict Rule)
"""
@bp.route("/api/events/update", methods=["POST"])
@login_required
@permission_required('screeningcore_approve+add')
def update_event():
    data = request.get_json()

    if not verify_captcha(data.get("recaptcha_token", "")):
        return jsonify({"error": "CAPTCHA verification failed"}), 400
    
    event_id = data.get("id")
    if not event_id:
        return jsonify({"error": "Missing event id"}), 400

    event = CalendarEvent.query.filter_by(id=event_id, deleted=False).first()

    if not event:
        return jsonify({"error": "Event not found"}), 404
    print("Fetched event:", event)
    print("Updating event:", event.id, event.title, event.start, event.end)

    start = parse_iso_utc(data["start"])
    end = parse_iso_utc(data["end"])
    machine = data["machine_name"]

    # ✅ Explicit boolean handling
    override = bool(data.get("override", False))
    admin = is_admin()
    print("Admin:", admin, "Override:", override)
    print(not (admin and override))
    # ---------------------------
    # CONFLICT CHECK
    # ---------------------------
    if not (admin and override):
        conflicts = (
            CalendarEvent.query
            .filter(
                CalendarEvent.machine_name == machine,
                CalendarEvent.id != event_id,  # exclude self
                CalendarEvent.start < end,
                CalendarEvent.end > start,
                CalendarEvent.deleted == False
            )
            .all()
        )

        if conflicts:
            return jsonify({
                "error": "This machine is already booked.",
                "conflict": True
            }), 400

    # ---------------------------
    # UPDATE EVENT
    # ---------------------------
    event.start = start
    event.end = end

    db.session.commit()

    req = InstrumentRequest.query.get_or_404(event.request_id)
    all_machines = get_all_machines_from_db()
    machine_colors = assign_machine_colors(all_machines)

    return jsonify({
        "id": event.id,
        "title": event.title,
        "start": event.start.replace(tzinfo=timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z"),
        "end": event.end.replace(tzinfo=timezone.utc)
                          .isoformat()
                          .replace("+00:00", "Z"),
        "backgroundColor": machine_colors.get(event.machine_name, "#000000"),
        "extendedProps": {
            "machine_name": event.machine_name,
            "request_id": event.request_id,
            "requestor_name": req.requestor_name
        }
    })

@bp.route("/api/events/delete", methods=["POST"])
@login_required
@permission_required('screeningcore_approve+add')
def soft_delete_event():
    data = request.get_json()

    if not verify_captcha(data.get("recaptcha_token", "")):
        return jsonify({"error": "CAPTCHA verification failed"}), 400

    event_id = data.get("id")
    if not event_id:
        return jsonify({"error": "Missing event id"}), 400

    event = CalendarEvent.query.filter_by(id=event_id, deleted=False).first()

    if not event:
        return jsonify({"error": "Event not found"}), 404

    # 👇 Soft delete
    event.deleted = True
    event.deleted_date = datetime.now()
    event.deleted_by = current_user.username  # or id / email

    db.session.commit()

    return jsonify({
        "success": True,
        "id": event_id
    })


