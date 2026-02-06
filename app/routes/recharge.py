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
    # print(r.json())
    return r.json().get("success", False)

def get_client_ip():
    """
    Return the best-guess client IP address.
    Works behind proxies if configured correctly.
    """
    # If behind a proxy (nginx, load balancer, etc.)
    if request.headers.get("X-Forwarded-For"):
        # X-Forwarded-For may contain multiple IPs: client, proxy1, proxy2
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()

    return request.remote_addr

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
            requestor_email=form.requestor_email.data
        )
        db.session.add(req)
        db.session.commit()

        request_data = {
            "Instrument": machine.machine_name,
            "PI Name": form.pi_name.data,
            "PI Email": form.pi_email.data,
            "PI Phone": form.pi_phone.data,
            "Requestor Name": form.requestor_name.data,
            "Requestor Email": form.requestor_email.data
        }

        # Reuse the email function
        email_request_barcode(req.id)

        flash(f"Request #{req.id} approved and barcode emailed to {req.requestor_email}.", "success")

    return render_template("recharge/request_instrument.html", form=form, request_data=request_data)

# --- Reviewer list ---
@bp.route("/review_requests")
@login_required
@permission_required('screeningcore_approve+add')
def review_requests():

    status = request.args.get("status")
    machine = request.args.get("machine")
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

# @login_required
# def email_request(request_id):

#     """Generates barcode and sends it via email."""
#     req = InstrumentRequest.query.get_or_404(request_id)
#     machine = Instrument.query.filter_by(machine_name=req.machine_name).first()

#     user = User.query.filter_by(id=current_user.id, deleted=False).first()
#     # approver = Employee.query.filter_by(employee_id=user.employee_id).first()

#     calendar_url = f"{request.url_root.rstrip('/')}{url_for('recharge.calendar', request_id=req.id)}"

#     # Create barcode image in memory
#     payload = f"{req.id}"
#     # print("Payload:", payload, type(payload))    

#     # Generate QR code image
#     qr_img = qrcode.make(payload).convert("RGB")
#     # print("QR size:", qr_img.size)

#     # Pick a font (falls back if not found)
#     try:
#         font = ImageFont.truetype("arial.ttf", 30)  # You can adjust font + size
#     except:
#         font = ImageFont.load_default()
    
#     title_text = f"{req.requestor_name} - {req.machine_name}"

#     # Measure text size
#     dummy_img = Image.new("RGB", (1, 1))
#     dummy_draw = ImageDraw.Draw(dummy_img)
#     # print("Measuring text...")
#     try:
#         bbox = dummy_draw.textbbox((0, 0), title_text, font=font)
#         text_width = bbox[2] - bbox[0]
#         text_height = bbox[3] - bbox[1]
#     except AttributeError:
#         # For older Pillow
#         text_width, text_height = dummy_draw.textsize(title_text, font=font)
#     # print("Text size:", text_width, text_height)

#     # Create canvas
#     qr_width, qr_height = qr_img.size
#     padding = 20
#     new_height = qr_height + text_height + padding
#     new_img = Image.new("RGB", (qr_width, new_height), "white")

#     # Draw title
#     draw = ImageDraw.Draw(new_img)
#     text_x = (qr_width - text_width) // 2
#     draw.text((text_x, 5), title_text, fill="black", font=font)

#     # Paste QR
#     new_img.paste(qr_img, (0, text_height + padding))

#     # ✅ Force save to a known writable location
#     filename = os.path.join(tempfile.gettempdir(), f"{req.id}.png")
#     # print("Saving QR to:", filename)

#     try:
#         new_img.save(filename, "PNG")
#         print("Exists after save?", os.path.exists(filename))
#         print("QR saved:", filename)
#     except Exception as e:
#         print("Error saving QR:", str(e))

#     # Send email with barcode
#     subject = f"{req.machine_name} Request Approved"
#     recipients = req.requestor_email
#     cc = req.pi_email
#     # sender = approver.email
#     sender = "screeningcore@health.ucsd.edu"

#     body_html = f"""
#     <p>Dear {req.requestor_name},</p>

#     <p>Your instrument request for <strong>{req.machine_name}</strong> has been approved.<br>
#     Your <strong>barcode is attached</strong> - <u>you will need it to access the instrument</u>.</p>

#     <p>To help ensure smooth scheduling and fair use, please note the following guidelines:</p>
#     <ul>
#         <li><strong>First time users:</strong> If this is your first time using the instrument, please complete the required training prior to your first session.</li>
#         <li><strong>Instrument Access:</strong> 
#             <ul>
#                 <li>UCSD AD username and password are required to log in to the instrument.</li>
#                 <li>Access to the instrument requires the attached barcode for authentication.</li>
#                 <li>Please log out at the end of your session. Billing continues until logout is completed.</li>
#             </ul>
#         </li>
#         <li><strong>Minimum usage time:</strong> {machine.min_duration} {machine.duration_type}.</li>
#         <li><strong>Billing increments:</strong> Time is billed in {machine.min_increment}-{machine.increment_type} increments after the minimum usage time ({machine.min_duration} {machine.duration_type}).</li>
#         <li><strong>Booking:</strong> All sessions must be reserved in advance through the instrument booking calendar.  Click <a href="{calendar_url}">Calendar Link</a> to book.</li>
#     </ul>

#     <p>Thank you for your cooperation, and we look forward to supporting your work!</p>

#     <p>Best regards,<br>
#     Screening Core</p>
#     """
 
#     send_email_via_powershell(recipients, cc, sender, subject, body_html, filename)

#     # Delete barcode file
#     try:
#         os.remove(filename)
#     except OSError as e:
#         print(f"Error deleting file {filename}: {e}")

#     return req

@bp.route("/email-request-barcode/<string:request_id>")
def email_request_barcode(request_id):

    """Generates barcode and sends it via email."""
    req = InstrumentRequest.query.get_or_404(request_id)
    machine = Instrument.query.filter_by(machine_name=req.machine_name).first()

    # user = User.query.filter_by(id=current_user.id, deleted=False).first()

    calendar_url = f"{request.url_root.rstrip('/')}{url_for('recharge.calendar', request_id=req.id)}"
    
    # Create barcode image in memory
    payload = f"{req.id}"

    # Generate QR code image
    qr_img = qrcode.make(payload).convert("RGB")

    # Pick a font (falls back if not found)
    try:
        font = ImageFont.truetype("arial.ttf", 30)  # You can adjust font + size
    except:
        font = ImageFont.load_default()
    
    title_text = f"{req.requestor_name} - {req.machine_name}"

    # Measure text size
    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    # print("Measuring text...")
    try:
        bbox = dummy_draw.textbbox((0, 0), title_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
        # For older Pillow
        text_width, text_height = dummy_draw.textsize(title_text, font=font)

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
    sender = "screeningcore@health.ucsd.edu"

    body_html = f"""
    <p>Dear {req.requestor_name},</p>

    <p>Your instrument request for <strong>{req.machine_name}</strong> has been approved.<br>
    Your <strong>barcode is attached</strong> - <u>you will need it to access the instrument</u>.</p>

    <p>To help ensure smooth scheduling and fair use, please note the following guidelines:</p>
    <ul>
        <li><strong>First time users:</strong> If this is your first time using the instrument, please complete the required training prior to your first session.</li>
        <li><strong>Instrument Access:</strong> 
            <ul>
                <li>UCSD AD username and password are required to log in to the instrument.</li>
                <li>Access to the instrument requires the attached barcode for authentication.</li>
                <li>Please log out at the end of your session. Billing continues until logout is completed.</li>
            </ul>
        </li>
        <li><strong>Minimum usage time:</strong> {machine.min_duration} {machine.duration_type}.</li>
        <li><strong>Billing increments:</strong> Time is billed in {machine.min_increment}-{machine.increment_type} increments after the minimum usage time ({machine.min_duration} {machine.duration_type}).</li>
        <li><strong>Booking:</strong> All sessions must be reserved in advance through the instrument booking calendar.  Click <a href="{calendar_url}">Calendar Link</a> to book.</li>
    </ul>

    <p>Thank you for your cooperation, and we look forward to supporting your work!</p>

    <p>Best regards,<br>
    Screening Core</p>
    """
    
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

def send_email_via_powershell(to_address, to_cc=None, from_address=None, subject=None, body=None, attachment_path=None):
    
    """Sends email using PowerShell's Send-MailMessage cmdlet."""

    # Escape double quotes in the body so HTML isn’t broken
    safe_body = body.replace('"', '`"') if body else ""

    if attachment_path:
        ps_script = f'Send-MailMessage -From "{from_address}" -To "{to_address}" -Cc ("{to_cc}","{from_address}","screeningcore@health.ucsd.edu") -Subject "{subject}" -Body "{safe_body}" -BodyAsHtml -Attachments "{attachment_path}" -SmtpServer "{config.MAIL_SERVER}" -UseSsl'
    else:
        ps_script = f'Send-MailMessage -From "{from_address}" -To "{to_address}" -Cc ("{to_cc}","{from_address}","screeningcore@health.ucsd.edu") -Subject "{subject}" -Body "{safe_body}" -BodyAsHtml -SmtpServer "{config.MAIL_SERVER}" -UseSsl'
    
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


def get_page_request_id():
    """
    Return the request_id that the front‑end supplied in the URL.
    The front‑end should always include ?request_id=nnn when a user
    is working on a specific request.
    """
    # URL query‑string – most reliable for GET page loads
    qs_id = request.args.get("request_id", type=int)
    if qs_id:
        return qs_id

    # In case the client posts the value (e.g. on Save)
    json_id = request.get_json(silent=True) or {}
    return json_id.get("request_id")


@bp.route("/api/events", methods=["POST"])
def add_event():
    """
    Add Event (Machine-Specific Conflict Rule)
    """
    data = request.get_json()

    # ---------- CAPTCHA ----------
    if not verify_captcha(data.get("recaptcha_token", "")):
        return jsonify({"error": "CAPTCHA verification failed"}), 400

    title = data.get("title")
    machine_name = data.get("machine_name")
    request_id = data.get("request_id")
    start = parse_iso_utc(data["start"])
    end = parse_iso_utc(data["end"])

    override = bool(data.get("override", False))
    admin = is_admin()

    # ---------- REQUEST VALIDATION ----------
    if request_id:
        req = InstrumentRequest.query.get_or_404(request_id)

        if req.status != "Approved":
            return jsonify({"error": "Request is not approved."}), 400

        if req.machine_name != machine_name:
            return jsonify({"error": "Machine mismatch."}), 400
    else:
        # If the user is not working off a request, we still allow creation
        # (e.g. admin‑only free‑form scheduling).  No further checks required.
        req = None

    # ---------- CONFLICT CHECK (always enforced) ----------
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
    
    # ---------- CREATE ----------
    event = CalendarEvent(
        title=title,
        machine_name=machine_name,
        start=start,
        end=end,
        request_id=request_id
    )
    event.created_date = datetime.now()
    if current_user.is_authenticated and current_user.username:
        event.created_by = current_user.username  # or id / email
    elif get_client_ip():
        event.created_by = get_client_ip()  # fallback to IP if no user info
    else:
        event.created_by = "Unknown"

    db.session.add(event)
    db.session.commit()
    
    # ---------- RESPONSE ----------
    all_machines   = get_all_machines_from_db()
    machine_colors = assign_machine_colors(all_machines)

    return jsonify({
        "id": event.id,
        "title": title,
        "start": event.start.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "end":   event.end.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "backgroundColor": machine_colors.get(event.machine_name, "#000000"),
        "extendedProps": {
            "machine_name": event.machine_name,
            "request_id":   event.request_id,
            "requestor_name": req.requestor_name if req else None
        }
    })


@bp.route("/api/events/update", methods=["POST"])
def update_event():
    """
    Update Event (Machine-Specific Conflict Rule)
    """
    data = request.get_json()

    # ---------- CAPTCHA ----------
    if not verify_captcha(data.get("recaptcha_token", "")):
        return jsonify({"error": "CAPTCHA verification failed"}), 400
    
    # ---------- BASIC INPUT ----------
    event_id = data.get("id")
    if not event_id:
        return jsonify({"error": "Missing event id"}), 400

    # ---------- FETCH EVENT ----------
    event = CalendarEvent.query.filter_by(id=event_id, deleted=False).first()
    if not event:
        return jsonify({"error": "Event not found"}), 404
    
    # ---------- OWNERSHIP / AUTHZ ----------
    page_req_id = get_page_request_id()

    # Explicit boolean handling
    admin = is_admin()
    override = bool(data.get("override", False))

    # Non-admins must own the event
    if not admin:
        if page_req_id is None:
            return jsonify({"error": "Missing request_id in URL"}), 400
        if event.request_id != page_req_id:
            return jsonify({"error": "You are not authorized to edit this booking."}), 403
    
    # ---------- NEW TIMES ----------
    start = parse_iso_utc(data["start"])
    end = parse_iso_utc(data["end"])
    machine = data.get("machine_name", event.machine_name)
    title = data.get("title", event.title)

    # ---------- CONFLICT CHECK ----------
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

    # ---------- APPLY CHANGES ----------
    if admin:
        event.request_id = data.get("request_id", event.request_id)  # Admins can change request association
        event.machine_name = machine  # Admins can change machine
        event.title = title  # Admins can change title
        print("Admin override: machine and title updated.")

    event.start = start
    event.end = end
    event.updated_date = datetime.now()
    if current_user.is_authenticated and current_user.username:
        event.updated_by = current_user.username  # or id / email
    elif get_client_ip():
        event.updated_by = get_client_ip()  # fallback to IP if no user info
    else:
        event.updated_by = "Unknown"

    db.session.commit()

    print(event.id, event.title, event.start, event.end, event.machine_name, event.request_id)

    # ---------- RESPONSE ----------
    req = InstrumentRequest.query.get_or_404(event.request_id)
    all_machines = get_all_machines_from_db()
    machine_colors = assign_machine_colors(all_machines)

    return jsonify({
        "id": event.id,
        "title": event.title,
        "start": event.start.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "end":   event.end.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "backgroundColor": machine_colors.get(event.machine_name, "#000000"),
        "extendedProps": {
            "machine_name": event.machine_name,
            "request_id":   event.request_id,
            "requestor_name": req.requestor_name
        }
    })

@bp.route("/api/events/delete", methods=["POST"])
def soft_delete_event():
    data = request.get_json()

    # ---------- CAPTCHA ----------
    if not verify_captcha(data.get("recaptcha_token", "")):
        return jsonify({"error": "CAPTCHA verification failed"}), 400

    event_id = data.get("id")
    if not event_id:
        return jsonify({"error": "Missing event id"}), 400

    # ---------- FETCH ----------
    event = CalendarEvent.query.filter_by(id=event_id, deleted=False).first()
    if not event:
        return jsonify({"error": "Event not found"}), 404

    # ---------- OWNERSHIP ----------
    admin = is_admin()
    if not admin:
        page_req_id = get_page_request_id()
        if page_req_id is None:
            return jsonify({"error": "Missing request_id in URL"}), 400

        if event.request_id != page_req_id:
            return jsonify({"error": "You are not authorized to delete this booking."}), 403
    
    # ---------- SOFT DELETE ----------
    event.deleted = True
    event.deleted_date = datetime.now()
    if current_user.is_authenticated and current_user.username:
        event.deleted_by = current_user.username  # or id / email
    elif get_client_ip():
        event.deleted_by = get_client_ip()  # fallback to IP if no user info
    else:
        event.deleted_by = "Unknown"

    db.session.commit()

    return jsonify({
        "success": True,
        "id": event_id
    })