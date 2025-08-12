from flask_wtf import FlaskForm
from wtforms.widgets import CheckboxInput, ListWidget
from wtforms import widgets, BooleanField, DateField, DateTimeLocalField, FileField, HiddenField, IntegerField, \
    SelectField, SelectMultipleField, StringField, SubmitField, TelField, TextAreaField, TimeField, ValidationError
from wtforms.validators import DataRequired, Email, InputRequired, Length, Optional, ValidationError
from app.models import Committee, Department, Employee, Machine, Permission, ProjectTaskCode, Role, User

MONTHS = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'),
    ('4', 'April'), ('5', 'May'), ('6', 'June'),
    ('7', 'July'), ('8', 'August'), ('9', 'September'),
    ('10', 'October'), ('11', 'November'), ('12', 'December')
]

class CSRFOnlyForm(FlaskForm):
    pass

## ADMIN FORMS
class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()

class UserForm(FlaskForm):
    username = StringField('Username')
    employee_id = SelectField('Select Employee', coerce=int)  # Only shown when adding
    role_id = SelectField('Role', coerce=int, validators=[DataRequired()])
    permissions = MultiCheckboxField('Additional Permissions', coerce=int)
    submit = SubmitField('Save')

    def __init__(self, *args, original_username=None, existing_usernames=None, employees=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username
        if employees:
            # Filter out users with existing usernames
            available_employees = [
                e for e in employees if e.username not in existing_usernames
            ]

            # Sort by last name
            available_employees.sort(key=lambda e: e.employee_last_name)

            # Add a blank option and then the rest
            self.employee_id.choices = [(0, 'Select an employee')] + [
                (e.employee_id, f"{e.employee_last_name}, {e.employee_first_name}") for e in available_employees
            ]

        # Remove employee_id field when editing (user already exists)
        if original_username:  # or you could check for `kwargs.get("obj") and kwargs["obj"].id`
            del self.employee_id

    def validate_username(self, field):
        if not self.original_username:
            return  # Skip validation on creation (new user)

        if not field.data:
            raise ValidationError("Username is required.")

        if field.data == self.original_username:
            return

        if not Employee.query.filter_by(username=field.data).first():
            raise ValidationError("That username does not match any employee.")

        if User.query.filter_by(username=field.data, deleted=False).first():
            raise ValidationError("That username is already taken.")

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.role_id.choices = [(r.id, r.name) for r in Role.query.all()]
    #     self.permissions.choices = [(p.id, f"{p.resource}:{p.action}") for p in Permission.query.all()]

class RoleForm(FlaskForm):
    name = StringField('Role Name', validators=[DataRequired()])
    permissions = MultiCheckboxField('Permissions', coerce=int)
    submit = SubmitField('Save')

    def __init__(self, original_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_name = original_name

    def validate_name(self, field):
        # If editing and name hasn't changed, skip validation
        if self.original_name and field.data == self.original_name:
            return
        if Role.query.filter_by(name=field.data, deleted=False).first():
            raise ValidationError("That role already exists.")
    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.permissions.choices = [(p.id, f"{p.resource}:{p.action}") for p in Permission.query.all()]

class PermissionForm(FlaskForm):
    resource = StringField('Resource', validators=[DataRequired()])
    action = StringField('Action', validators=[DataRequired()])
    submit = SubmitField('Save')

    def __init__(self, original_resource=None, original_action=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_resource = original_resource
        self.original_action = original_action

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False

        # Only validate uniqueness if the resource/action has changed
        resource_changed = self.resource.data != self.original_resource
        action_changed = self.action.data != self.original_action

        if resource_changed or action_changed:
            exists = Permission.query.filter_by(
                resource=self.resource.data,
                action=self.action.data, 
                deleted=False
            ).first()
            if exists:
                self.resource.errors.append('That resource/action combination already exists.')
                return False

        return True
    
## COMMITTEE TRACKER FORMS
class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

# class OrganizationForm(FlaskForm):
#     orgName = StringField('Organization Name', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})
#     logo = FileField('Logo', render_kw={'accept': "image/*"})
    
class AcademicYearForm(FlaskForm):
    year = StringField('Academic Year', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})
    is_current = BooleanField('Current Academic Year', default=False)

class CommitteeTypeForm(FlaskForm):
    type = StringField('Committee Type', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})

class FrequencyTypeForm(FlaskForm):
    type = StringField('Frequency', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})
    multiplier =  IntegerField('Occurrences per year', validators=[InputRequired()], render_kw={'autofocus': True})

class MemberTypeForm(FlaskForm):
    type = StringField('Member Type', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})

class MemberRoleForm(FlaskForm):
    role = StringField('Role', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})
    description = StringField('Description', validators=[Length(max=500)])
    functions = StringField('Functions', validators=[Length(max=255)])

class MemberTaskForm(FlaskForm):
    task = StringField('Task', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})
    description = StringField('Description', validators=[Length(max=50)])

class CommitteeForm(FlaskForm):
    name = StringField('Name', validators=[InputRequired(), Length(max=100)], render_kw={'autofocus': True})
    short_name = StringField('Short Name', validators=[Length(max=50)])
    description = TextAreaField('Description', validators=[Length(max=255)])
    reporting_start = SelectField('Reporting Start', choices=MONTHS, validators=[DataRequired()])
    mission = TextAreaField('Mission Statement', validators=[Length(max=4000)])
    frequency_type_id = SelectField('Reporting Frequency', choices=[], validators=[DataRequired()])
    committee_type_id = SelectField('Committee Type', choices=[], validators=[DataRequired()])

    def __init__(self, original_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_name = original_name

    def validate_name(self, field):
        # If editing and name hasn't changed, skip validation
        if self.original_name and field.data == self.original_name:
            return
        if Committee.query.filter_by(name=field.data, deleted=False).first():
            raise ValidationError("That committee already exists.")

class AYCommitteeForm(FlaskForm):
    committee_id = SelectField('Committee', validators=[InputRequired()], choices=[])
    academic_year_id = SelectField('Academic Year', validators=[InputRequired()], choices=[])

class CommitteeReportForm(FlaskForm):
    academic_year = SelectMultipleField('Academic Year', 
                            validators=[DataRequired()], 
                            coerce=int, 
                            choices=[], 
                            )  
    committee = SelectMultipleField('Committee', 
                            validators=[DataRequired()], 
                            coerce=int, 
                            choices=[]
                            )  
    users = SelectMultipleField('Employee', 
                            validators=[DataRequired()], 
                            coerce=int, 
                            choices=[]
                            ) 
    committee_type = SelectMultipleField('Committee Type', 
                            validators=[DataRequired()], 
                            coerce=int, 
                            choices=[]
                            ) 
    sort_by_role = BooleanField('Sort Members by Roles', default=False)
    show_mission = BooleanField('Show Mission Statements', default=True)
    show_members = BooleanField('Show Members', default=True)
    show_documents = BooleanField('Show Documents', default=True)
    show_meetings = BooleanField('Show Meetings', default=True)
    submit = SubmitField('Apply Filters')

class MemberForm(FlaskForm):
    ay_committee_id = HiddenField('AYCommittee', validators=[DataRequired()])
    employee_id = SelectField('Select Member', choices=[], validators=[DataRequired()])
    member_role_id = SelectField('Select Role', choices=[], validators=[DataRequired()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])    
    voting = BooleanField('Voting Member', default=True)
    notes = TextAreaField('Notes', validators=[Length(max=255)])
    submit = SubmitField('Submit')    

    def validate_end_date(self, field):
        if self.start_date.data and field.data:
            if field.data <= self.start_date.data:
                raise ValidationError('End Date must be later than Start Date.')
            
class MeetingForm(FlaskForm):
    ay_committee_id = HiddenField('AYCommittee', validators=[DataRequired()])
    title = StringField('Meeting Title', validators=[DataRequired()])
    date = DateField('Meeting Date', validators=[DataRequired()], format='%Y-%m-%d')
    start_time = TimeField('Start Time', validators=[DataRequired()])
    end_time = TimeField('End Time', validators=[DataRequired()])
    location = StringField('Location', validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])

    def validate_end_time(self, field):
        if self.start_time.data and field.data:
            if field.data <= self.start_time.data:
                raise ValidationError('End Time must be later than Start Time.')

class FileUploadForm(FlaskForm):
    ay_committee_id = HiddenField('AYCommittee', validators=[DataRequired()])
    files = FileField('Files', render_kw={'accept': "image/*"})

class CalendarGroupForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    ics_filename = StringField('ICS Filename', validators=[DataRequired()])
    submit = SubmitField('Save')

class StudentForm(FlaskForm):
    pid = StringField("PID", validators=[DataRequired()])
    username = StringField("Username", validators=[DataRequired()])
    email = StringField("Email", validators=[Optional(), Email()])
    first_name = StringField("First Name", validators=[DataRequired()])
    last_name = StringField("Last Name", validators=[DataRequired()])
    middle_name = StringField("Middle Name", validators=[Optional()])
    suffix = StringField("Suffix", validators=[Optional()])
    pronoun = StringField("Pronoun", validators=[Optional()])
    loa = BooleanField("LOA")
    phonetic_first_name = StringField("Phonetic First Name", validators=[Optional()])
    phonetic_last_name = StringField("Phonetic Last Name", validators=[Optional()])
    lived_first_name = StringField("Lived First Name", validators=[Optional()])
    lived_last_name = StringField("Lived Last Name", validators=[Optional()])
    class_of = StringField("Class Of", validators=[Optional()])
    photo_url = StringField("Photo URL", validators=[Optional()])
    photo_file = FileField("Upload New Photo")

class GroupForm(FlaskForm):
    group_name = StringField('Google Group Name', validators=[DataRequired()])

# RECHARGE APP
class InstrumentRequestForm(FlaskForm):
    instrument = SelectField("Instrument", coerce=int, validators=[DataRequired()])
    department_code = SelectField('Department', validators=[DataRequired()])
    pi_name = StringField("PI Name", validators=[DataRequired()])
    pi_email = StringField("PI Email", validators=[DataRequired(), Email()])
    pi_phone = TelField("PI Phone")
    ad_username = StringField("Requestor AD Username", validators=[DataRequired()])
    requestor_position = StringField("Requestor Position", validators=[DataRequired()])
    requestor_email = StringField("Requestor Email", validators=[DataRequired(), Email()])
    requestor_phone = TelField("Requestor Phone")
    requires_training = BooleanField("Requires Training?")
    project_number = StringField("Project Number", validators=[DataRequired()])
    task_code = StringField("Task Code", validators=[DataRequired()])
    start_datetime = DateTimeLocalField('Start Date and Time', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    end_datetime = DateTimeLocalField( 'End Date and Time', format='%Y-%m-%dT%H:%M', validators=[DataRequired()])
    submit = SubmitField("Submit Request")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instrument.choices = [
            (0, '--- Select a Machine ---') 
        ] + [
            (m.MachineId, m.MachineName)
            for m in Machine.query.filter_by(MachineStatus=True)
                .order_by(Machine.MachineName)
                .all()
        ]
        # Populate Department choices: value=department.code, label=department.name
        departments = Department.query.order_by(Department.name).all()
        dept_choices = [(d.code, d.code +" - "+ d.name) for d in departments]
        self.department_code.choices = [('', '--- Select a Department ---')] + dept_choices

    def validate(self, extra_validators=None):
        rv = super().validate(extra_validators=extra_validators)
        if not rv:
            return False

        task = ProjectTaskCode.query.filter_by(
            project_code=self.project_number.data.strip(),
            task_code=self.task_code.data.strip(),
            status='Active'
        ).first()

        if not task:
            self.project_number.errors.append("Invalid or inactive Project/Task combination.")
            return False

        return True