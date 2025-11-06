from app.utils import admin_required
from app.forms import UserForm
from app.models import User, Role, Permission, db, Employee
from collections import defaultdict
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash
from flask_login import login_required, current_user

bp = Blueprint('users', __name__, url_prefix='/users')

@bp.before_request
@admin_required
def before_request():
    pass

# Users
@bp.route('/list_users')
# @permission_required('user+view')
def list_users():
    all_users = User.query.filter_by(deleted=False).all()
    # Fetch all permissions
    all_permissions = Permission.query.filter_by(deleted=False).all()
    # Group by resource
    grouped_permissions = defaultdict(list)
    print(grouped_permissions)
    for perm in all_permissions:
        grouped_permissions[perm.resource].append(perm)
    return render_template('users/list.html', users=all_users, permissions=all_permissions, grouped_permissions=grouped_permissions)

@bp.route('/new', methods=['GET', 'POST'])
@bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
# @permission_required('user+edit')
def edit(user_id=None):
    user = User.query.filter_by(id=user_id, deleted=False).first() if user_id else User()

    all_permissions = Permission.query.filter_by(deleted=False).all()
    all_roles = Role.query.filter_by(deleted=False).all()
    existing_usernames = {u.username for u in User.query.with_entities(User.username).filter_by(deleted=False)}
    employees = Employee.query.all()

    form = UserForm(
        original_username=user.username if user.id else None,
        obj=user,
        existing_usernames=existing_usernames,
        employees=employees
    )

    form.role_id.choices = [(r.id, r.name) for r in all_roles]
    form.permissions.choices = [(p.id, f"{p.resource}:{p.action}") for p in all_permissions]

    role_permission_ids = set(p.id for p in user.role.permissions) if user.role else set()
    user_permission_ids = set(p.id for p in user.permissions)
    combined_permission_ids = role_permission_ids.union(user_permission_ids)
    
    if request.method == 'GET' and user.id:
        form.permissions.data = list(combined_permission_ids)

    # Group permissions by resource for table layout
    grouped_permissions = defaultdict(list)
    for perm in all_permissions:
        grouped_permissions[perm.resource].append(perm)

    if form.validate_on_submit():                
        if not user.id:
            selected_employee = Employee.query.get(form.employee_id.data)
            if not selected_employee or selected_employee.username in existing_usernames:
                flash("Invalid or already-used employee selected.", "danger")
                return render_template('users/form.html', form=form, grouped_permissions=grouped_permissions,
                                       selected_permissions=combined_permission_ids,
                                       role_permission_ids=role_permission_ids,
                                       user_permission_ids=user_permission_ids)

            user.username = selected_employee.username
            user.employee_id = selected_employee.employee_id
            user.create_date = datetime.now()
            user.create_by =  current_user.id
        else:
            user.employee_id = user.employee_id  # Keep existing link
            user.modify_date = datetime.now()
            user.modify_by = current_user.id

        user.role_id = form.role_id.data
        user.permissions = Permission.query.filter_by(deleted=False).filter(Permission.id.in_(form.permissions.data)).all()

        db.session.add(user)
        db.session.commit()
        print("success")
        flash("User saved successfully.", "success")
        return redirect(url_for('users.list_users'))
    else:
        print("Form errors:", form.errors)

    return render_template('users/form.html',
                           form=form,
                           grouped_permissions=grouped_permissions,
                           selected_permissions=combined_permission_ids,
                           role_permission_ids=role_permission_ids,
                           user_permission_ids=user_permission_ids, user=user)

@bp.route('/<int:user_id>/delete')
# @permission_required('user+delete')
def delete(user_id):
    user = User.query.filter_by(id=user_id, deleted=False).first_or_404()
    user.deleted = True  # Set the  deleted flag
    user.delete_date = datetime.now()
    user.delete_by = current_user.id
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for('users.list_users'))
