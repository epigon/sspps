# from app import db
# from . import db
from cred import server, user, pwd, database  # ensure `database` is defined in cred.py
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
import chardet
import pandas as pd

driver="ODBC Driver 17 for SQL Server" 
connection_string = f'mssql+pyodbc://{user}:{pwd}@{server}/{database}?driver={driver}'
engine = create_engine(connection_string)

def import_employees():
    # Step 1: Load the CSV files
    df1 = pd.read_csv('static/files/vchs_sspps_employee.csv')
    df2 = pd.read_csv('static/files/vchs_sspps_job_location.csv')

    # Step 2: Perform a left join on a common key (e.g., employee_id)
    # merged_df = pd.merge(df1, df2, on='employee_id', how='left')  # or 'left', 'right', 'outer'

    # # Step 3: Remove rows with blank or missing ad_username
    # # This filters out both empty strings and NaNs
    # merged_df = merged_df[merged_df['ad_username'].notna() & (merged_df['ad_username'].str.strip() != '')]
    # print(merged_df)

    # Import to 'Employee' table
    # merged_df.to_sql('NEW_EMPLOYEES', con=engine, if_exists='append', index=False)

    df1.to_sql('NEW_EMPLOYEES1', con=engine, if_exists='append', index=False)
    df2.to_sql('NEW_EMPLOYEES2', con=engine, if_exists='append', index=False)

# def transfer2db(csv, table):

#     with open(csv, 'rb',) as file:
#         data = file.read()

#         # Step 3: Detect Encoding using chardet Library
#         encoding_result = chardet.detect(data)

#         # Step 4: Retrieve Encoding Information
#         encoding = encoding_result['encoding']

#         # Step 5: Print Detected Encoding Information
#         print("Detected Encoding:", encoding)

#     with open(csv, 'rb') as file:
#         # data_df = pd.read_csv(file, encoding = encoding.upper())
#         df = pd.read_csv(csv, encoding = encoding.upper())

#         # Insert data into the table (replace 'your_table' with actual table name)
#         df.to_sql(table, db.engine, if_exists='append', index=False)

#         print("Data inserted successfully!")

    # data_df.to_sql(table, con=db.engine,  if_exists="replace")
    # print(data_df)
    # with open(csv, 'rb') as file:
    #     data_df = pd.read_csv(file, encoding = encoding)
    # # data_df.to_sql(table, con=db.engine,  if_exists='replace')
    # print(data_df)

if __name__ == '__main__':
    import_employees()
    
    # csv_file_path = 'static/files/vchs_sspps_employee.csv'
    # transfer2db(csv_file_path, 'Members')

    # csv_file_path = 'static/files/vchs_sspps_job_location.csv'
    # transfer2db(csv_file_path, 'Members')

    # csv_file_path = 'static/files/Members.csv'
    # transfer2db(csv_file_path, 'Members')

    # csv_file_path = 'static/files/Committees.csv'
    # transfer2db(csv_file_path, 'Committees')

    # csv_file_path = 'static/files/SSPPS-current-workforce.csv'
    # transfer2db(csv_file_path, 'ADUsers')

    # csv_file_path = 'static/files/AcademicYear.csv'
    # transfer2db(csv_file_path, 'AcademicYears')
    
    # csv_file_path = 'static/files/FrequencyTypes.csv'
    # transfer2db(csv_file_path, 'FrequencyTypes')
    
    # csv_file_path = 'static/files/MemberRoles.csv'
    # transfer2db(csv_file_path, 'MemberRoles')
    
    # csv_file_path = 'static/files/MemberTasks.csv'
    # transfer2db(csv_file_path, 'MemberTasks')
    
    # csv_file_path = 'static/files/MemberTypes.csv'
    # transfer2db(csv_file_path, 'MemberTypes')
    
    # csv_file_path = 'static/files/CommitteeTypes.csv'
    # transfer2db(csv_file_path, 'CommitteeTypes')

# import pandas as pd
# import chardet

# csv_file_path = 'static/files/AcademicYear.csv'
# # Step 2: Read CSV File in Binary Mode
# with open(csv_file_path, 'rb') as f:
#     data = f.read()

# # Step 3: Detect Encoding using chardet Library
# encoding_result = chardet.detect(data)

# # Step 4: Retrieve Encoding Information
# encoding = encoding_result['encoding']

# # Step 5: Print Detected Encoding Information
# print("Detected Encoding:", encoding)
