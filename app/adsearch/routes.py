from app.models import db
from app.utils import permission_required
from datetime import datetime, timedelta
from flask import render_template, request, Blueprint
from flask_login import login_required
from sqlalchemy import text
import pyodbc

adsearch_bp = Blueprint('adsearch', __name__, url_prefix='/adsearch')

# Routes to Webpages
@adsearch_bp.before_request
@login_required
def before_request():
    pass

def is_active(user_account_control):
    # Bitwise check: if 0x2 is set, account is disabled
    return not (user_account_control & 2)

def convert_windows_time(windows_time):
    try:
        if windows_time in (0, None):
            return "None"
        return (datetime(1601, 1, 1) + timedelta(microseconds=int(windows_time) / 10)).strftime('%Y-%m-%d')
    except:
        return "None"

def extract_ou(distinguished_name, keyword):
    # Try to extract the OU matching keyword (case-insensitive)
    parts = distinguished_name.split(',')
    for part in parts:
        if part.strip().lower().startswith(f'ou={keyword.lower()}'):
            return part.strip()
    return ''

@adsearch_bp.route('/search', methods=['GET', 'POST'])
@permission_required('adsearch+view')
def search():
    results = []
    if request.method == 'POST':
        firstname = request.form.get('firstname', '').strip()
        lastname = request.form.get('lastname', '').strip()
        username = request.form.get('username', '').strip()

        where_clauses = ["objectCategory = ''Person''", "objectClass = ''user''"]
        if firstname:
            where_clauses.append(f"givenName = ''*{firstname}*''")
        if lastname:
            where_clauses.append(f"sn = ''*{lastname}*''")
        if username:
            where_clauses.append(f"sAMAccountName = ''{username}*''")

        where_sql = " AND ".join(where_clauses)
        
        sql = text(f"""
            SELECT sAMAccountName, displayName, userAccountControl, accountExpires,
                   employeeID, distinguishedName
            FROM OPENQUERY(ADSI, '
                SELECT sAMAccountName, displayName, userAccountControl, accountExpires,
                       employeeID, distinguishedName
                FROM ''LDAP://ldap.ad.ucsd.edu/DC=AD,DC=UCSD,DC=EDU''
                WHERE {where_sql}
            ')
        """)

        try:
            query_result = db.session.execute(sql).fetchall()
            for row in query_result:
                # Check if user is in DUO group
                duo_clauses = ["objectCategory = ''Person''", "objectClass = ''user''", f"sAMAccountName = ''{row.sAMAccountName}''"]
                where_sql = " AND ".join(duo_clauses)
                duosql = text(f"""
                    SELECT sAMAccountName
                    FROM OPENQUERY(ADSI, '
                        SELECT sAMAccountName
                        FROM ''LDAP://ldap.ad.ucsd.edu/DC=AD,DC=UCSD,DC=EDU''
                        WHERE {where_sql}
                        AND memberOf = ''CN=HS-DUO-USERS,OU=Groups,OU=Global Resources,OU=UCSD Healthcare,DC=AD,DC=UCSD,DC=EDU''
                    ')
                """)
                duo_result = db.session.execute(duosql).fetchone()
                is_duo = duo_result is not None
                sopsql = text(f"""
                    SELECT sAMAccountName
                    FROM OPENQUERY(ADSI, '
                        SELECT sAMAccountName
                        FROM ''LDAP://ldap.ad.ucsd.edu/DC=AD,DC=UCSD,DC=EDU''
                        WHERE {where_sql}
                        AND memberOf = ''CN=FOL_AHS-SOPPS-PHARMACY_EDUCATION-RW,OU=DFS Groups,OU=Groups,OU=AHS,OU=UCSD Healthcare,DC=AD,DC=UCSD,DC=EDU''
                    ')
                """)
                sop_result = db.session.execute(sopsql).fetchone()
                is_sop = sop_result is not None
                # print("duo_result",duo_result)
                results.append({
                    'Username': row.sAMAccountName,
                    'Name': row.displayName,
                    'Active': 'Yes' if is_active(row.userAccountControl) else 'No',
                    'Exp': convert_windows_time(row.accountExpires),
                    'Emp ID': row.employeeID,
                    'DN': row.distinguishedName,
                    'HC OU': 'Yes' if extract_ou(row.distinguishedName, 'UCSD Healthcare') else 'No',
                    'SOP OU': 'Yes' if is_sop else 'No',
                    'DUO': 'Yes' if is_duo else 'No'
                })
        except Exception as e:
            print("LDAP query failed:", e)

    return render_template('adsearch/search.html', results=results)