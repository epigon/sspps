from app.models import db
from app.cred import LDAP_USER, LDAP_PASSWORD
from app.utils import permission_required
from datetime import datetime, timedelta
from flask import render_template, request, Blueprint
from flask_login import login_required
from ldap3 import Server, Connection, ALL, SUBTREE

bp = Blueprint('ad_lookup', __name__, url_prefix='/ad_lookup')

LDAP_SERVER = 'ldap.ad.ucsd.edu'
BASE_DN = 'DC=AD,DC=UCSD,DC=EDU'

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

def is_active(uac):
    # Bitmask: 2 = account disabled
    return 'Yes' if uac is not None and not (int(uac) & 2) else 'No'

def convert_windows_time(windows_time):
    try:
        if windows_time in (None, '0', 0, '9223372036854775807'):
            return 'Never'
        microseconds = int(windows_time) / 10
        return (datetime(1601, 1, 1) + timedelta(microseconds=microseconds)).strftime('%Y-%m-%d')
    except Exception:
        return 'Invalid'

def extract_ou(distinguished_name, keyword):
    # Try to extract the OU matching keyword (case-insensitive)
    parts = distinguished_name.split(',')
    for part in parts:
        if part.strip().lower().startswith(f'ou={keyword.lower()}'):
            return part.strip()
    return ''

@bp.route('/search', methods=['GET', 'POST'])
@permission_required('ad_lookup+view')
def search():

    searchterms = '+'.join(filter(None, [
        request.form.get('username', '').strip(),
        request.form.get('partialusername', '').strip(),
        request.form.get('firstname', '').strip(),
        request.form.get('lastname', '').strip()
    ]))

    custom_breadcrumbs = [
        {'name': 'Active Directory Search', 'url': '/ad_lookup/search'},
        {'name': f'Search Results for: {searchterms}', 'url': '/ad_lookup/search'}
    ]

    results = []
    error = None
    searched = False

    if request.method == 'POST':
        searched = True  # User submitted form
        username = request.form.get('username', '').strip()
        partialusername = request.form.get('partialusername', '').strip()
        firstname = request.form.get('firstname', '').strip()
        lastname = request.form.get('lastname', '').strip()

        # Build LDAP filter
        filters = ['(objectClass=user)']
        if username:
            filters.append(f'(sAMAccountName={username})')
        if partialusername:
            filters.append(f'(sAMAccountName=*{partialusername}*)')
        if firstname:
            filters.append(f'(givenName=*{firstname}*)')
        if lastname:
            filters.append(f'(sn=*{lastname}*)')

        ldap_filter = '(&' + ''.join(filters) + ')'

        try:
            server = Server(LDAP_SERVER, get_info=ALL)
            conn = Connection(server, user=LDAP_USER, password=LDAP_PASSWORD, auto_bind=True)
            conn.search(
                BASE_DN,
                ldap_filter,
                search_scope=SUBTREE,
                attributes=[
                    'sAMAccountName', 'displayName', 'userAccountControl',
                    'accountExpires', 'employeeID', 'distinguishedName',
                    'givenName', 'sn', 'memberOf'
                ]
            )
            for entry in conn.entries:
                print(entry)
                attr = entry.entry_attributes_as_dict
                member_of = attr.get('memberOf', [])

                def in_group(dn_fragment):
                    return any(dn_fragment in group_dn for group_dn in member_of)
                
                results.append({
                    'Username': attr.get('sAMAccountName', [''])[0],
                    'Name': attr.get('displayName', [''])[0],
                    'Active': is_active(attr.get('userAccountControl', [0])[0]),
                    'Exp': convert_windows_time(attr.get('accountExpires', [0])[0]),
                    'Emp ID': attr.get('employeeID', [''])[0] if attr.get('employeeID') else '',
                    # 'UCOP Emp ID': attr.get('ucpathEmplID', [''])[0] if attr.get('ucpathEmplID') else '',
                    # 'PID': attr.get('PID', [''])[0] if attr.get('PID') else '',
                    'DN': attr.get('distinguishedName', [''])[0],
                    'HC OU': 'Yes' if 'UCSD Healthcare' in attr.get('distinguishedName', [''])[0] else 'No',
                    'SOP OU': 'Yes' if in_group('FOL_AHS-SOPPS-PHARMACY_EDUCATION-RW') else 'No',
                    'HS DUO': 'Yes' if in_group('HS-DUO-USERS') else 'No'
                })
            conn.unbind()
        except Exception as e:
            error = str(e)

    # print(results)
    return render_template('ad_lookup/search.html', results=results, error=error, searched=searched, breadcrumbs=custom_breadcrumbs)

#"""Using ADSI LDAP Linked Server"""
# def search():
#     results = []
#     searched = False
#     if request.method == 'POST':
#         searched = True
#         firstname = request.form.get('firstname', '').strip()
#         lastname = request.form.get('lastname', '').strip()
#         username = request.form.get('username', '').strip()

#         where_clauses = ["objectCategory = ''Person''", "objectClass = ''user''"]
#         if firstname:
#             where_clauses.append(f"givenName = ''*{firstname}*''")
#         if lastname:
#             where_clauses.append(f"sn = ''*{lastname}*''")
#         if username:
#             where_clauses.append(f"sAMAccountName = ''{username}*''")

#         where_sql = " AND ".join(where_clauses)
        
#         sql = text(f"""
#             SELECT sAMAccountName, displayName, userAccountControl, accountExpires,
#                    employeeID, distinguishedName
#             FROM OPENQUERY(ADSI, '
#                 SELECT sAMAccountName, displayName, userAccountControl, accountExpires,
#                        employeeID, distinguishedName
#                 FROM ''LDAP://ldap.ad.ucsd.edu/DC=AD,DC=UCSD,DC=EDU''
#                 WHERE {where_sql}
#             ')
#         """)

#         try:
#             query_result = db.session.execute(sql).fetchall()
#             for row in query_result:
#                 # Check if user is in DUO group
#                 duo_clauses = ["objectCategory = ''Person''", "objectClass = ''user''", f"sAMAccountName = ''{row.sAMAccountName}''"]
#                 where_sql = " AND ".join(duo_clauses)
#                 duosql = text(f"""
#                     SELECT sAMAccountName
#                     FROM OPENQUERY(ADSI, '
#                         SELECT sAMAccountName
#                         FROM ''LDAP://ldap.ad.ucsd.edu/DC=AD,DC=UCSD,DC=EDU''
#                         WHERE {where_sql}
#                         AND memberOf = ''CN=HS-DUO-USERS,OU=Groups,OU=Global Resources,OU=UCSD Healthcare,DC=AD,DC=UCSD,DC=EDU''
#                     ')
#                 """)
#                 duo_result = db.session.execute(duosql).fetchone()
#                 is_duo = duo_result is not None
#                 sopsql = text(f"""
#                     SELECT sAMAccountName
#                     FROM OPENQUERY(ADSI, '
#                         SELECT sAMAccountName
#                         FROM ''LDAP://ldap.ad.ucsd.edu/DC=AD,DC=UCSD,DC=EDU''
#                         WHERE {where_sql}
#                         AND memberOf = ''CN=FOL_AHS-SOPPS-PHARMACY_EDUCATION-RW,OU=DFS Groups,OU=Groups,OU=AHS,OU=UCSD Healthcare,DC=AD,DC=UCSD,DC=EDU''
#                     ')
#                 """)
#                 sop_result = db.session.execute(sopsql).fetchone()
#                 is_sop = sop_result is not None
#                 # print("duo_result",duo_result)
#                 results.append({
#                     'Username': row.sAMAccountName,
#                     'Name': row.displayName,
#                     'Active': 'Yes' if is_active(row.userAccountControl) else 'No',
#                     'Exp': convert_windows_time(row.accountExpires),
#                     'Emp ID': row.employeeID,
#                     'DN': row.distinguishedName,
#                     'HC OU': 'Yes' if extract_ou(row.distinguishedName, 'UCSD Healthcare') else 'No',
#                     'SOP OU': 'Yes' if is_sop else 'No',
#                     'HS DUO': 'Yes' if is_duo else 'No'
#                 })
#         except Exception as e:
#             print("LDAP query failed:", e)

#     print(results)

#     return render_template('ad_lookup/search.html', results=results, searched=searched)