from flask_login import current_user
from flask import current_app, request, abort, jsonify, render_template, flash, redirect, url_for
from flask_login import current_user
from functools import wraps

# def role_or_permission_required(roles, permissions):
#     def decorator(f):
#         @wraps(f)
#         def decorated_function(*args, **kwargs):
#             if not has_role_or_permission(roles, permissions):
#                 abort(403)
#             return f(*args, **kwargs)
#         return decorated_function
#     return decorator

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

# def role_required(role_name):
#     def decorator(f):
#         @wraps(f)
#         def decorated_function(*args, **kwargs):
#             if not current_user.is_authenticated or current_user.role.name.lower() != role_name.lower():
#                 abort(403)
#             return f(*args, **kwargs)
#         return decorated_function
#     return decorator

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

# def has_role(role_name):
#     return current_user.is_authenticated and current_user.role.name.lower() == role_name.lower()

def is_admin():
    return current_user.is_authenticated and current_user.role.name.lower() == "admin"

# def has_role_or_permission(roles, permissions):
#     if not current_user.is_authenticated:
#         return False

#     # Normalize input
#     if isinstance(roles, str):
#         roles = [r.strip().lower() for r in roles.split(',')]
#     else:
#         roles = [r.lower() for r in roles]

#     if isinstance(permissions, str):
#         permissions = [p.strip().lower() for p in permissions.split(',')]
#     else:
#         permissions = [p.lower() for p in permissions]

#     user_role = current_user.role.name.lower()

#     if user_role in roles:
#         return True

#     for perm in permissions:
#         try:
#             resource, action = perm.split('/')
#             if current_user.can(resource.strip(), action.strip()):
#                 return True
#         except ValueError:
#             continue  # Skip malformed permission

#     return False
