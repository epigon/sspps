from app import db
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import event, Column, Integer, String, DateTime, UniqueConstraint, ForeignKey, Boolean, Date, Time, Text #create_engine, 
from sqlalchemy.orm import relationship, object_session
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
import uuid

## ADMIN MODELS
user_permissions = db.Table('USER_PERMISSIONS',
    Column('user_id', db.Integer, db.ForeignKey('USERS.id')),
    Column('permission_id', db.Integer, db.ForeignKey('PERMISSIONS.id'))
)

role_permissions = db.Table('ROLE_PERMISSIONS',
    Column('role_id', db.Integer, db.ForeignKey('ROLES.id')),
    Column('permission_id', db.Integer, db.ForeignKey('PERMISSIONS.id'))
)

class Role(db.Model):
    __tablename__ = 'ROLES'
    id = Column(db.Integer, primary_key=True)
    name = Column(db.String(64), unique=True)
    permissions = db.relationship('Permission', secondary=role_permissions)
    users = db.relationship('User', back_populates='role')
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

    
class Permission(db.Model):
    __tablename__ = 'PERMISSIONS'
    id = Column(db.Integer, primary_key=True)
    resource = Column(db.String(64))
    action = Column(db.String(64))
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class User(UserMixin, db.Model):
    __tablename__ = 'USERS'
    id = Column(db.Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('EMPLOYEES.employee_id'), nullable=False)
    username = Column(db.String(64), unique=True, nullable=False)
    role_id = Column(db.Integer, db.ForeignKey('ROLES.id'), nullable=False)
    role = db.relationship('Role', back_populates='users')
    permissions = db.relationship('Permission', secondary=user_permissions)
    is_active = Column(db.Boolean, default=True)
    employee = relationship("Employee", backref="users")  # Link to Employee
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

    def get_id(self):
        return str(self.id)
    
    def can(self, resource, action):
        # Get permissions from role and user (empty lists if none)
        role_perms = self.role.permissions if self.role else []
        user_perms = self.permissions if self.permissions else []

        # Combine and filter out deleted permissions
        all_permissions = [p for p in role_perms + user_perms if not getattr(p, 'deleted', False)]

        # Check if any permission matches resource and action
        return any(p.resource == resource and p.action == action for p in all_permissions)
    
    # def can(self, resource, action):
    #     permissions = self.role.permissions if self.role else []
    #     all_permissions = permissions + self.permissions
    #     # for p in all_permissions:
    #     #     print(f"Checking Permission: {p.resource}:{p.action}")
    #     return any(p.resource == resource and p.action == action for p in all_permissions)
    
    def __str__(self):
        return f'ID: {self.id}\nUsername: {self.username}\nRole: {self.role_id}\nActive: {self.is_active}'
    
## COMMITTEE TRACKER MODELS
class AcademicYear(db.Model):
    __tablename__ = 'ACADEMIC_YEARS'
    id = Column(Integer, primary_key=True)
    year = Column(String(20), nullable=False, unique=True)  # Example: "2024-2025"
    is_current = Column(Boolean, default=False)
    ay_committee = relationship("AYCommittee", back_populates="academic_year")
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))
    
    def __str__(self):
        return f'Year: {self.year}\nCommittees: {self.ay_committee}'

class CommitteeType(db.Model):
    __tablename__ = 'COMMITTEE_TYPES'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False)
    committees = relationship('Committee', backref='committee_type', lazy=True)
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

class FrequencyType(db.Model):
    __tablename__ = 'FREQUENCY_TYPES'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False)
    multiplier = Column(Integer, nullable=False)
    ay_committees = relationship("AYCommittee", back_populates="meeting_frequency_type")
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

class Committee(db.Model):
    __tablename__ = 'BASE_COMMITTEES'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    short_name = Column(String(50))
    description = Column(String(255))
    reporting_start = Column(Integer)
    mission = Column(String(8000))
    committee_type_id = Column(Integer, ForeignKey('COMMITTEE_TYPES.id'))    
    active = Column(Boolean, default=True)
    ay_committee = relationship('AYCommittee', back_populates='committee', lazy='dynamic')
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))
    def __str__(self):
        return f'ID: {self.id}\nCommittee: {self.name}\nShort name: {self.short_name}\nDescription: {self.description}\nMission: {self.mission} \
        \nReporting start: {self.reporting_start}\nType: {self.committee_type_id}'
       
class AYCommittee(db.Model):
    __tablename__ = 'AY_COMMITTEES'    
    id = Column(Integer, primary_key=True)
    committee_id = Column(Integer, ForeignKey('BASE_COMMITTEES.id', ondelete='RESTRICT'), nullable=False)
    academic_year_id = Column(Integer, ForeignKey('ACADEMIC_YEARS.id', ondelete='RESTRICT'), nullable=False)
    meeting_frequency_type_id = Column(Integer, ForeignKey('FREQUENCY_TYPES.id'))
    meeting_duration_in_minutes = Column(Integer)
    supplemental_minutes_per_frequency = Column(Integer)
    active = Column(Boolean, default=True)
    finalized = Column(Boolean, default=False)
    finalized_date = Column(DateTime, nullable=True)
    finalized_by = Column(Integer, ForeignKey('USERS.id'))
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))
    # Relationships
    members = relationship(
        "Member",
        primaryjoin="and_(Member.ay_committee_id==AYCommittee.id, Member.deleted==False)",
        back_populates="ay_committee"
    )
    fileuploads = relationship("FileUpload", back_populates="ay_committee", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="ay_committee", cascade="all, delete-orphan")
    academic_year = relationship("AcademicYear", back_populates="ay_committee", cascade="all")
    committee = relationship('Committee', back_populates='ay_committee', lazy='joined')
    meeting_frequency_type = relationship("FrequencyType", back_populates="ay_committees")
    finalized_user = relationship("User", foreign_keys=[finalized_by])

    __table_args__ = (
        UniqueConstraint('committee_id', 'academic_year_id', name='_committee_ay_uc'),
    )

    def __str__(self):
        return f'Committee: {self.committee.name}\nAY: {self.academic_year.year}'

class Meeting(db.Model):
    __tablename__ = 'MEETINGS'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)  
    date = Column(Date, nullable=False)
    location = Column(String(255))
    notes = Column(Text)    
    ay_committee_id = Column(Integer, ForeignKey("AY_COMMITTEES.id"), nullable=False)
    ay_committee = relationship("AYCommittee", back_populates="meetings")
    attendance = relationship("Attendance", back_populates="meeting", cascade="all, delete-orphan")
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

class Attendance(db.Model):
    __tablename__ = 'ATTENDANCE'
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("MEETINGS.id"), nullable=False)
    member_id = Column(db.Integer, db.ForeignKey("MEMBERS.id"), nullable=False)
    status = Column(db.Enum("Present", "Absent", "Excused", name="attendance_status"))
    meeting = db.relationship("Meeting", back_populates="attendance")
    member = db.relationship(
        "Member",
        primaryjoin="and_(Attendance.member_id==Member.id, Member.deleted==False, Attendance.deleted==False)",
        backref="attendance"
    )
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

class FileUpload(db.Model):
    __tablename__ = 'FILE_UPLOADS'
    id = Column(Integer, primary_key=True)
    filename = Column(String(50), nullable=False)
    ay_committee_id = Column(Integer, ForeignKey("AY_COMMITTEES.id"), nullable=False)
    ay_committee = relationship("AYCommittee", back_populates="fileuploads")
    upload_date = Column(DateTime, default=datetime.now)
    upload_by = Column(Integer, ForeignKey('USERS.id'))
    delete_date = Column(DateTime)
    deleted = Column(Boolean, default=False)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

class Employee(db.Model):
    __tablename__ = 'EMPLOYEES'
    employee_id = Column(Integer, primary_key=True)
    employee_name = Column(String(100), nullable=False)
    employee_first_name = Column(String(50), nullable=False)
    employee_last_name = Column(String(50), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(50), unique=True)
    reports_to_id = Column(Integer, ForeignKey('EMPLOYEES.employee_id'))
    department = Column(String(255))
    employee_type = Column(String(50))
    employee_status = Column(String(50))
    position_class = Column(String(50))
    job_code = Column(String(50))
    job_start_date = Column(DateTime)
    job_code_description = Column(String(255))
    mail_code = Column(String(50))
    building = Column(String(255))
    room = Column(String(50))

        # Add a class-level dictionary for labels
    display_labels = {
        'employee_id': 'Employee ID',
        'employee_name': 'Full Name',
        'employee_first_name': 'First Name',
        'employee_last_name': 'Last Name',
        'username': 'Username',
        'email': 'Email Address',
        'reports_to_id': 'Supervisor',
        'department': 'Department',
        'employee_type': 'Employee Type',
        'employee_status': 'Employment Status',
        'position_class': 'Position Class',
        'job_code': 'Job Code',
        'job_code_start_date': 'Job Code Start Date',
        'job_code_description': 'Job Description',
        'mail_code': 'Mail Code',
        'job_location': 'Job Location',
        'building': 'Building',
        'room': 'Room',
    }

    def to_dict(self, include_labels=False):
        """
        Returns a dictionary where each key is the original column name.
        If include_labels=True, values are dicts with 'label' and 'value'.
        """
        result = {}
        for c in self.__table__.columns:
            key = c.name
            value = getattr(self, key)
            if include_labels:
                result[key] = {
                    'label': self.display_labels.get(key, key),
                    'value': value
                }
            else:
                result[key] = value
        return result

class Member(db.Model):
    __tablename__ = 'MEMBERS'    
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('EMPLOYEES.employee_id'), nullable=False)
    member_role_id = Column(Integer, ForeignKey('MEMBER_ROLES.id'), nullable=False)
    ay_committee_id = Column(Integer, ForeignKey('AY_COMMITTEES.id'), nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    voting = Column(Boolean, default=True)
    allow_edit = Column(Boolean, default=False)
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    notes = Column(String(255))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

    # Relationships
    ay_committee = relationship("AYCommittee", back_populates="members")
    employee = relationship("Employee", backref="members")
    member_role = relationship("MemberRole", backref="members")

class MemberType(db.Model):
    __tablename__ = 'MEMBER_TYPES'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), unique=True)
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

class MemberRole(db.Model):
    __tablename__ = 'MEMBER_ROLES'
    id = Column(Integer, primary_key=True)
    role = Column(String(50), nullable=False)
    description = Column(String(500))
    default_order = Column(Integer)
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, ForeignKey('USERS.id'))
    modify_date = Column(DateTime)
    modify_by = Column(Integer, ForeignKey('USERS.id'))
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    delete_by = Column(Integer, ForeignKey('USERS.id'))

    # def __str__(self):
    #     return f'Role: {self.role}\nDescription: {self.description}\nVoting: {self.voting}'

# Scheduler Models
class ScheduledRecording(db.Model):
    __tablename__ = 'SCHEDULED_RECORDINGS'
    id = Column(db.Integer, primary_key=True)
    canvas_event_id = Column(db.Integer, nullable=False)
    title = Column(db.String(255), nullable=False)
    start_time = Column(db.DateTime, nullable=False)
    end_time = Column(db.DateTime, nullable=False)
    folder_id = Column(db.String(255))
    recorder_id = Column(db.String(255))
    panopto_session_id = Column(db.String(255))
    broadcast = Column(Boolean, default=False)
    create_date = Column(db.DateTime, default=datetime.now)

class CalendarGroupSelection(db.Model):
    __tablename__ = 'CALENDAR_GROUP_SELECTIONS'
    id = Column(db.Integer, primary_key=True)
    group_name = Column(db.String(50), nullable=False)
    course_id = Column(db.String(50), nullable=False)
    course_name = Column(db.String(255), nullable=False)
    timestamp = Column(db.DateTime, default=datetime.now)

class CalendarGroup(db.Model):
    __tablename__ = 'CALENDAR_GROUPS'
    id = Column(db.Integer, primary_key=True)
    name = Column(db.String(100), nullable=False)
    ics_filename = Column(db.String(100), nullable=False)


class Student(db.Model):
    __tablename__ = 'STUDENTS'
    id = Column(Integer, primary_key=True)
    pid = Column(String(50), nullable=False)
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    middle_name = Column(String(255))
    suffix = Column(String(50))
    pronoun = Column(String(50))
    loa = Column(Boolean, default=False)
    phonetic_first_name = Column(String(255))
    phonetic_last_name = Column(String(255))
    lived_first_name = Column(String(255))
    lived_last_name = Column(String(255))
    class_of = Column(String(50))
    photo_url = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    create_by = Column(Integer, nullable=False)
    update_date = Column(DateTime)
    update_by = Column(Integer)
    delete_date = Column(DateTime)
    delete_by = Column(Integer)
    deleted = Column(Boolean, default=False)
    
class Listserv(db.Model):
    __tablename__ = 'LISTSERV'
    id = Column(db.Integer, primary_key=True)
    group_name = Column(db.String(128), unique=True, nullable=False)
    create_date = Column(db.DateTime, default=datetime.now())
    create_by = Column(Integer, nullable=False)
    delete_date = Column(db.DateTime, nullable=True)
    delete_by = Column(Integer)
    deleted = Column(db.Boolean, default=False)

# RECHARGE APP
class ProjectTaskCode(db.Model):
    __bind_key__ = 'rechargedb' 
    __tablename__ = 'ProjectTaskCodes'
    entity_code = db.Column(db.String(20), primary_key=True)
    project_task_code = db.Column(db.String(20), primary_key=True)
    funding_source_code = db.Column(db.String(50), primary_key=True)
    funding_source = db.Column(db.String(500), primary_key=True)
    pi_email = db.Column(db.String(50), nullable=False)
    pi_name = db.Column(db.String(50), nullable=False)
    fund_manager_name = db.Column(db.String(50), nullable=False)
    fund_manager_email = db.Column(db.String(50), nullable=False)
    status = Column(db.String(20), nullable=False)  # e.g., 'Active', 'Inactive'

class Chartstring(db.Model):
    __bind_key__ = 'rechargedb'
    __tablename__ = 'Chartstrings'

    entity_code = db.Column(db.String(20), nullable=False)
    fund_code = db.Column(db.String(20), nullable=False)
    financial_unit_code = db.Column(db.String(20), nullable=False)
    account_code = db.Column(db.String(20), nullable=False)
    function_code = db.Column(db.String(20), nullable=False)
    project_code = db.Column(db.String(20), nullable=False)
    chartstring = db.Column(db.String(200), primary_key=True)
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return (
            f"<Chartstring(entity_code={self.entity_code}, fund_code={self.fund_code}, "
            f"financial_unit_code={self.financial_unit_code}, account_code={self.account_code}, "
            f"function_code={self.function_code}, project_code={self.project_code}, "
            f"status={self.status})>"
        )

class InstrumentRequest(db.Model):
    __bind_key__ = 'rechargedb' 
    __tablename__ = 'InstrumentRequests'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4())) # For general UUID handling   
    machine_name = Column(db.String(255), nullable=False)
    department_code = Column( db.String(20), db.ForeignKey("DEPARTMENTS.code"), nullable=False )
    department = db.relationship( "Department", back_populates="instrument_requests" )
    pi_name = Column(db.String(100), nullable=False)
    pi_email = Column(db.String(120), nullable=False)
    pi_phone = Column(db.String(20))
    # ad_username = Column(db.String(50), nullable=False)
    requestor_name = Column(db.String(50), nullable=False)
    requestor_position = Column(db.String(100), nullable=False)
    requestor_email = Column(db.String(120), nullable=False)
    requestor_phone = Column(db.String(20))
    had_training = Column(db.Boolean, nullable=False, default=False)
    project_task_code = Column(db.String(50), nullable=False)
    funding_source_code = db.Column(db.String(50), nullable=False)
    status = Column(db.String(20), default="Pending")  # Pending, Approved, Denied, Cancelled
    notes = db.Column(db.Text)
    created_at = Column(db.DateTime, default=datetime.now)
    approved_at = Column(db.DateTime)
    approved_by = Column(db.String(50))  # AD username of reviewer

    # relationship to Employee (different bind)
    approver = db.relationship(
        "Employee",
        primaryjoin="foreign(InstrumentRequest.approved_by) == Employee.username",
        uselist=False,
        viewonly=True
    )

class Instrument(db.Model):
    __bind_key__ = 'rechargedb'
    __tablename__ = 'InstrumentConfig'
    machine_name = db.Column(db.String(255), primary_key=True, nullable=False)
    charge = db.Column(db.Numeric, nullable=False)
    min_duration = db.Column(db.Numeric, nullable=False)
    duration_type = db.Column(db.String(10), nullable=False)
    min_increment = db.Column(db.Numeric, nullable=False)
    increment_type = db.Column(db.String(10), nullable=False)
    flag = db.Column(db.Boolean, nullable=False)  # True = active
    
class Department(db.Model):
    __bind_key__ = 'rechargedb'
    __tablename__ = 'DEPARTMENTS'
    code = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    # Backref to instrument requests
    instrument_requests = db.relationship(
        "InstrumentRequest",
        back_populates="department"
    )