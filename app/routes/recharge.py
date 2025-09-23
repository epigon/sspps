from app import db
from app import config
# from app.email import send_email_via_powershell
from app.forms import InstrumentRequestForm
from app.models import Department, Employee, InstrumentRequest, Machine, MachineEvent, ProjectTaskCode, User
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

def aligned_to_15(dt: datetime) -> bool:
    return dt.minute % 15 == 0 and dt.second == 0 and dt.microsecond == 0

# --- Requestor form ---
@bp.route("/request_instrument/", methods=["GET", "POST"])
def request_instrument():
    form = InstrumentRequestForm()

    if form.validate_on_submit():
        machine = Machine.query.get(form.machine.data)
        
        req = InstrumentRequest(
            machine_name=machine.MachineName,
            machine_id=str(machine.MachineId),
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
@bp.route("/review_requests")
# @permission_required('screeningcore_approve+add')
def review_requests():

    # print(current_user.can("screeningcore_approve", "add"))
    status = request.args.get("status")
    machineID = request.args.get("machine")
    print("machine",request.args.get('machine'))
    query = InstrumentRequest.query

    if status:
        query = query.filter_by(status=status)
        
    if machineID:
        query = query.filter_by(machine_id=machineID)

    requests_list = query.order_by(InstrumentRequest.created_at.desc()).all()
    machines_list = Machine.query.filter_by(MachineStatus=True).order_by(Machine.MachineName).all()
    print(machines_list)
    for m in machines_list:
        print(m.MachineId, m.MachineName)
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

# @bp.route("/approve_request/<string:request_id>", methods=["POST"])
# @permission_required('screeningcore_approve+add')
# def approve_request(request_id):

#     req = InstrumentRequest.query.get_or_404(request_id)

#     # Update status
#     req.status = "Approved"
#     req.approved_at = datetime.now()
#     req.approved_by = current_user.username
#     req.notes = request.form.get("notes")  
#     db.session.commit()

#     # Reuse the email function
#     email_request_barcode(request_id)

#     flash(f"Request #{req.id} approved and barcode emailed to {req.requestor_email}.", "success")
#     return redirect(url_for("recharge.review_requests"))

# @bp.route("/deny_request/<string:request_id>", methods=["POST"])
# @permission_required('screeningcore_approve+add')
# def deny_request(request_id):

#     req = InstrumentRequest.query.get_or_404(request_id)

#     # Update status
#     req.status = "Denied"
#     req.approved_at = datetime.now()
#     req.approved_by = current_user.username
#     req.notes = request.form.get("notes")  
#     db.session.commit()

#     # Reuse the email function
#     # email_request_barcode(request_id)

#     flash(f"Request #{req.id} denied.", "success")
#     return redirect(url_for("recharge.review_requests"))

@bp.route("/email-request-barcode/<string:request_id>")
@permission_required('screeningcore_approve+add')
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
    body = (
        f"Hello,\n\nYour instrument request for {req.machine_name} has been approved.\n"
        "Your barcode is attached. Please keep it for your records.\n\n"
        f"Regards,\n{approver.employee_first_name} {approver.employee_last_name}"
    )

    send_email_via_powershell(recipients, cc, sender, subject, body, filename)

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
    
    ps_script = f'Send-MailMessage -From "{from_address}" -To "{to_address}" -Cc ("{to_cc}","{from_address}") -Subject "{subject}" -Body "{body}" -Attachments "{attachment_path}" -SmtpServer "{config.MAIL_SERVER}" -UseSsl'

    completed = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    if completed.returncode != 0:
        print("Error sending mail:", completed.stderr)
    else:
        print("Mail sent successfully")

@bp.route("/schedule")
def schedule():
    request_id = request.args.get("requestID")
    if not request_id:
        return "Missing requestID", 400

    instr_req = InstrumentRequest.query.get(request_id)
    if not instr_req:
        return "Invalid requestID", 404

    machine = Machine.query.get(instr_req.machine_id)
    if not machine:
        return "Machine not found", 404

    return render_template(
        "recharge/scheduler.html",
        machine=machine,
        request_id=request_id,
        instrument_request=instr_req
    )

@bp.route("/api/events", methods=["GET", "POST"])
def api_events():
    # ----------------- GET -----------------
    if request.method == "GET":
        request_id = request.args.get("requestID")
        if not request_id:
            return jsonify({"error": "missing requestID"}), 400

        instr_req = InstrumentRequest.query.get(request_id)
        if not instr_req:
            return jsonify({"error": "invalid requestID"}), 404

        events = MachineEvent.query.filter_by(machine_id=instr_req.machine_id).all()

        # FullCalendar expects fields: id, title, start, end, description
        return jsonify([
            {
                "id": e.id,
                "title": e.title,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "description": e.description
            } for e in events
        ])

    # ----------------- POST -----------------
    data = request.get_json() or {}
    request_id = data.get("requestID")
    if not request_id:
        return jsonify({"error": "missing requestID"}), 400

    instr_req = InstrumentRequest.query.get(request_id)
    if not instr_req:
        return jsonify({"error": "invalid requestID"}), 404

    machine = Machine.query.get(instr_req.machine_id)
    if not machine:
        return jsonify({"error": "invalid machine"}), 404

    title = data.get("title") or "Reserved"
    # Include both requestor name and request ID
    description = f"Requestor: {instr_req.requestor_name}\nRequest ID: {request_id}"

    try:
        new_start = datetime.fromisoformat(data["start"])
        new_end = datetime.fromisoformat(data["end"])
    except Exception:
        return jsonify({"error": "Invalid datetime format"}), 400

    # Validate duration & alignment
    duration_minutes = (new_end - new_start).total_seconds() / 60
    min_duration = max(15, int(machine.MinimumDuration or 15))
    if duration_minutes < min_duration:
        return jsonify({"error": f"Minimum duration is {min_duration} minutes"}), 400
    if duration_minutes % 15 != 0 or not aligned_to_15(new_start) or not aligned_to_15(new_end):
        return jsonify({"error": "Times must align to 15-minute increments"}), 400

    # Conflict check
    conflict = (MachineEvent.query
                .filter(MachineEvent.machine_id == machine.MachineId)
                .filter(MachineEvent.start < new_end, MachineEvent.end > new_start)
                .first())
    if conflict:
        return jsonify({"error": "Time conflict with existing event"}), 409

    # Save the new event
    ev = MachineEvent(
        machine_id=machine.MachineId,
        title=title,
        description=description,
        start=new_start,
        end=new_end
    )
    db.session.add(ev)
    db.session.commit()

    return jsonify({
        "id": ev.id,
        "title": ev.title,
        "start": ev.start.isoformat(),
        "end": ev.end.isoformat(),
        "description": ev.description
    }), 201