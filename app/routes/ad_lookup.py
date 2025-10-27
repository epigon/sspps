from app.models import db
from app.cred import LDAP_USER, LDAP_PASSWORD
from app.utils import permission_required
from datetime import datetime, timedelta
from flask import render_template, request, Blueprint, g
from flask_login import login_required
from functools import lru_cache
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.utils.conv import escape_filter_chars as esc

bp = Blueprint('ad_lookup', __name__, url_prefix='/ad_lookup')

LDAP_SERVER = 'ldap.ad.ucsd.edu'
BASE_DN = 'DC=AD,DC=UCSD,DC=EDU'

# Routes to Webpages
@bp.before_request
@login_required
def before_request():
    pass

def get_ldap_conn():
    if not hasattr(g, 'ldap_conn') or not g.ldap_conn.bound:
        server = Server(LDAP_SERVER, get_info=None)
        g.ldap_conn = Connection(
            server,
            user=LDAP_USER,
            password=LDAP_PASSWORD,
            auto_bind=True,
            read_only=True,
            raise_exceptions=True
        )
    return g.ldap_conn

@bp.teardown_app_request
def close_ldap_conn(exception=None):
    conn = getattr(g, 'ldap_conn', None)
    if conn and conn.bound:
        conn.unbind()

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

# def extract_ou(distinguished_name, keyword):
#     # Try to extract the OU matching keyword (case-insensitive)
#     parts = distinguished_name.split(',')
#     for part in parts:
#         if part.strip().lower().startswith(f'ou={keyword.lower()}'):
#             return part.strip()
#     return ''

@lru_cache(maxsize=256)
def cached_ldap_search(searchtype_ad, searchtype_first, searchtype_last, username, firstname, lastname):
    """Cache AD search results with group checks via LDAP filters."""
    conn = get_ldap_conn()

    # Base filters
    # Restrict to user objects (avoids computers)
    filters = ['(objectCategory=person)', '(objectClass=user)']
    if searchtype_ad == 'partial':
        if username:
            filters.append(f'(sAMAccountName=*{esc(username)}*)')
    else:
        if username:
            filters.append(f'(sAMAccountName={esc(username)})')

    if searchtype_first == 'partial':
        if firstname:
            filters.append(f'(givenName=*{esc(firstname)}*)')
    else:
        if firstname:
            filters.append(f'(givenName={esc(firstname)})')

    if searchtype_last == 'partial':
        if lastname:
            filters.append(f'(sn=*{esc(lastname)}*)')
    else:
        if lastname:
            filters.append(f'(sn={esc(lastname)})')

    # Group checks (matching rule in chain = nested group aware)
    # HS_DUO_DN = f"CN=HS-DUO-USERS,OU=Groups,{BASE_DN}"
    # SOP_DN = f"CN=FOL_AHS-SOPPS-PHARMACY_EDUCATION-RW,OU=Groups,{BASE_DN}"

    ldap_filter = '(&' + ''.join(filters) + ')'

    conn.search(
        BASE_DN,
        ldap_filter,
        search_scope=SUBTREE,
        attributes=[
            'sAMAccountName', 'displayName', 'userAccountControl',
            'accountExpires', 'employeeID', 'distinguishedName'
        ],
        paged_size=50
    )

    results = []
    for entry in conn.entries:
        attr = entry.entry_attributes_as_dict
        # uname = attr.get('sAMAccountName', [''])[0]
        results.append({
            'Username': attr.get('sAMAccountName', [''])[0],
            'Name': attr.get('displayName', [''])[0],
            'Active': is_active(attr.get('userAccountControl', [0])[0]),
            'Exp': convert_windows_time(attr.get('accountExpires', [0])[0]),
            'Emp ID': attr.get('employeeID', [''])[0] if attr.get('employeeID') else '',
            'DN': attr.get('distinguishedName', [''])[0],
            'HC OU': 'Yes' if 'UCSD Healthcare' in attr.get('distinguishedName', [''])[0] else 'No',
            'SOP OU': 'Yes' if 'School of Pharmacy' in attr.get('distinguishedName', [''])[0] else 'No'
            # ,
            # 'HS DUO': 'Yes' if user_in_group(uname, HS_DUO_DN) else 'No',
            # 'SOP OU': 'Yes' if user_in_group(uname, SOP_DN) else 'No'
        })
    return results

@bp.route('/search', methods=['GET', 'POST'])
@permission_required('ad_lookup+view')
def search():

    searchterms = '+'.join(filter(None, [
        request.form.get('username', '').strip(),
        request.form.get('firstname', '').strip(),
        request.form.get('lastname', '').strip()
    ]))

    custom_breadcrumbs = [
        {'name': 'Active Directory Search', 'url': '/ad_lookup/search'},
        {'name': f'Search Results for: {searchterms}', 'url': '/ad_lookup/search'}
    ]

    results = []
    error = None
    # searched = False

    if request.method == 'POST':
        # searched = True
        try:
            results = cached_ldap_search(
                request.form.get('searchtype_ad', 'exact').strip(),
                request.form.get('searchtype_first', 'exact').strip(),
                request.form.get('searchtype_last', 'exact').strip(),
                request.form.get('username', '').strip(),
                request.form.get('firstname', '').strip(),
                request.form.get('lastname', '').strip()
            )
        except Exception as e:
            error = str(e)

    print(results)
        
    return render_template('ad_lookup/search.html', results=results, error=error, searchterms=searchterms, breadcrumbs=custom_breadcrumbs)
