from flask_login import UserMixin
from datetime import datetime
from app import db
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Date, Time, Text, UniqueConstraint
from sqlalchemy.orm import relationship, object_session
from sqlalchemy import event

# === ADMIN MODELS ===
user_permissions = db.Table('USER_PERMISSIONS',
    db.Column('user_id', db.Integer, db.ForeignKey('USERS.id', ondelete='RESTRICT')),
    db.Column('permission_id', db.Integer, db.ForeignKey('PERMISSIONS.id', ondelete='RESTRICT'))
)

role_permissions = db.Table('ROLE_PERMISSIONS',
    db.Column('role_id', db.Integer, db.ForeignKey('ROLES.id', ondelete='RESTRICT')),
    db.Column('permission_id', db.Integer, db.ForeignKey('PERMISSIONS.id', ondelete='RESTRICT'))
)

class Role(db.Model):
    __tablename__ = 'ROLES'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    permissions = db.relationship('Permission', secondary=role_permissions)
    users = db.relationship('User', back_populates='role')
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class Permission(db.Model):
    __tablename__ = 'PERMISSIONS'
    id = db.Column(db.Integer, primary_key=True)
    resource = db.Column(db.String(64))
    action = db.Column(db.String(64))
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class User(UserMixin, db.Model):
    __tablename__ = 'USERS'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('EMPLOYEES.employee_id', ondelete='RESTRICT'), nullable=False)
    username = db.Column(db.String(64), unique=True, nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('ROLES.id', ondelete='RESTRICT'), nullable=False)
    role = db.relationship('Role', back_populates='users')
    permissions = db.relationship('Permission', secondary=user_permissions)
    is_active = db.Column(db.Boolean, default=True)
    employee = relationship("Employee", backref="users")
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

    def get_id(self):
        return str(self.id)

    def can(self, resource, action):
        permissions = self.role.permissions if self.role else []
        all_permissions = permissions + self.permissions
        return any(p.resource == resource and p.action == action for p in all_permissions)

# === COMMITTEE TRACKER MODELS ===
class AcademicYear(db.Model):
    __tablename__ = 'ACADEMIC_YEARS'
    id = Column(Integer, primary_key=True)
    year = Column(String(20), nullable=False, unique=True)
    is_current = Column(Boolean, default=False)
    ay_committee = relationship("AYCommittee", back_populates="academic_year")
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class CommitteeType(db.Model):
    __tablename__ = 'COMMITTEE_TYPES'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), unique=True)
    committees = relationship('Committee', backref='committee_type', lazy=True)
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class FrequencyType(db.Model):
    __tablename__ = 'FREQUENCY_TYPES'
    id = Column(Integer, primary_key=True)
    type = Column(String(50), unique=True)
    committees = relationship('Committee', backref='frequency_type', lazy=True)    
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class Committee(db.Model):
    __tablename__ = 'BASE_COMMITTEES'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    short_name = Column(String(50))
    description = Column(String(255))
    reporting_start = Column(Integer)
    mission = Column(String(8000))
    frequency_type_id = Column(Integer, ForeignKey('FREQUENCY_TYPES.id', ondelete='RESTRICT'))
    committee_type_id = Column(Integer, ForeignKey('COMMITTEE_TYPES.id', ondelete='RESTRICT'))
    active = Column(Boolean, default=True)
    ay_committee = relationship('AYCommittee', back_populates='committee', lazy='dynamic')    
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class AYCommittee(db.Model):
    __tablename__ = 'AY_COMMITTEES'
    id = Column(Integer, primary_key=True)
    committee_id = Column(Integer, ForeignKey('BASE_COMMITTEES.id', ondelete='RESTRICT'), nullable=False)
    academic_year_id = Column(Integer, ForeignKey('ACADEMIC_YEARS.id', ondelete='RESTRICT'), nullable=False)
    members = relationship("Member", back_populates="ay_committee")
    fileuploads = relationship("FileUpload", back_populates="ay_committee")
    meetings = relationship("Meeting", back_populates="ay_committee")
    academic_year = relationship("AcademicYear", back_populates="ay_committee")
    active = Column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('committee_id', 'academic_year_id', name='_committee_ay_uc'),)
    committee = relationship('Committee', back_populates='ay_committee', lazy='joined')    
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class Meeting(db.Model):
    __tablename__ = 'MEETINGS'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)  
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    location = Column(String(255), nullable=False)
    notes = Column(Text)    
    ay_committee_id = Column(Integer, ForeignKey("AY_COMMITTEES.id", ondelete='RESTRICT'), nullable=False)
    ay_committee = relationship("AYCommittee", back_populates="meetings")    
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

class FileUpload(db.Model):
    __tablename__ = 'FILE_UPLOADS'
    id = Column(Integer, primary_key=True)
    filename = Column(String(50), nullable=False)
    ay_committee_id = Column(Integer, ForeignKey("AY_COMMITTEES.id", ondelete='RESTRICT'), nullable=False)
    ay_committee = relationship("AYCommittee", back_populates="fileuploads")
    upload_date = Column(DateTime, default=datetime.now)
    delete_date = Column(DateTime)
    deleted = Column(Boolean, default=False)
    delete_by = Column(Integer, ForeignKey('EMPLOYEES.employee_id', ondelete='RESTRICT'))

class Employee(db.Model):
    __tablename__ = 'EMPLOYEES'
    employee_id = Column(Integer, primary_key=True)
    employee_name = Column(String(100), nullable=False)
    employee_first_name = Column(String(50), nullable=False)
    employee_last_name = Column(String(50), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(50), unique=True)
    reports_to_ad = Column(String(50))
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

class Member(db.Model):
    __tablename__ = 'MEMBERS'
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('EMPLOYEES.employee_id', ondelete='RESTRICT'), nullable=False)
    member_role_id = Column(Integer, ForeignKey('MEMBER_ROLES.id', ondelete='RESTRICT'), nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    ay_committee_id = Column(Integer, ForeignKey('AY_COMMITTEES.id', ondelete='RESTRICT'), nullable=False)
    ay_committee = relationship("AYCommittee", back_populates="members")
    voting = Column(Boolean, default=True)
    notes = Column(String(255))
    employee = relationship("Employee", backref="members")
    member_role = relationship("MemberRole", backref="members")
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

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
    role = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    default_order = Column(Integer)
    create_date = Column(DateTime, default=datetime.now)
    deleted = Column(Boolean, default=False)
    delete_date = Column(DateTime)

# # === DELETE PREVENTION HOOKS ===
# @event.listens_for(Committee, 'before_delete')
# def prevent_committee_deletion(mapper, connection, target):
#     if target.ay_committee.count() > 0:
#         raise ValueError("Cannot delete this Base Committee because it's assigned to one or more Academic Years.")

# @event.listens_for(AcademicYear, 'before_delete')
# def prevent_academic_year_deletion(mapper, connection, target):
#     if target.ay_committee:
#         raise ValueError("Cannot delete this Academic Year because it has assigned committees.")

# @event.listens_for(AYCommittee, 'before_delete')
# def prevent_ay_committee_deletion(mapper, connection, target):
#     if target.members or target.fileuploads or target.meetings:
#         raise ValueError("Cannot delete this AYCommittee because it has associated members, files, or meetings.")
