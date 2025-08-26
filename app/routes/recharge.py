from app import db
from app import config
# from app.email import send_email_via_powershell
from app.forms import InstrumentRequestForm
from app.models import Department, Employee, InstrumentRequest, Machine, ProjectTaskCode, User
from app.utils import permission_required
from datetime import datetime, timedelta
from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for 
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

# --- Requestor form ---
@bp.route("/request_instrument/", methods=["GET", "POST"])
def request_instrument():
    form = InstrumentRequestForm()

    if form.validate_on_submit():
        machine = Machine.query.get(form.instrument.data)
        
        req = InstrumentRequest(
            instrument_name=machine.MachineName,
            instrument_id=str(machine.MachineId),
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
        flash("Your request has been submitted for review.", "success")
        return redirect(url_for("recharge.request_instrument"))
    return render_template("recharge/request_instrument.html", form=form)

# --- Reviewer list ---
@permission_required('screeningcore_approve+add')
@bp.route("/review_requests")
def review_requests():
    status = request.args.get("status")
    query = InstrumentRequest.query

    if status:
        query = query.filter_by(status=status)

    requests_list = query.order_by(InstrumentRequest.created_at.desc()).all()
    return render_template("recharge/review_requests.html", requests=requests_list)

@permission_required('screeningcore_approve+add')
@bp.route("/approve-request/<string:request_id>", methods=["POST"])
def approve_request(request_id):

    req = InstrumentRequest.query.get_or_404(request_id)

    # Update status
    req.status = "Approved"
    req.approved_at = datetime.now()
    req.approved_by = current_user.username
    req.notes = request.form.get("notes")  
    db.session.commit()

    # Reuse the email function
    email_request_barcode(request_id)

    flash(f"Request #{req.id} approved and barcode emailed to {req.requestor_email}.", "success")
    return redirect(url_for("recharge.review_requests"))

@permission_required('screeningcore_approve+add')
@bp.route("/email-request-barcode/<string:request_id>")
def email_request_barcode(request_id):

    """Generates barcode and sends it via email."""
    req = InstrumentRequest.query.get_or_404(request_id)
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
    
    title_text = f"{req.requestor_name} - {req.instrument_name}"

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
    subject = f"{req.instrument_name} Request Approved"
    recipients = req.requestor_email
    cc = req.pi_email
    sender = approver.email
    body = (
        f"Hello,\n\nYour instrument request for {req.instrument_name} has been approved.\n"
        "Your barcode is attached. Please keep it for your records.\n\n"
        f"Regards,\n{approver.employee_first_name} {approver.employee_last_name}"
    )

    send_email_via_powershell(recipients, cc, sender, subject, body, filename)

    # Delete barcode file
    # try:
    #     os.remove(filename)
    # except OSError as e:
    #     print(f"Error deleting file {filename}: {e}")

    return req

@permission_required('screeningcore_approve+add')
@bp.route("/resend-email/<string:request_id>")
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
    
    ps_script = f'Send-MailMessage -From "{from_address}" -To "{to_address}" -Cc ("{to_cc}","{from_address}") -Subject "{subject}" -Body "{body}" -Attachments "{attachment_path}" -SmtpServer "{config.MAIL_SERVER}" -UseSsl'

    completed = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    if completed.returncode != 0:
        print("Error sending mail:", completed.stderr)
    else:
        print("Mail sent successfully")