from app.emmaAPIAdapter import EmmaAPIAdapter
from app.utils import permission_required
from flask import render_template, request, Blueprint, jsonify, current_app
from flask_login import login_required, current_user

bp = Blueprint('emma', __name__, url_prefix='/emma')

adapter = EmmaAPIAdapter() 

# Routes to Webpages
@bp.before_request
def require_login():
    if not current_user.is_authenticated:
        # Force redirect instead of JSON 403
        return current_app.login_manager.unauthorized()

@bp.route('/groups', methods=['GET', 'POST'])
@permission_required('listserv+view')
def groups_page():
    groups = adapter.get_groups() or []
    # Sort alphabetically by group_name (case-insensitive)
    groups = sorted(groups, key=lambda g: g.get("group_name", "").lower())
    return render_template('emma/list_groups.html', groups=groups)

@bp.route("/groups/<int:group_id>/members")
@permission_required('listserv+view')
def group_members_page(group_id):
    group = next((g for g in adapter.get_groups() if g["member_group_id"] == group_id), None)
    return render_template("emma/list_members.html", group=group)

@bp.route("/api/groups/<int:group_id>/members")
def group_members_api(group_id):
    members = adapter.get_group_members(group_id) or []
    members = sorted(members, key=lambda m: (m.get("email") or "").lower())
    return jsonify(members)
