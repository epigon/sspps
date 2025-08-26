from app import db
from app.email import send_email_via_powershell
from app.forms import InstrumentRequestForm
from app.models import Department, Employee, InstrumentRequest, Machine, ProjectTaskCode, User
from app.utils import permission_required
from datetime import datetime, timedelta
from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for 
from flask_login import login_required, current_user
import io
import os
import qrcode

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
    filename = f"{req.id}.png"
    qrcode.make(payload).save(filename)

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
    try:
        os.remove(filename)
    except OSError as e:
        print(f"Error deleting file {filename}: {e}")

    return req

@permission_required('screeningcore_approve+add')
@bp.route("/resend-email/<string:request_id>")
def resend_email(request_id):
    req = email_request_barcode(request_id)
    flash(f"Request #{req.id} barcode emailed to {req.requestor_email}.", "success")
    return redirect(url_for("recharge.review_requests"))