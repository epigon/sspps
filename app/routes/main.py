from app.models import User, Employee
from flask import session, Blueprint, render_template, request, redirect, url_for, flash, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user

bp = Blueprint('main', __name__, template_folder='templates')

@bp.route("/")
@bp.route("/home/")
def home():    
    return render_template("main/home.html")

@bp.route("/profile/")
@login_required
def profile():  
    user = User.query.filter_by(username=current_user.username, deleted=False).first()
    if user and hasattr(user.employee, 'reports_to_id') and user.employee.reports_to_id:
        supervisor = Employee.query.filter_by(employee_id=user.employee.reports_to_id).first()
    else:
        supervisor = Employee()
    return render_template("main/profile.html", user=user.employee.to_dict(include_labels=True), supervisor=supervisor.to_dict())

@bp.route('/sso-redirect')
def sso_redirect():
    next_url = request.args.get('next')
    secure_url = url_for('main.secure', _external=True)
    if next_url:
        secure_url += f'?next={next_url}'
    return redirect(secure_url)

@bp.route("/secure/")
# @bp.route('/login/')
def secure():
    try:

        """Handles Shibboleth login and user session"""
        host = request.headers['Host']
    
        if host == "127.0.0.1:5000":
            # user_ad = "e1flastname"
            user_ad = "epigon"
        else:
            user_ad = request.environ.get("ADUSERNAME")
                    
        if not user_ad:
            return "Access denied: No Shibboleth authentication detected", 403
        
        user = User.query.filter_by(username=user_ad, deleted=False).first()

        if user:
                                    
            login_user(user)
            # Print role and user permissions to debug -- only for testing permissions
            # print("== User Permissions ==")
            # if user.role:
            #     print(f"Role: {user.role.name}")
            #     for p in user.role.permissions:
            #         print(f"Role Permission: {p.resource}:{p.action}")
            # for p in user.permissions:
            #     print(f"User Permission: {p.resource}:{p.action}")

            return redirect(url_for("main.home"))
        flash("You are not authorized to use this site.", "danger")
        # return 'User not found', 404
        return render_template("home.html")
    
    except Exception as e:
        return f"Error: {str(e)}", 500    

@bp.route('/logout/')
@login_required
def logout():    
    print(f"User before: {current_user.get_id()}, {current_user.is_authenticated}")
    logout_user()
    session.clear()
    print(f"---Logout, user authenticated? {current_user.is_authenticated}, {current_user.get_id()}")

    host = request.headers['Host']
    
    if host == "127.0.0.1:5000":
        redirect_url = url_for('main.home')
    else:
        redirect_url = "/Shibboleth.sso/Logout?return=https://a5.ucsd.edu/tritON/logout?target=https://"+host+url_for('main.home')
    return redirect(redirect_url)

@bp.route('/calendars/<path:filename>')
def serve_calendar_file(filename):
    return send_from_directory('static/calendars', filename)

@bp.route('/favicon.ico')
def favicon():
    return send_from_directory(
        'static',
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )