from app import db
from app import config
# from app.email import send_email_via_powershell
from app.forms import InstrumentRequestForm
from app.models import Department, Employee, InstrumentRequest, Instrument, ProjectTaskCode, User
from app.utils import permission_required
from datetime import datetime, timedelta
from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for, render_template_string
from flask_login import login_required, current_user
from PIL import Image, ImageDraw, ImageFont
import io
import os
import qrcode
import subprocess
import tempfile

bp = Blueprint('recharge', __name__, url_prefix='/recharge')

@bp.before_request
def before_request():
    excluded_endpoints = ['recharge.request_instrument']  # full endpoint name: blueprint_name.view_function_name
    if request.endpoint in excluded_endpoints:
        return  # Skip login_required check
    return login_required(lambda: None)()  # Call login_required manually

def aligned_to_15(dt: datetime) -> bool:
    return dt.minute % 15 == 0 and dt.second == 0 and dt.microsecond == 0

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
        # flash("Your request has been submitted for review.", "success")
        # return redirect(url_for("recharge.request_instrument"))
    return render_template("recharge/request_instrument.html", form=form, request_data=request_data)

# --- Reviewer list ---
@bp.route("/review_requests")
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
