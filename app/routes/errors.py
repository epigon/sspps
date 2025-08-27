from flask import Blueprint, render_template

bp = Blueprint('errors', __name__, url_prefix='/errors')

@bp.errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html", message="You do not have permission to access this page."), 403
