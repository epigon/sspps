from app import db
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import event, Column, Integer, String, DateTime, UniqueConstraint, ForeignKey, Boolean, Date, Time, Text #create_engine, 
from sqlalchemy.orm import relationship, object_session

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
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

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
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)
    
    def __str__(self):
        return f'Year: {self.year}\nCommittees: {self.ay_committee}'

class CommitteeType(db.Model):
    __tablename__ = 'COMMITTEE_TYPES'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False)
    committees = relationship('Committee', backref='committee_type', lazy=True)
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)


class FrequencyType(db.Model):
    __tablename__ = 'FREQUENCY_TYPES'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), nullable=False)  
    committees = relationship('Committee', backref='frequency_type', lazy=True)
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)


class Committee(db.Model):
    __tablename__ = 'BASE_COMMITTEES'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    short_name = Column(String(50))
    description = Column(String(255))
    reporting_start = Column(Integer)
    mission = Column(String(8000))
    frequency_type_id = Column(Integer, ForeignKey('FREQUENCY_TYPES.id'))
    committee_type_id = Column(Integer, ForeignKey('COMMITTEE_TYPES.id'))    
    active = Column(Boolean, default=True)
    ay_committee = relationship('AYCommittee', back_populates='committee', lazy='dynamic')
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)


    def __str__(self):
        return f'ID: {self.id}\nCommittee: {self.name}\nShort name: {self.short_name}\nDescription: {self.description}\nMission: {self.mission} \
        \nReporting start: {self.reporting_start}\nFrequency Type: {self.frequency_type_id}\nType: {self.committee_type_id}'
    
class AYCommittee(db.Model):
    __tablename__ = 'AY_COMMITTEES'
    id = Column(Integer, primary_key=True)
    committee_id = Column(Integer, ForeignKey('BASE_COMMITTEES.id', ondelete='RESTRICT'), nullable=False)
    academic_year_id = Column(Integer, ForeignKey('ACADEMIC_YEARS.id', ondelete='RESTRICT'), nullable=False)
    members = relationship("Member", back_populates="ay_committee", cascade="all, delete-orphan")
    fileuploads = relationship("FileUpload", back_populates="ay_committee", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="ay_committee", cascade="all, delete-orphan")
    academic_year = relationship("AcademicYear", back_populates="ay_committee", cascade="all")
    active = Column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('committee_id', 'academic_year_id', name='_committee_ay_uc'),)
    committee = relationship('Committee', back_populates='ay_committee', lazy='joined')
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

    def __str__(self):
        return f'Committee: {self.committee.name}\nAY: {self.academic_year.year}'

class Meeting(db.Model):
    __tablename__ = 'MEETINGS'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)  
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    location = Column(String(255), nullable=False)
    notes = Column(Text)    
    ay_committee_id = Column(Integer, ForeignKey("AY_COMMITTEES.id"), nullable=False)
    ay_committee = relationship("AYCommittee", back_populates="meetings")
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)    

class FileUpload(db.Model):
    __tablename__ = 'FILE_UPLOADS'
    id = Column(Integer, primary_key=True)
    filename = Column(String(50), nullable=False)
    ay_committee_id = Column(Integer, ForeignKey("AY_COMMITTEES.id"), nullable=False)
    ay_committee = relationship("AYCommittee", back_populates="fileuploads")
    # upload_by = Column(Integer, ForeignKey('ADUsers.employee_id'))
    upload_date = Column(DateTime, default=datetime.now)
    delete_date = Column(DateTime)
    deleted = Column(Boolean, default=False)
    delete_by = Column(Integer, ForeignKey('EMPLOYEES.employee_id'))

class Employee(db.Model):
    __tablename__ = 'EMPLOYEES'
    employee_id = Column(Integer, primary_key=True)
    employee_name = Column(String(100), nullable=False)
    employee_first_name = Column(String(50), nullable=False)
    employee_last_name = Column(String(50), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(50), unique=True)
    # reports_to_ad = Column(String(50))
    reports_to_id = Column(Integer, ForeignKey('EMPLOYEES.employee_id'))
    department = Column(String(255))
    employee_type = Column(String(50))
    employee_status = Column(String(50))
    position_class = Column(String(50))
    job_code = Column(String(50))
    job_code_start_date = Column(DateTime)
    job_code_description = Column(String(255))
    mail_code = Column(String(50))
    job_location = Column(String(255))
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

    # def to_dict(self, readable=False):
    #     """
    #     Returns dictionary of field names and values.
    #     If readable=True, use human-readable keys.
    #     """
    #     if readable:
    #         return {
    #             self.display_labels.get(c.name, c.name): getattr(self, c.name)
    #             for c in self.__table__.columns
    #         }
    #     else:
    #         return {c.name: getattr(self, c.name) for c in self.__table__.columns}
        

class Member(db.Model):
    __tablename__ = 'MEMBERS'
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('EMPLOYEES.employee_id'), nullable=False)
    member_role_id = Column(Integer, ForeignKey('MEMBER_ROLES.id'), nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    ay_committee_id = Column(Integer, ForeignKey('AY_COMMITTEES.id'), nullable=False)
    ay_committee = relationship("AYCommittee", back_populates="members")
    voting = Column(Boolean, default=True)
    create_date = Column(DateTime, default=datetime.now)
    notes = Column(String(255))
    delete_date = Column(DateTime)
    deleted = Column(Boolean, default=False)
    # delete_by = Column(Integer, ForeignKey('ADUsers.employee_id'))
    employee = relationship("Employee", backref="members")  # Link to Employee
    member_role = relationship("MemberRole", backref="members")  # Link to MemberRole

    # def __str__(self):
    #     return f'Member: {self.member}\nType: {self.member_type_id}\nRole: {self.member_role_id}'

class MemberType(db.Model):
    __tablename__ = 'MEMBER_TYPES'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), unique=True)
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)


class MemberTask(db.Model):
    __tablename__ = 'MEMBER_TASKS'
    id = Column(Integer, primary_key=True)
    task = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)


class MemberRole(db.Model):
    __tablename__ = 'MEMBER_ROLES'
    id = Column(Integer, primary_key=True)
    role = Column(String(50), nullable=False)
    description = Column(String(500))
    default_order = Column(Integer)
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

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
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(128), unique=True, nullable=False)
    create_date = db.Column(db.DateTime, default=datetime.now())
    create_by = Column(Integer, nullable=False)
    delete_date = db.Column(db.DateTime, nullable=True)
    delete_by = Column(Integer)
    deleted = db.Column(db.Boolean, default=False)