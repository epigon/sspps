from app.cred import server, user, pwd, database, odbcdriver  # ensure `database` is defined in cred.py
from datetime import datetime
from sqlalchemy import create_engine, text
import pandas as pd

connection_string = f'mssql+pyodbc://{user}:{pwd}@{server}/{database}?driver={odbcdriver}&TrustServerCertificate=yes'
engine = create_engine(connection_string)

def import_employees():
    # Step 1: Load the CSV files
    df = pd.read_csv('app/static/files/vchs_sspps_employee.csv',
                     dtype={
                            'Department_Code': 'string'  # use the CSV column name here
                        })
                        
    # Rename columns
    rename_map = {
        'Employee_Name_Current': 'employee_name',
        'Employee_First_Name_Current': 'employee_first_name',
        'Employee_Last_Name_Current': 'employee_last_name',
        'Identity_Active_Directory_ID_Current': 'username',
        'Identity_Email_Address_Current': 'email2',
        'Reports_To_Employee_ID': 'reports_to_id',
        'Pay_Group': 'employee_type',
        'Employee_PPS_ID_Current': 'employee_pps_id',
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

    # Step 2: Load the second file with updated email and mail drop info
    contact_df = pd.read_csv('app/static/files/eahWorkforceIdentity.csv')

    # Rename columns for consistency
    contact_df = contact_df.rename(columns={
        'Employee_ID': 'employee_id',
        'Job_Indicator': 'job_indicator',
        'Identity_Subdomain_Email_Address_Current': 'email',
        'Identity_Mail_Drop_Current': 'mail_code'
    })

    # Convert to lowercase
    contact_df.columns = contact_df.columns.str.lower()

    # Step 3: Load pay frequency file
    pay_df = pd.read_csv('app/static/files/eahWorkforceJobExtended.csv')
    pay_df = pay_df.rename(columns={
        'Employee_ID': 'employee_id',
        'Job_Indicator': 'job_indicator',
        'Pay_Frequency': 'pay_frequency'
    })
    pay_df.columns = pay_df.columns.str.lower()

    # filtered_df = df[df['job_indicator'] == 'Primary']

    # Merge contact info
    filtered_df = df.merge(
        contact_df[['employee_id', 'job_indicator', 'email', 'mail_code']],
        on=['employee_id', 'job_indicator'],
        how='left'
    )

    # Merge pay frequency
    filtered_df = filtered_df.merge(
        pay_df[['employee_id', 'job_indicator', 'pay_frequency']],
        on=['employee_id', 'job_indicator'],
        how='left'
    )

    print(f"{filtered_df['email'].isnull().sum()} employees missing email from contact file.")

    print(f"{filtered_df['pay_frequency'].isnull().sum()} employees missing pay frequency from pay file.")

    filtered_df = filtered_df.drop_duplicates(
        subset=["employee_id", "job_indicator"],
        keep="first"
    )   
    
    staging_table = 'STAGING_EMPLOYEES'
    
    filtered_df.to_sql(staging_table, con=engine, if_exists='replace', index=False)
    print(f"Loaded {len(filtered_df)} records into {staging_table}.")

    merge_sql = f"""
        ;WITH Staging AS (
            SELECT *
            FROM STAGING_EMPLOYEES
        )
        -- Step 1: Merge Primary records first
        MERGE INTO EMPLOYEES AS target
        USING (
            SELECT *
            FROM Staging
            WHERE job_indicator = 'Primary'
        ) AS source
        ON target.employee_id = source.employee_id
        
        WHEN MATCHED THEN 
            UPDATE SET 
                target.employee_first_name = source.employee_first_name,
                target.employee_last_name = source.employee_last_name,
                target.employee_name = source.employee_name,
                target.employee_id = source.employee_id,
                target.username = source.username,
                target.job_action_effective_date = source.job_action_effective_date,
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
                target.pay_frequency = source.pay_frequency,
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
                target.mail_code = source.mail_code

        WHEN NOT MATCHED THEN 
            INSERT (employee_first_name,
                employee_last_name,
                employee_name,
                employee_id,
                username,
                job_action_effective_date,
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
                pay_frequency,
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
            source.pay_frequency,
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
                
        -- Step 2: Insert non-primary records only if they don't exist yet
        INSERT INTO EMPLOYEES (
            employee_first_name,
                employee_last_name,
                employee_name,
                employee_id,
                username,
                job_action_effective_date,
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
                pay_frequency,
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
        SELECT s.employee_first_name,
                s.employee_last_name,
                s.employee_name,
                s.employee_id,
                s.username,
                s.job_action_effective_date,
                s.employee_record,
                s.employee_status,
                s.employee_pps_id,
                s.student_pid,
                s.email,
                s.email2,
                s.employee_work_phone_number,
                s.department_code,
                s.department,
                s.vice_chancellor_code,
                s.vice_chancellor,
                s.flsa_status,
                s.position_number,
                s.working_title,
                s.reports_to_employee,
                s.reports_to_id,
                s.reports_to_employee_status_code,
                s.reports_to_position_number,
                s.occupational_subgroup,
                s.employee_start_date,
                s.employee_original_start_date,
                s.department_start_date,
                s.employee_restart_date,
                s.last_separation_date,
                s.job_expected_end_date,
                s.job_start_date,
                s.job_end_date,
                s.job_automatically_end_flag,
                s.pay_group_code,
                s.employee_type,
                s.job_compensation_frequency_code,
                s.job_compensation_frequency,                
                s.pay_frequency,
                s.job_code,
                s.job_code_description,
                s.employee_class_code,
                s.employee_class,
                s.position_class_code,
                s.position_class,
                s.position_employee_relations_code,
                s.position_employee_relations,
                s.position_special_training_code,
                s.position_start_date,
                s.union_code,
                s.union_name,
                s.job_fte,
                s.next_salary_review_date,
                s.salary_grade,
                s.salary_step_number,
                s.building,
                s.building_code,
                s.room,
                s.mail_code
        FROM STAGING_EMPLOYEES s
        WHERE s.job_indicator <> 'Primary'
        AND NOT EXISTS (
            SELECT 1 
            FROM EMPLOYEES e
            WHERE e.employee_id = s.employee_id
        );
    """

    with engine.begin() as conn:
        result = conn.execute(text(merge_sql))
        actions = result.fetchall()

    # Count how many rows were inserted or updated
    from collections import Counter
    action_counts = Counter(row[0] for row in actions)

    print(f"Inserted: {action_counts['INSERT']}, Updated: {action_counts['UPDATE']}")

if __name__ == '__main__':
    print("Run summary:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    import_employees()