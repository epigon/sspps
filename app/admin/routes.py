from app.utils import admin_required, permission_required, has_permission, is_admin
from app.forms import UserForm, RoleForm, PermissionForm
from app.models import User, Role, Permission, db, Employee
from collections import defaultdict
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash

from sqlalchemy.exc import IntegrityError

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
@admin_required
def before_request():
    pass

# Users
@admin_bp.route('/users/')
# @permission_required('user+view')
def users():
    all_users = User.query.filter_by(deleted=False).all()
    # Fetch all permissions
    all_permissions = Permission.query.filter_by(deleted=False).all()
    # Group by resource
    grouped_permissions = defaultdict(list)
    for perm in all_permissions:
        grouped_permissions[perm.resource].append(perm)
    return render_template('admin/users.html', users=all_users, permissions=all_permissions, grouped_permissions=grouped_permissions)

@admin_bp.route('/users/new', methods=['GET', 'POST'])
@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
# @permission_required('user+edit')
def edit_user(user_id=None):
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
                return render_template('admin/edit_user.html', form=form, grouped_permissions=grouped_permissions,
                                       selected_permissions=combined_permission_ids,
                                       role_permission_ids=role_permission_ids,
                                       user_permission_ids=user_permission_ids)

            user.username = selected_employee.username
            user.employee_id = selected_employee.employee_id
        else:
            user.employee_id = user.employee_id  # Keep existing link

        user.role_id = form.role_id.data
        user.permissions = Permission.query.filter_by(deleted=False).filter(Permission.id.in_(form.permissions.data)).all()

        db.session.add(user)
        db.session.commit()
        print("success")
        flash("User saved successfully.", "success")
        return redirect(url_for('admin.users'))
    else:
        print("Form errors:", form.errors)

    return render_template('admin/edit_user.html',
                           form=form,
                           grouped_permissions=grouped_permissions,
                           selected_permissions=combined_permission_ids,
                           role_permission_ids=role_permission_ids,
                           user_permission_ids=user_permission_ids, user=user)

@admin_bp.route('/users/<int:user_id>/delete')
# @permission_required('user+delete')
def delete_user(user_id):
    user = User.query.filter_by(id=user_id, deleted=False).first_or_404()
    user.deleted = True  # Set the  deleted flag
    user.delete_date = datetime.now()
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for('admin.users'))

# Roles
@admin_bp.route('/roles')
# @permission_required('role+view')
def roles():
    all_roles = Role.query.filter_by(deleted=False).all()
    # Fetch all permissions
    all_permissions = Permission.query.filter_by(deleted=False).all()
    # Group by resource
    grouped_permissions = defaultdict(list)
    for perm in all_permissions:
        grouped_permissions[perm.resource].append(perm)
    return render_template('admin/roles.html', roles=all_roles, permissions=all_permissions, grouped_permissions=grouped_permissions)

@admin_bp.route('/roles/new', methods=['GET', 'POST'])
@admin_bp.route('/roles/<int:role_id>/edit', methods=['GET', 'POST'])
# @permission_required('role+edit')
def edit_role(role_id=None):
    role = Role.query.filter_by(id=role_id, deleted=False).first() if role_id else Role()
    form = RoleForm(original_name=role.name if role.id else None, obj=role)
    all_permissions = Permission.query.filter_by(deleted=False).all()
    form.permissions.choices = [(p.id, f"{p.resource}:{p.action}") for p in all_permissions]

    grouped_permissions = defaultdict(list)
    for perm in all_permissions:
        grouped_permissions[perm.resource].append(perm)

    if form.validate_on_submit():
        role.name = form.name.data
        selected_ids = list(map(int, form.permissions.data))
        role.permissions = Permission.query.filter_by(deleted=False).filter(Permission.id.in_(selected_ids)).all()
        db.session.add(role)
        db.session.commit()
        flash("Role updated successfully.", "success")
        return redirect(url_for('admin.roles'))

    form.permissions.data = [p.id for p in role.permissions]
    return render_template('admin/edit_role.html', form=form, grouped_permissions=grouped_permissions)

@admin_bp.route('/roles/<int:role_id>/delete')
# @permission_required('role+delete')
def delete_role(role_id):
    role = Role.query.filter_by(id=role_id, deleted=False).first_or_404()
    
    # Check if any users are assigned to this role
    assigned_users = User.query.filter_by(role_id=role_id, deleted=False).count()
 
    if assigned_users > 0:
        flash("Cannot delete this role because it is currently assigned to one or more users.", "danger")
        return redirect(url_for('admin.roles'))

    role.deleted = True  # Set the  deleted flag
    role.delete_date = datetime.now()

    try:
        db.session.commit()
        flash("Role deleted.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("An error occurred while trying to delete the role.", "danger")
        
    return redirect(url_for('admin.roles'))

# Permissions
@admin_bp.route('/permissions')
# @permission_required('permission+view')
def permissions():
    all_perms = Permission.query.filter_by(deleted=False).order_by(Permission.resource).all()
    return render_template('admin/permissions.html', permissions=all_perms)

@admin_bp.route('/permissions/new', methods=['GET', 'POST'])
@admin_bp.route('/permissions/<int:perm_id>/edit', methods=['GET', 'POST'])
# @permission_required('permission+edit')
def edit_permission(perm_id=None):
    perm = Permission.query.filter_by(id=perm_id, deleted=False).first() if perm_id else Permission()
    form = PermissionForm(original_resource=perm.resource, original_action=perm.action, obj=perm)

    if form.validate_on_submit():
        form.populate_obj(perm)
        db.session.add(perm)
        db.session.commit()
        flash('Permission saved.', 'success')
        return redirect(url_for('admin.permissions'))
    return render_template('admin/edit_permission.html', form=form)

@admin_bp.route('/permissions/<int:perm_id>/delete')
# @permission_required('permission+delete')
def delete_permission(perm_id):
    perm = Permission.query.filter_by(id=perm_id, deleted=False).first_or_404()
    perm.deleted = True  # Set the  deleted flag
    perm.delete_date = datetime.now()
    db.session.commit()
    flash("Permission deleted.", "success")
    return redirect(url_for('admin.permissions'))

@admin_bp.route('/get_role_permissions')
def get_role_permissions():
    role_id = request.args.get('role_id', type=int)
    role = Role.query.filter_by(id=role_id, deleted=False).first()
    if not role:
        return jsonify(permission_ids=[])
    permission_ids = [perm.id for perm in role.permissions]
    return jsonify(permission_ids=permission_ids)