from app.cred import server, user, pwd, database  # ensure `database` is defined in cred.py
from sqlalchemy import create_engine, text
import pandas as pd

driver="ODBC Driver 17 for SQL Server" 
connection_string = f'mssql+pyodbc://{user}:{pwd}@{server}/{database}?driver={driver}'
engine = create_engine(connection_string)

def import_employees():
    # Step 1: Load the CSV files
    df = pd.read_csv('app/static/files/vchs_sspps_employee.csv')
    
    # Rename columns
    rename_map = {
        'Employee_Name_Current': 'employee_name',
        'Employee_First_Name_Current': 'employee_first_name',
        'Employee_Last_Name_Current': 'employee_last_name',
        'Identity_Active_Directory_ID_Current': 'username',
        'Identity_Subdomain_Email_Address_Current': 'email',
        'Identity_Email_Address_Current': 'email2',
        'Reports_To_Employee_ID': 'reports_to_id',
        'Pay_Group': 'employee_type',
        'Employee_PPS_ID_Current': 'employee_pps_id',
        'Identity_Mail_Drop_Current': 'mail_code',
        'Identity_Building_Location_Current': 'building',
        'Identity_Room_Number_Current': 'room',
        'Identity_Building_Code_Current': 'building_code',
        'Identity_Working_Title_Current': 'working_title',
        'Employee_Work_Phone_Number_Current': 'employee_work_phone_number',
        'Identity_Student_PID_Current': 'student_pid',
        'Union': 'union_name'
    }
    df = df.rename(columns=rename_map)
    # Convert all column names to lowercase
    df.columns = df.columns.str.lower()
    filtered_df = df[df['job_indicator'] == 'Primary']

    staging_table = 'STAGING_EMPLOYEES'
    filtered_df.to_sql(staging_table, con=engine, if_exists='replace', index=False)

    # print(filtered_df)
    # # Upload to temporary table
    # temp_table = "##temp_employees"
    # filtered_df.to_sql(temp_table[2:], con=engine, if_exists='replace', index=False)

    # with engine.connect() as conn:
    #     merge_sql = text(f"""
    #     MERGE INTO EMPLOYEES AS target
    #     USING {staging_table} AS source
    #     ON target.employee_id = source.employee_id
    #     WHEN MATCHED THEN
    #         UPDATE SET
    #             employee_first_name = source.employee_first_name,
    #             employee_last_name = source.employee_last_name,
    #             employee_name = source.employee_name,
    #             employee_id = source.employee_id,
    #             username = source.username,
    #             job_action_effective_date = source.job_action_effective_date,
    #             job_indicator = source.job_indicator,
    #             employee_record = source.employee_record,
    #             employee_status = source.employee_status,
    #             employee_pps_id = source.employee_pps_id,
    #             student_pid = source.student_pid,
    #             email2 = source.email2,
    #             employee_work_phone_number = source.employee_work_phone_number,
    #             department_code = source.department_code,
    #             department = source.department,
    #             vice_chancellor_code = source.vice_chancellor_code,
    #             vice_chancellor = source.vice_chancellor,
    #             flsa_status = source.flsa_status,
    #             position_number = source.position_number,
    #             working_title = source.working_title,
    #             reports_to_employee = source.reports_to_employee,
    #             reports_to_id = source.reports_to_id,
    #             reports_to_employee_status_code = source.reports_to_employee_status_code,
    #             reports_to_position_number = source.reports_to_position_number,
    #             occupational_subgroup = source.occupational_subgroup,
    #             employee_start_date = source.employee_start_date,
    #             employee_original_start_date = source.employee_original_start_date,
    #             department_start_date = source.department_start_date,
    #             employee_restart_date = source.employee_restart_date,
    #             last_separation_date = source.last_separation_date,
    #             job_expected_end_date = source.job_expected_end_date,
    #             job_start_date = source.job_start_date,
    #             job_end_date = source.job_end_date,
    #             job_automatically_end_flag = source.job_automatically_end_flag,
    #             pay_group_code = source.pay_group_code,
    #             employee_type = source.employee_type,
    #             job_compensation_frequency_code = source.job_compensation_frequency_code,
    #             job_compensation_frequency = source.job_compensation_frequency,
    #             job_code = source.job_code,
    #             job_code_description = source.job_code_description,
    #             employee_class_code = source.employee_class_code,
    #             employee_class = source.employee_class,
    #             position_class_code = source.position_class_code,
    #             position_class = source.position_class,
    #             position_employee_relations_code = source.position_employee_relations_code,
    #             position_employee_relations = source.position_employee_relations,
    #             position_special_training_code = source.position_special_training_code,
    #             position_start_date = source.position_start_date,
    #             union_code = source.union_code,
    #             union_name = source.union_name,
    #             job_fte = source.job_fte,
    #             salary_grade = source.salary_grade,
    #             salary_step_number = source.salary_step_number,
    #             next_salary_review_date = source.next_salary_review_date,
    #             building = source.building,
    #             building_code = source.building_code,
    #             room = source.room
    #     WHEN NOT MATCHED THEN
    #         INSERT ({', '.join(filtered_df.columns)})
    #         VALUES ({', '.join(['source.' + col for col in filtered_df.columns])});
    #     """)
        # adding email, mail_code
        # merge_sql = text(f"""
        # MERGE INTO EMPLOYEES AS target
        # USING {staging_table} AS source
        # ON target.employee_id = source.employee_id
        # WHEN MATCHED THEN
        #     UPDATE SET
        #         employee_first_name = source.employee_first_name,
        #         employee_last_name = source.employee_last_name,
        #         employee_name = source.employee_name,
        #         employee_id = source.employee_id,
        #         username = source.username,
        #         job_action_effective_date = source.job_action_effective_date,
        #         job_indicator = source.job_indicator,
        #         employee_record = source.employee_record,
        #         employee_status = source.employee_status,
        #         employee_pps_id = source.employee_pps_id,
        #         student_pid = source.student_pid,
        #         email = source.email,
        #         email2 = source.email2,
        #         employee_work_phone_number = source.employee_work_phone_number,
        #         department_code = source.department_code,
        #         department = source.department,
        #         vice_chancellor_code = source.vice_chancellor_code,
        #         vice_chancellor = source.vice_chancellor,
        #         flsa_status = source.flsa_status,
        #         position_number = source.position_number,
        #         working_title = source.working_title,
        #         reports_to_employee = source.reports_to_employee,
        #         reports_to_id = source.reports_to_id,
        #         reports_to_employee_status_code = source.reports_to_employee_status_code,
        #         reports_to_position_number = source.reports_to_position_number,
        #         occupational_subgroup = source.occupational_subgroup,
        #         employee_start_date = source.employee_start_date,
        #         employee_original_start_date = source.employee_original_start_date,
        #         department_start_date = source.department_start_date,
        #         employee_restart_date = source.employee_restart_date,
        #         last_separation_date = source.last_separation_date,
        #         job_expected_end_date = source.job_expected_end_date,
        #         job_start_date = source.job_start_date,
        #         job_end_date = source.job_end_date,
        #         job_automatically_end_flag = source.job_automatically_end_flag,
        #         pay_group_code = source.pay_group_code,
        #         employee_type = source.employee_type,
        #         job_compensation_frequency_code = source.job_compensation_frequency_code,
        #         job_compensation_frequency = source.job_compensation_frequency,
        #         job_code = source.job_code,
        #         job_code_description = source.job_code_description,
        #         employee_class_code = source.employee_class_code,
        #         employee_class = source.employee_class,
        #         position_class_code = source.position_class_code,
        #         position_class = source.position_class,
        #         position_employee_relations_code = source.position_employee_relations_code,
        #         position_employee_relations = source.position_employee_relations,
        #         position_special_training_code = source.position_special_training_code,
        #         position_start_date = source.position_start_date,
        #         union_code = source.union_code,
        #         union_name = source.union_name,
        #         job_fte = source.job_fte,
        #         salary_grade = source.salary_grade,
        #         salary_step_number = source.salary_step_number,
        #         next_salary_review_date = source.next_salary_review_date,
        #         building = source.building,
        #         building_code = source.building_code,
        #         room = source.room,
        #         mail_code = source.mail_code
        # WHEN NOT MATCHED THEN
        #     INSERT ({', '.join(filtered_df.columns)})
        #     VALUES ({', '.join(['source.' + col for col in filtered_df.columns])});
        # """)
        # conn.execute(merge_sql)

    merge_sql = f"""
        MERGE INTO EMPLOYEES AS target
        USING {staging_table} AS source
        ON target.employee_id = source.employee_id
        WHEN MATCHED THEN 
            UPDATE SET 
                target.employee_first_name = source.employee_first_name,
                target.employee_last_name = source.employee_last_name,
                target.employee_name = source.employee_name,
                target.employee_id = source.employee_id,
                target.username = source.username,
                target.job_action_effective_date = source.job_action_effective_date,
                target.job_indicator = source.job_indicator,
                target.employee_record = source.employee_record,
                target.employee_status = source.employee_status,
                target.employee_pps_id = source.employee_pps_id,
                target.student_pid = source.student_pid,
                target.email = source.email2,
                target.email2 = source.email2,
                target.employee_work_phone_number = source.employee_work_phone_number,
                target.department_code = source.department_code,
                target.department = source.department,
                target.vice_chancellor_code = source.vice_chancellor_code,
                target.vice_chancellor = source.vice_chancellor,
                target.flsa_status = source.flsa_status,
                target.position_number = source.position_number,
                target.working_title = source.working_title,
                target.reports_to_employee = source.reports_to_employee,
                target.reports_to_id = source.reports_to_id,
                target.reports_to_employee_status_code = source.reports_to_employee_status_code,
                target.reports_to_position_number = source.reports_to_position_number,
                target.occupational_subgroup = source.occupational_subgroup,
                target.employee_start_date = source.employee_start_date,
                target.employee_original_start_date = source.employee_original_start_date,
                target.department_start_date = source.department_start_date,
                target.employee_restart_date = source.employee_restart_date,
                target.last_separation_date = source.last_separation_date,
                target.job_expected_end_date = source.job_expected_end_date,
                target.job_start_date = source.job_start_date,
                target.job_end_date = source.job_end_date,
                target.job_automatically_end_flag = source.job_automatically_end_flag,
                target.pay_group_code = source.pay_group_code,
                target.employee_type = source.employee_type,
                target.job_compensation_frequency_code = source.job_compensation_frequency_code,
                target.job_compensation_frequency = source.job_compensation_frequency,
                target.job_code = source.job_code,
                target.job_code_description = source.job_code_description,
                target.employee_class_code = source.employee_class_code,
                target.employee_class = source.employee_class,
                target.position_class_code = source.position_class_code,
                target.position_class = source.position_class,
                target.position_employee_relations_code = source.position_employee_relations_code,
                target.position_employee_relations = source.position_employee_relations,
                target.position_special_training_code = source.position_special_training_code,
                target.position_start_date = source.position_start_date,
                target.union_code = source.union_code,
                target.union_name = source.union_name,
                target.job_fte = source.job_fte,
                target.next_salary_review_date = source.next_salary_review_date,
                target.salary_grade = source.salary_grade,
                target.salary_step_number = source.salary_step_number,
                target.building = source.building,
                target.building_code = source.building_code,
                target.room = source.room,
                target.mail_code = ''

        WHEN NOT MATCHED THEN 
            INSERT (employee_first_name,
                employee_last_name,
                employee_name,
                employee_id,
                username,
                job_action_effective_date,
                job_indicator,
                employee_record,
                employee_status,
                employee_pps_id,
                student_pid,
                email,
                email2,
                employee_work_phone_number,
                department_code,
                department,
                vice_chancellor_code,
                vice_chancellor,
                flsa_status,
                position_number,
                working_title,
                reports_to_employee,
                reports_to_id,
                reports_to_employee_status_code,
                reports_to_position_number,
                occupational_subgroup,
                employee_start_date,
                employee_original_start_date,
                department_start_date,
                employee_restart_date,
                last_separation_date,
                job_expected_end_date,
                job_start_date,
                job_end_date,
                job_automatically_end_flag,
                pay_group_code,
                employee_type,
                job_compensation_frequency_code,
                job_compensation_frequency,
                job_code,
                job_code_description,
                employee_class_code,
                employee_class,
                position_class_code,
                position_class,
                position_employee_relations_code,
                position_employee_relations,
                position_special_training_code,
                position_start_date,
                union_code,
                union_name,
                job_fte,
                next_salary_review_date,
                salary_grade,
                salary_step_number,
                building,
                building_code,
                room,
                mail_code
            )
            VALUES (source.employee_first_name,
            source.employee_last_name,
            source.employee_name,
            source.employee_id,
            source.username,
            source.job_action_effective_date,
            source.job_indicator,
            source.employee_record,
            source.employee_status,
            source.employee_pps_id,
            source.student_pid,
            source.email2,
            source.email2,
            source.employee_work_phone_number,
            source.department_code,
            source.department,
            source.vice_chancellor_code,
            source.vice_chancellor,
            source.flsa_status,
            source.position_number,
            source.working_title,
            source.reports_to_employee,
            source.reports_to_id,
            source.reports_to_employee_status_code,
            source.reports_to_position_number,
            source.occupational_subgroup,
            source.employee_start_date,
            source.employee_original_start_date,
            source.department_start_date,
            source.employee_restart_date,
            source.last_separation_date,
            source.job_expected_end_date,
            source.job_start_date,
            source.job_end_date,
            source.job_automatically_end_flag,
            source.pay_group_code,
            source.employee_type,
            source.job_compensation_frequency_code,
            source.job_compensation_frequency,
            source.job_code,
            source.job_code_description,
            source.employee_class_code,
            source.employee_class,
            source.position_class_code,
            source.position_class,
            source.position_employee_relations_code,
            source.position_employee_relations,
            source.position_special_training_code,
            source.position_start_date,
            source.union_code,
            source.union_name,
            source.job_fte,
            source.next_salary_review_date,
            source.salary_grade,
            source.salary_step_number,
            source.building,
            source.building_code,
            source.room,
            ''
        )
        OUTPUT $action AS merge_action;
    """

    with engine.begin() as conn:
        result = conn.execute(text(merge_sql))
        actions = result.fetchall()

    # Count how many rows were inserted or updated
    from collections import Counter
    action_counts = Counter(row[0] for row in actions)
    print(f"Inserted: {action_counts['INSERT']}, Updated: {action_counts['UPDATE']}")

    # with engine.begin() as conn:
    #     conn.execute(text("TRUNCATE TABLE STAGING_EMPLOYEES"))

# def import_employees():
#     # Step 1: Load the CSV files
#     df1 = pd.read_csv('static/files/vchs_sspps_employee.csv')
#     # df2 = pd.read_csv('static/files/vchs_sspps_job_location.csv')
#     # print(len(df1))
#     # print(len(df2))
#     # , usecols=['EmployeeID', 'ad_username', 'Name']

#     # 'ad_username','building','department','email','employee_id','employee_first_name','employee_last_name',
#     # 'employee_name','employee_status','employee_type','job_code','job_code_description','job_code_start_date',
#     # 'mail_code','position_class','reports_to_ID','reports_to_employee','room'


#     # 'employee_id',	'job_action_end_effective_date'	'job_code'	'job_expected_end_date'	'job_location'	'position_class'	
#     # 'position_number'	'position'


#     # Step 2: Perform a left join on a common key (e.g., employee_id)
#     # merged_df = pd.merge(df1, df2, on='Employee_ID', how='left')  # or 'left', 'right', 'outer'
#     # print(len(merged_df))
#     # # Step 3: Remove rows with blank or missing ad_username
#     # # This filters out both empty strings and NaNs
#     # merged_df = merged_df[merged_df['ad_username'].notna() & (merged_df['ad_username'].str.strip() != '')]
#     # print(merged_df)

#     # Rename column in DataFrame
#     # merged_df = merged_df.rename(columns={'ad_username': 'username'})
#     # Convert all column names to lowercase
    
#     # df1 = df1.rename(columns={'Employee_ID': 'employee_id'})
#     df1 = df1.rename(columns={'Employee_Name_Current': 'employee_name'})
#     df1 = df1.rename(columns={'Employee_First_Name_Current': 'employee_first_name'})
#     df1 = df1.rename(columns={'Employee_Last_Name_Current': 'employee_last_name'})
#     df1 = df1.rename(columns={'Identity_Active_Directory_ID_Current': 'username'})
#     df1 = df1.rename(columns={'Identity_Subdomain_Email_Address_Current': 'email'})
#     df1 = df1.rename(columns={'Identity_Email_Address_Current': 'email2'})
#     df1 = df1.rename(columns={'Reports_To_Employee_ID': 'reports_to_id'})
#     df1 = df1.rename(columns={'Pay_Group': 'employee_type'})
#     df1 = df1.rename(columns={'Employee_PPS_ID_Current': 'employee_pps_id'})
#     df1 = df1.rename(columns={'Identity_Mail_Drop_Current': 'mail_code'})
#     df1 = df1.rename(columns={'Identity_Building_Location_Current': 'building'})
#     df1 = df1.rename(columns={'Identity_Room_Number_Current': 'room'})
#     df1 = df1.rename(columns={'Identity_Building_Code_Current': 'building_code'})
#     df1 = df1.rename(columns={'Identity_Working_Title_Current': 'working_title'})
#     df1 = df1.rename(columns={'Employee_Work_Phone_Number_Current': 'employee_work_phone_number'})
#     df1 = df1.rename(columns={'Identity_Student_PID_Current': 'student_pid'})
#     df1 = df1.rename(columns={'Union': 'union_name'})
   
#     df1.columns = df1.columns.str.lower()
#     # print(df1.head())
#     # Import to 'Employee' table
#     # merged_df.to_sql('NEW_EMPLOYEES', con=engine, if_exists='append', index=False)

#     # Define the list of statuses to exclude
#     excluded_statuses = ['Terminated', 'Deceased', 'Retired']

#     # Filter the DataFrame
#     # filtered_df = df1[~df1['employee_status'].isin(excluded_statuses) & (df1['job_indicator'] == 'Primary')]
#     filtered_df = df1[df1['job_indicator'] == 'Primary']

#     # Now, append the filtered_df to the SQL table
#     filtered_df.to_sql('EMPLOYEES', con=engine, if_exists='append', index=False)
#     # df2.to_sql('NEW_EMPLOYEES2', con=engine, if_exists='append', index=False)

# # def transfer2db(csv, table):

# #     with open(csv, 'rb',) as file:
# #         data = file.read()

# #         # Step 3: Detect Encoding using chardet Library
# #         encoding_result = chardet.detect(data)

# #         # Step 4: Retrieve Encoding Information
# #         encoding = encoding_result['encoding']

# #         # Step 5: Print Detected Encoding Information
# #         print("Detected Encoding:", encoding)

# #     with open(csv, 'rb') as file:
# #         # data_df = pd.read_csv(file, encoding = encoding.upper())
# #         df = pd.read_csv(csv, encoding = encoding.upper())

# #         # Insert data into the table (replace 'your_table' with actual table name)
# #         df.to_sql(table, db.engine, if_exists='append', index=False)

# #         print("Data inserted successfully!")

#     # data_df.to_sql(table, con=db.engine,  if_exists="replace")
#     # print(data_df)
#     # with open(csv, 'rb') as file:
#     #     data_df = pd.read_csv(file, encoding = encoding)
#     # # data_df.to_sql(table, con=db.engine,  if_exists='replace')
#     # print(data_df)

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
