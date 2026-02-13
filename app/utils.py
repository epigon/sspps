from app.models import Member, Employee, AYCommittee
from flask_login import current_user
from flask import current_app, request, abort, jsonify, render_template, flash, redirect, url_for
from flask_login import current_user
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role.name.lower() != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permissions):
    """
    Decorator to protect routes by required permissions.

    permissions: str like "screeningcore_approve+add" or list of such strings.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                # User not logged in
                if request.accept_mimetypes.accept_json:
                    return jsonify({'success': False, 'message': 'Authentication required'}), 403
                return render_template("403.html", message="You must be logged in to access this page."), 403

            # Normalize permission list
            if isinstance(permissions, str):
                permission_list = [p.strip().lower() for p in permissions.split(',')]
            else:
                permission_list = [p.lower() for p in permissions]

            # Check if user has ANY of the required permissions
            for perm in permission_list:
                try:
                    resource, action = perm.split('+')
                    if current_user.can(resource.strip(), action.strip()):
                        # User has permission → allow access
                        return f(*args, **kwargs)
                except ValueError:
                    continue  # skip malformed permissions

            # User has no permission → handle gracefully
            if request.method == "POST":
                flash("You do not have permission to perform this action.", "danger")
                return redirect(request.referrer or url_for("main.home"))

            return render_template("errors/403.html", message="You do not have permission."), 403
        
        return decorated_function
    return decorator

def has_permission(permissions):
    if not current_user.is_authenticated:
        return False

    if isinstance(permissions, str):
        permission_list = [p.strip().lower() for p in permissions.split(',')]
    else:
        permission_list = [p.lower() for p in permissions]

    for perm in permission_list:
        try:
            resource, action = perm.split('+')
            if current_user.can(resource.strip(), action.strip()):
                return True
        except ValueError:
            continue  # Skip malformed permissions

    return False

def is_admin():
    return current_user.is_authenticated and current_user.role.name.lower() == "admin"

def can_edit_committee(ay_committee_id: int, action: str = "edit") -> bool:
    """
    Check if the current user can perform a specific action on a committee.
    action: "edit" or "delete"
    """
    if not current_user.is_authenticated:
        return False

    # ---- Global overrides ----
    if is_admin():
        return True

    # ---- Global permission checks ----
    if action == "delete":
        if has_permission("committee+delete"):
            return True
    elif action == "edit":
        if has_permission("committee+edit"):
            return True

    # ---- Local membership (allow_edit flag) ----
    if action == "edit":  # local delete not allowed, only edit
        member = Member.query.join(Employee).filter(
            Member.ay_committee_id == ay_committee_id,
            Member.deleted == False,
            Employee.employee_id == current_user.employee_id,
            Member.allow_edit == True
        ).first()
        if member:
            return True

    return False

# def committee_edit_required(action="edit"):
#     def decorator(f):
#         @wraps(f)
#         def decorated_function(*args, **kwargs):
#             ay_committee_id = kwargs.get("ay_committee_id") or request.form.get("ay_committee_id", type=int)
#             if not ay_committee_id or not can_edit_committee(ay_committee_id, action):
#                 if request.headers.get("X-Requested-With") == "XMLHttpRequest":
#                     return jsonify(success=False, message=f"You do not have permission to {action} this committee."), 403
#                 flash(f"You do not have permission to {action} this committee.", "danger")
#                 return redirect(request.referrer or url_for("committee.ay_committees"))
#             return f(*args, **kwargs)
#         return decorated_function
#     return decorator

def committee_edit_required(action="edit"):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ay_committee_id = kwargs.get("ay_committee_id") or request.form.get("ay_committee_id", type=int)
            if not ay_committee_id:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify(success=False, message="No committee specified."), 400
                flash("No committee specified.", "danger")
                return redirect(request.referrer or url_for("committee.ay_committees"))

            aycommittee = AYCommittee.query.filter_by(id=ay_committee_id, deleted=False).first()

            # 🚫 Check if committee is finalized
            if aycommittee and aycommittee.finalized:
                msg = (
                    f"This committee was finalized on "
                    f"{aycommittee.finalized_date.strftime('%Y-%m-%d') if aycommittee.finalized_date else 'a previous date'} "
                    f"by {aycommittee.finalized_user.username if aycommittee.finalized_user else 'an administrator'} "
                    f"and can no longer be modified."
                )
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify(success=False, message=msg), 403
                flash(msg, "warning")
                return redirect(request.referrer or url_for("committee.ay_committees"))

            # 🔒 Existing permission check
            if not can_edit_committee(ay_committee_id, action):
                msg = f"You do not have permission to {action} this committee."
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify(success=False, message=msg), 403
                flash(msg, "danger")
                return redirect(request.referrer or url_for("committee.ay_committees"))

            # ✅ All checks passed
            return f(*args, **kwargs)
        return decorated_function
    return decorator