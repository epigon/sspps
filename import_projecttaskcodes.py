from app import create_app, db
from app.cred import server, user, pwd, rechargedatabase, odbcdriver  # ensure `database` is defined in cred.py
from app.models import InstrumentRequest, ProjectTaskCode
from app.utils import permission_required
from datetime import datetime
from sqlalchemy import create_engine, Table, Column, String, MetaData
import pandas as pd

metadata = MetaData()
app = create_app()

connection_string = f'mssql+pyodbc://{user}:{pwd}@{server}/{rechargedatabase}?driver={odbcdriver}&TrustServerCertificate=yes'
engine = create_engine(connection_string)

# --- Define Table for Bulk Insert ---
project_task_codes_table = Table(
    'ProjectTaskCodes', metadata,
    Column('entity_code', String(20), primary_key=True),
    Column('project_task_code', String(20), primary_key=True),
    Column('funding_source_code', String(50), primary_key=True),
    Column('funding_source', String(500), primary_key=True),
    Column('pi_email', String(50), nullable=False),
    Column('pi_name', String(50), nullable=False),
    Column('fund_manager_name', String(50), nullable=False),
    Column('fund_manager_email', String(50), nullable=False),
    Column('status', String(20), nullable=False)
)

chartstrings_table = Table(
    'Chartstrings', metadata,
    Column('chartstring', String(200), primary_key=True),
    Column('entity_code', String(20), nullable=False),
    Column('fund_code', String(20), nullable=False),
    Column('financial_unit_code', String(20), nullable=False),
    Column('account_code', String(20), nullable=False),
    Column('function_code', String(20), nullable=False),
    Column('project_code', String(20), nullable=False),
    Column('status', String(20))
)

# --- CSV Import Function ---
def import_project_task_codes(csv_path):
    df = pd.read_csv(csv_path, dtype=str).fillna('')

    required_columns = [
        'Entity_Code',
        'Project-Task_Code',
        'Award_External_Funding_Source_Code',
        'Award_External_Funding_Source',
        'Project_Status',
        'Award_Principal_Investigator_Email_Address',
        'Award_Principal_Investigator_Name_Full',
        'Award_Most_Recent_Principal_Investigator_Email_Address',
        'Award_Most_Recent_Principal_Investigator_Name_Full',
        'Award_Fund_Manager_Name_Full',
        'Award_Fund_Manager_Email_Address'
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing column in CSV: {col}")

    # Clean whitespace
    for col in df.columns:
        df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

    # Remove incomplete rows
    df = df.dropna(subset=[
        'Entity_Code', 'Project-Task_Code', 'Award_External_Funding_Source_Code', 'Award_External_Funding_Source'
    ])

    # Keep only distinct records based on primary key columns
    df = df.drop_duplicates(subset=[
        'Entity_Code', 'Project-Task_Code', 'Award_External_Funding_Source_Code', 'Award_External_Funding_Source'
    ])

    
# Combine — use "most recent" if present, otherwise "original"
    df['pi_email'] = (
        df['Award_Most_Recent_Principal_Investigator_Email_Address']
        .replace('', pd.NA)  # treat empty string as missing
        .fillna(df['Award_Principal_Investigator_Email_Address'])
    )

    df['pi_name'] = (
        df['Award_Most_Recent_Principal_Investigator_Name_Full']
        .replace('', pd.NA)
        .fillna(df['Award_Principal_Investigator_Name_Full'])
    )

    # Then rename other columns as needed
    df = df.rename(columns={
        'Entity_Code': 'entity_code',
        'Project-Task_Code': 'project_task_code',
        'Award_External_Funding_Source_Code': 'funding_source_code',
        'Award_External_Funding_Source': 'funding_source',
        'Project_Status': 'status',
        'Award_Fund_Manager_Name_Full': 'fund_manager_name',
        'Award_Fund_Manager_Email_Address': 'fund_manager_email'
    })

    # Convert to list of dicts
    records = df.to_dict(orient='records')

    if not records:
        print("No valid rows found to import.")
        return

    with engine.begin() as conn:
        # Delete existing rows
        print("Deleting existing records from ProjectTaskCodes...")
        deleted_rows = conn.execute(project_task_codes_table.delete()).rowcount or 0
        print(f"Deleted {deleted_rows} existing row(s).")

        # Bulk insert
        print(f"Inserting {len(records)} distinct records...")
        try:
            conn.execute(project_task_codes_table.insert(), records)
            print(f"Import complete: {len(records)} records inserted.")
        except Exception as e:
            print(f"Error during insert: {e}")

# --- CSV Import Function ---
def import_chartstrings(csv_path):
    df = pd.read_csv(csv_path, dtype=str).fillna('')

    required_columns = [
        'Entity_Code', 'Fund_Code', 'Financial_Unit_Code',
        'Account_Code', 'Function_Code', 'Project_Code',
        'Chartstring', 'Project_Status'
    ]

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Missing column in CSV: {col}")

    # Clean whitespace
    for col in df.columns:
        df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

    # Remove incomplete rows
    df = df.dropna(subset=required_columns)

    # Keep only distinct chartstrings (PK)
    df = df.drop_duplicates(subset=['Chartstring'])

    # Convert to dicts
    records = df.rename(columns={
        'Entity_Code': 'entity_code',
        'Fund_Code': 'fund_code',
        'Financial_Unit_Code': 'financial_unit_code',
        'Account_Code': 'account_code',
        'Function_Code': 'function_code',
        'Project_Code': 'project_code',
        'Chartstring': 'chartstring',
        'Project_Status': 'status'
    }).to_dict(orient='records')

    if not records:
        print("No valid records found to import.")
        return

    with engine.begin() as conn:
        # Delete all existing rows
        print("Deleting existing records from Chartstrings...")
        deleted_rows = conn.execute(chartstrings_table.delete()).rowcount or 0
        print(f"Deleted {deleted_rows} existing row(s).")

        # Bulk insert
        print(f"Inserting {len(records)} distinct chartstring records...")
        try:
            conn.execute(chartstrings_table.insert(), records)
            print(f"Import complete: {len(records)} inserted.")
        except Exception as e:
            print(f"Error during insert: {e}")

def verify_requests():
    with app.app_context():
        req = InstrumentRequest.query.filter(InstrumentRequest.status.in_(["Approved", "Pending"])).all()

        for r in req:
            activeProjectTaskCode = ProjectTaskCode.query.filter_by(
                project_task_code=r.project_task_code
            ).first()
            if not activeProjectTaskCode:         
                # print(r.id, r.project_task_code, r.status)   
                r.notes = ((r.notes+";") or "") + f'\nInvalid Project Task Code. {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                r.status = "Cancelled"
                db.session.commit()
                print(f"Request ID {r.id} denied due to invalid project task code.")

# --- Run Script ---
if __name__ == "__main__":
    csv_file = "app/static/files/pharmacy_projectTaskCodes.csv"  # change this path as needed
    import_project_task_codes(csv_file)

    csv_file = "app/static/files/pharmacy_chartstrings.csv"  # update if needed
    import_chartstrings(csv_file)

    verify_requests()
