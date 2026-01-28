from app import config, db
from app.forms import CategoryForm, ContactForm
from app.models import ContactCategory, Contact, ContactHeader, Employee, User
from app.cred import HR_EMAIL_ADDRESS
from app.utils import permission_required
from flask import abort, Blueprint, flash, jsonify, redirect, request, render_template, url_for
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
import subprocess

bp = Blueprint("directory", __name__, url_prefix="/directory")

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

# ---------- DIRECTORY ----------
@bp.route("edit/<type>")
@permission_required('directory+add')
def edit(type="contacts"):
    # Validate dir_type
    if type not in ("alumni", "contacts"):
        # Optionally return 404 if invalid
        abort(404)

    # Categories are based on type
    categories = ContactCategory.query.filter_by(type=type).order_by(
        ContactCategory.sort_order, ContactCategory.name
    ).all()

    category_map = {
        c.id: {"is_lab": c.is_lab} for c in categories
    }

    # Header can differ if needed
    header_type = "alumni" if type == "alumni" else "contacts"
    header = ContactHeader.query.filter_by(type=header_type).first()

    return render_template(
        "directory/list.html",
        type=type,
        categories=categories,
        header=header,
        category_map=category_map,
        admin=True
    )


# ---------- DIRECTORY ----------
@bp.route("list/<type>")
@permission_required('directory+add, committee+view')
def list(type="contacts"):
    # Validate dir_type
    if type not in ("alumni", "contacts"):
        # Optionally return 404 if invalid
        from flask import abort
        abort(404)

    # Categories are based on type
    categories = ContactCategory.query.filter_by(type=type).order_by(
        ContactCategory.sort_order, ContactCategory.name
    ).all()

    category_map = {
        c.id: {"is_lab": c.is_lab} for c in categories
    }

    # Header can differ if needed
    header_type = "alumni" if type == "alumni" else "contacts"
    header = ContactHeader.query.filter_by(type=header_type).first()

    return render_template(
        "directory/list.html",
        type=type,
        categories=categories,
        header=header,
        category_map=category_map,
        admin=False
    )

# -------------------------------
# Category List
# -------------------------------
@bp.route("/categories")
def categories():
    type = request.args.get("type", "contacts")
    categories = ContactCategory.query.filter_by(type=type).order_by(ContactCategory.sort_order, ContactCategory.name).all()
    csrf_token = generate_csrf()
    return render_template("directory/categories.html", categories=categories, type=type, csrf_token=csrf_token)

# -------------------------------
# New or Edit Category
# -------------------------------
@bp.route("/categories/modal", defaults={"category_id": None}, methods=["GET"])
@bp.route("/categories/modal/<int:category_id>", methods=["GET"])
def category_modal(category_id):
    type = request.args.get("type", "contacts")

    category = ContactCategory.query.filter_by(id=category_id, type=type).first() if category_id else None

    form = CategoryForm(obj=category)
    form.type.data = type

    if category and category.display_fields:
        form.display_fields.data = category.display_fields.split(",")
    return render_template("directory/category_modal.html", form=form, category=category)

@bp.route("/categories/save", methods=["POST"])
def save_category():
    category_id = request.form.get("category_id")
    type = request.form.get("type", "contacts")
    category = ContactCategory.query.get(category_id) if category_id else ContactCategory()
    category.type = type
    form = CategoryForm()

    # Validate and check duplicates
    if form.validate_on_submit():
        existing = ContactCategory.query.filter_by(name=form.name.data, type=type).first()
        if existing and (not category_id or existing.id != int(category_id)):
            return jsonify(
                success=False,
                errors={"name": ["A category with this name already exists."]}
            ), 400
        
        # Save category
        form.populate_obj(category)
        category.name = form.name.data.strip()
        category.display_fields = ",".join(form.display_fields.data or [])
        category.type = type

        if not category_id:
            db.session.add(category)

        db.session.commit()
        
        flash(
            "Category updated successfully." if category_id else "Category created successfully.",
            "success"
        )
    
        return jsonify(success=True)

    # Return validation errors
    return jsonify(success=False, errors=form.errors), 400

# -------------------------------
# Sort Category
# -------------------------------
@bp.route("/categories/reorder", methods=["POST"])
def reorder_categories():
    data = request.get_json()
    type = request.args.get("type", "contacts")

    for item in data:
        category = ContactCategory.query.filter_by(
            id=item["id"],
            type=type
        ).first()
        if category:
            category.sort_order = item["sort_order"]

    db.session.commit()
    return jsonify(success=True)


# -------------------------------
# Delete Category (hard delete OK)
# -------------------------------
@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
def category_delete(category_id):
    type = request.args.get("type", "contacts")
    category = ContactCategory.query.filter_by(
        id=category_id,
        type=type
    ).first_or_404()
    
    # Optional: prevent deleting categories that still have contacts
    if len(category.contacts) > 0:
        return jsonify({"error": "Category has contacts, cannot delete"}), 400
    
    db.session.delete(category)
    db.session.commit()
    return jsonify({"success": True, "message": "Category deleted successfully"})


# ---------- CONTACTS ----------
@bp.route("/contacts_modal", defaults={"category_id": None, "contact_id": None})
@bp.route("/contacts_modal/<int:category_id>", defaults={"contact_id": None})
@bp.route("/contacts_modal/<int:category_id>/<int:contact_id>")
def contact_modal(category_id, contact_id):
    contact = Contact.query.get(contact_id) if contact_id else None
    type = request.args.get("type", "contacts")

    form = ContactForm(obj=contact)
    category = ContactCategory.query.get(category_id) if category_id else None

    categories = ContactCategory.query.filter_by(
        type=type
    ).order_by(
        ContactCategory.sort_order,
        ContactCategory.name
    ).all()

    header = ContactHeader.query.filter_by(type=type).first()

    form.category_id.choices = [
        (c.id, c.name) for c in categories
    ]

    if category_id:
        form.category_id.data = category_id
    elif contact:
        form.category_id.data = contact.category_id

    form.type.data = type
    
    return render_template(
        "directory/contact_form-wizard.html",
        form=form,
        categories=categories,
        category=category,
        contact=contact,
        header=header
    )

@bp.route("/save", methods=["POST"])
@login_required
def save_contact():
    form = ContactForm()

    contact_id = request.form.get("contact_id")
    type = request.form.get("type", "contacts")

    category_id = form.category_id.data
    category = ContactCategory.query.get_or_404(category_id)

    categories = ContactCategory.query.filter_by(
        type=type
    ).order_by(
        ContactCategory.sort_order,
        ContactCategory.name
    ).all()

    header = ContactHeader.query.filter_by(type=type).first()

    form.category_id.choices = [
        (c.id, c.name) for c in categories
    ]

    if form.validate_on_submit():
        if form.first_name.data and form.last_name.data:
            existing = Contact.query.filter_by(first_name=form.first_name.data,last_name=form.last_name.data,is_active=True).first()
        else:
            existing = Contact.query.filter_by(group_name=form.group_name.data,is_active=True).first()
        
        if existing and (not contact_id or existing.id != int(contact_id)):
            return jsonify(
                success=False,
                errors={"first_name": ["A contact with this name already exists."],
                        "last_name": ["A contact with this name already exists."],
                        "group_name": ["A contact with this name already exists."]}
            ), 400
        
        if contact_id:
            contact = Contact.query.get_or_404(contact_id)
            form.populate_obj(contact)
        else:
            contact = Contact(category_id=category_id)
            form.populate_obj(contact)
            db.session.add(contact)

        db.session.commit()

        # -----------------------------------
        # Email notifications
        # -----------------------------------
        try:
            
            subject = f"New {category.name} Contact Added"

            body = render_template(
                "directory/email_contact.html",
                contact=contact,
                category=category,
                emailHR=form.emailHR.data,
                emailDSA=form.emailDSA.data,
                emailComms=form.emailComms.data,
                header=header
            )

            from_address = HR_EMAIL_ADDRESS

            recipients = []
            if form.emailDSA.data:
                recipients.append(header.dsa)
            if form.emailHR.data:
                recipients.append(header.hr)
            if form.emailComms.data:
                recipients.append(header.comms)

            if recipients:
                send_email_via_powershell(
                    to_address=",".join(recipients),
                    from_address=from_address,
                    subject=subject,
                    body=body
                )

        except Exception as e:
            flash(f"Contact saved, but email failed: {str(e)}", "warning")
            return redirect(url_for("contacts.categories"))

        flash(
            "Contact updated successfully." if contact_id else "Contact created successfully.",
            "success"
        )    

        return jsonify({
            "success": True,
            "message": "Contact saved successfully.",
            "category_id": category_id,
            "contact_id": contact.id
        })

    return jsonify(
        success=False,
        errors=form.errors
    ), 400

@bp.route("/<int:contact_id>/delete", methods=["POST"])
def delete_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    contact.is_active = False
    db.session.commit()

    return jsonify(success=True)


@bp.route("/save_pdf_header", methods=["POST"])
def save_pdf_header():
    data = request.json
    type = request.form.get("type", "contacts")

    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    # Either create new or update existing header (for simplicity, only one header row)
    header = ContactHeader.query.filter_by(type=type).first()

    if not header:
        header = ContactHeader()

    header.line1 = data.get("line1", "").strip()
    header.line2 = data.get("line2", "").strip()
    header.line3 = data.get("line3", "").strip()
    header.line4 = data.get("line4", "").strip()
    header.line5 = data.get("line5", "").strip()
    header.line6 = data.get("line6", "").strip()
    header.dsa = data.get("dsa", "")
    header.hr = data.get("hr", "")
    header.comms = data.get("comms", "")
    header.type = data.get("type", "contacts")    

    try:
        db.session.add(header)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("DB ERROR:", e)
        return jsonify({"success": False, "message": str(e)}), 500
    
    return jsonify({"success": True, "message": "Header saved successfully"})

# @login_required
def send_email_via_powershell(to_address, to_cc=None, from_address=None, subject=None, body=None, attachment_path=None):
    """Sends email using PowerShell's Send-MailMessage cmdlet."""
    print(to_address,  to_cc, from_address, subject, body, attachment_path)
    # Escape double quotes in the body so HTML isn’t broken
    safe_body = body.replace('"', '`"') if body else ""

    # Build PowerShell recipient arrays
    to_list = to_address.split(",") if to_address else []
    cc_list = []

    if to_cc:
        cc_list.append(to_cc)
    if from_address:
        cc_list.append(from_address)

    ps_to = ",".join(f'"{addr.strip()}"' for addr in to_list)
    ps_cc = ",".join(f'"{addr.strip()}"' for addr in cc_list)

    base_cmd = f'''
    Send-MailMessage `
        -From "{from_address}" `
        -To @({ps_to}) `
        -Cc @({ps_cc}) `
        -Subject "{subject}" `
        -Body "{safe_body}" `
        -BodyAsHtml `
        -SmtpServer "{config.MAIL_SERVER}" `
        -UseSsl
    '''

    if attachment_path:
        base_cmd += f' -Attachments "{attachment_path}"'

    completed = subprocess.run(
        ["powershell", "-Command", base_cmd],
        capture_output=True,
        text=True
    )

    if completed.returncode != 0:
        print("Error sending mail:", completed.stderr)
    else:
        print("Mail sent successfully")
