from app.utils import admin_required
from app.forms import  PermissionForm
from app.models import Role, Permission, db
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash

bp = Blueprint('permissions', __name__, url_prefix='/permissions')

@bp.before_request
@admin_required
def before_request():
    pass

# Permissions
@bp.route('/list_permissions')
# @permission_required('permission+view')
def list_permissions():
    all_perms = Permission.query.filter_by(deleted=False).order_by(Permission.resource).all()
    return render_template('permissions/list.html', permissions=all_perms)

@bp.route('/new', methods=['GET', 'POST'])
@bp.route('/<int:perm_id>/edit', methods=['GET', 'POST'])
# @permission_required('permission+edit')
def edit(perm_id=None):
    perm = Permission.query.filter_by(id=perm_id, deleted=False).first() if perm_id else Permission()
    form = PermissionForm(original_resource=perm.resource, original_action=perm.action, obj=perm)

    if form.validate_on_submit():
        form.populate_obj(perm)
        db.session.add(perm)
        db.session.commit()
        flash('Permission saved.', 'success')
        return redirect(url_for('permissions.list_permissions'))
    return render_template('permissions/form.html', form=form)

@bp.route('/<int:perm_id>/delete')
# @permission_required('permission+delete')
def delete(perm_id):
    perm = Permission.query.filter_by(id=perm_id, deleted=False).first_or_404()
    perm.deleted = True  # Set the  deleted flag
    perm.delete_date = datetime.now()
    db.session.commit()
    flash("Permission deleted.", "success")
    return redirect(url_for('permissions.list_permissions'))

@bp.route('/get_role_permissions')
def get_role_permissions():
    role_id = request.args.get('role_id', type=int)
    role = Role.query.filter_by(id=role_id, deleted=False).first()
    if not role:
        return jsonify(permission_ids=[])
    permission_ids = [perm.id for perm in role.permissions]
    return jsonify(permission_ids=permission_ids)