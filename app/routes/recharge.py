from app import config, db
from app.forms import InstrumentRequestForm
from app.models import Department, Employee, InstrumentRequest, Machine, User
from datetime import datetime, timedelta
from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for 
from flask_login import login_required, current_user
import io
import os
import qrcode
import subprocess

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

        start = form.start_datetime.data
        end = form.end_datetime.data

        # Validation: end must be later than start
        if end <= start:
            flash("End datetime must be later than start datetime.", "danger")
            return render_template('instrument_request.html', form=form)

        # Validation: must meet minimum duration
        min_delta = timedelta(minutes=machine.MinimumDuration)
        if (end - start) < min_delta:
            flash(f"End datetime must be at least {machine.MinimumDuration} minutes after start.", "danger")
            return render_template('recharge/request_instrument.html', form=form)
        
        req = InstrumentRequest(
            instrument_name=machine.MachineName,
            instrument_id=str(machine.MachineId),
            department_code=form.department_code.data,
            pi_name=form.pi_name.data,
            pi_email=form.pi_email.data,
            pi_phone=form.pi_phone.data,
            ad_username=form.ad_username.data,
            requestor_position=form.requestor_position.data,
            requestor_email=form.requestor_email.data,
            requestor_phone=form.requestor_phone.data,
            requires_training=form.requires_training.data,
            project_number=form.project_number.data,
            task_code=form.task_code.data,
            start_datetime=form.start_datetime.data,
            end_datetime=form.end_datetime.data
        )
        db.session.add(req)
        db.session.commit()
        flash("Your request has been submitted for review.", "success")
        return redirect(url_for("recharge.request_instrument"))
    return render_template("recharge/request_instrument.html", form=form)

# --- Reviewer list ---
@bp.route("/review_requests")
def review_requests():
    status = request.args.get("status")
    query = InstrumentRequest.query

    if status:
        query = query.filter_by(status=status)

    requests_list = query.order_by(InstrumentRequest.created_at.desc()).all()
    return render_template("recharge/review_requests.html", requests=requests_list)

@bp.route("/approve-request/<int:request_id>")
def approve_request(request_id):

    req = InstrumentRequest.query.get_or_404(request_id)

    # Update status
    req.status = "Approved"
    req.approved_at = datetime.now()
    req.approved_by = current_user.username
    db.session.commit()

    # Reuse the email function
    email_request_barcode(request_id)

    flash(f"Request #{req.id} approved and barcode emailed to {req.requestor_email}.", "success")
    return redirect(url_for("recharge.review_requests"))

@bp.route("/email-request-barcode/<int:request_id>")
def email_request_barcode(request_id):

    """Generates barcode and sends it via email."""
    req = InstrumentRequest.query.get_or_404(request_id)
    user = User.query.filter_by(id=current_user.id, deleted=False).first()
    approver = Employee.query.filter_by(employee_id=user.employee_id).first()

    # Create barcode image in memory
    payload = f"{req.ad_username}&{req.instrument_id}&{req.project_number}&{req.task_code}"
    filename = f"{req.ad_username}.png"
    qrcode.make(payload).save(filename)

    # Send email with barcode
    subject = f"{req.instrument_name} Request Approved"
    recipients = req.requestor_email
    cc = req.pi_email
    sender = approver.email
    body = (
        f"Hello,\n\nYour instrument request for {req.instrument_name} on "
        f"{req.start_datetime.strftime('%m/%d/%Y %I:%M %p').lower()} - "
        f"{req.end_datetime.strftime('%m/%d/%Y %I:%M %p').lower()} has been approved.\n"
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

@bp.route("/resend-email/<int:request_id>")
def resend_email(request_id):
    req = email_request_barcode(request_id)
    flash(f"Request #{req.id} barcode emailed to {req.requestor_email}.", "success")
    return redirect(url_for("recharge.review_requests"))

def send_email_via_powershell(to_address, to_cc, from_address, subject, body, attachment_path):
    ps_script = f'Send-MailMessage -From "{from_address}" -To "{to_address}" -Cc ("{to_cc}","{from_address}") -Subject "{subject}" -Body "{body}" -Attachments "{attachment_path}" -SmtpServer "{config.MAIL_SERVER}" -UseSsl'

    completed = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    if completed.returncode != 0:
        print("Error sending mail:", completed.stderr)
    else:
        print("Mail sent successfully")