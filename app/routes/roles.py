from app.utils import admin_required
from app.forms import RoleForm
from app.models import User, Role, Permission, db
from collections import defaultdict
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash

from sqlalchemy.exc import IntegrityError

bp = Blueprint('roles', __name__, url_prefix='/roles')

@bp.before_request
@admin_required
def before_request():
    pass

# Roles
@bp.route('/list_roles')
# @permission_required('role+view')
def list_roles():
    all_roles = Role.query.filter_by(deleted=False).all()
    # Fetch all permissions
    all_permissions = Permission.query.filter_by(deleted=False).all()
    # Group by resource
    grouped_permissions = defaultdict(list)
    for perm in all_permissions:
        grouped_permissions[perm.resource].append(perm)
    return render_template('roles/list.html', roles=all_roles, permissions=all_permissions, grouped_permissions=grouped_permissions)

@bp.route('/new', methods=['GET', 'POST'])
@bp.route('/<int:role_id>/edit', methods=['GET', 'POST'])
# @permission_required('role+edit')
def edit(role_id=None):
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
        return redirect(url_for('roles.list_roles'))

    form.permissions.data = [p.id for p in role.permissions]
    return render_template('roles/form.html', form=form, grouped_permissions=grouped_permissions)

@bp.route('/<int:role_id>/delete')
# @permission_required('role+delete')
def delete(role_id):
    role = Role.query.filter_by(id=role_id, deleted=False).first_or_404()
    
    # Check if any users are assigned to this role
    assigned_users = User.query.filter_by(role_id=role_id, deleted=False).count()
 
    if assigned_users > 0:
        flash("Cannot delete this role because it is currently assigned to one or more users.", "danger")
        return redirect(url_for('roles.list_roles'))

    role.deleted = True  # Set the  deleted flag
    role.delete_date = datetime.now()

    try:
        db.session.commit()
        flash("Role deleted.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("An error occurred while trying to delete the role.", "danger")
        
    return redirect(url_for('roles.list_roles'))