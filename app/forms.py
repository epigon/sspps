from app.models import Committee, Department, Employee, Instrument, Permission, ProjectTaskCode, Role, User
from flask_wtf import FlaskForm
from markupsafe import Markup, escape
from wtforms import widgets, BooleanField, DateField, DateTimeLocalField, FileField, HiddenField, IntegerField, RadioField,\
    SelectField, SelectMultipleField, StringField, SubmitField, TelField, TextAreaField, TimeField, ValidationError
from wtforms.validators import DataRequired, Email, InputRequired, Length, Optional, ValidationError
from wtforms.widgets import CheckboxInput, ListWidget

MONTHS = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'),
    ('4', 'April'), ('5', 'May'), ('6', 'June'),
    ('7', 'July'), ('8', 'August'), ('9', 'September'),
    ('10', 'October'), ('11', 'November'), ('12', 'December')
]

class CSRFOnlyForm(FlaskForm):
    pass

class DataAttributeSelectField(SelectField):
    """
    Custom SelectField that supports data-* attributes in choices.
    Each choice should be (value, label, data_attr_dict)
    Example: ("P123", "Project 123", {"data-email": "pi@example.com"})
    """
    def __init__(self, *args, data_key_map=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_key_map = data_key_map or {}

    def __call__(self, **kwargs):
        html = [f'<select name="{escape(self.name)}" id="{escape(self.id)}"']
        for k, v in kwargs.items():
            html.append(f' {escape(k)}="{escape(v)}"')
        html.append('>')

        for value, label, attrs in self.choices:
            selected = " selected" if str(self.data) == str(value) else ""
            extra_attrs = "".join(
                f' {escape(k)}="{escape(v)}"' for k, v in (attrs or {}).items()
            )
            html.append(
                f'<option value="{escape(value)}"{selected}{extra_attrs}>{escape(label)}</option>'
            )

        html.append('</select>')
        return Markup("".join(html))

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

class CommitteeForm(FlaskForm):
    name = StringField('Name', validators=[InputRequired(), Length(max=100)], render_kw={'autofocus': True})
    short_name = StringField('Short Name', validators=[Length(max=50)])
    description = TextAreaField('Description', validators=[Length(max=255)])
    reporting_start = SelectField('Reporting Start', choices=MONTHS, validators=[DataRequired()])
    mission = TextAreaField('Mission Statement', validators=[Length(max=4000)])
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
    id = HiddenField('AYCommittee ID')
    committee_id = SelectField('Committee', validators=[InputRequired()], choices=[])
    academic_year_id = SelectField('Academic Year', validators=[InputRequired()], choices=[])
    meeting_frequency_type_id = SelectField('Meeting Frequency', choices=[], validators=[DataRequired()])
    meeting_duration_in_minutes = IntegerField('Meeting duration per frequency (in minutes)', default=0)
    supplemental_minutes_per_frequency = IntegerField('Outside meeting workload per frequency (in minutes)', default=0)
    copy_from_id = SelectField("Copy from Previous Academic Years", coerce=int, choices=[(0, "-- Select --")], default=0)

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
    allow_edit = BooleanField('Committee Editor', default=False)
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
    location = StringField('Location', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])

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
    machine = SelectField("Instrument", validators=[DataRequired()])
    department_code = SelectField('Department', validators=[DataRequired()])
    pi_name = DataAttributeSelectField("PI Name", validators=[DataRequired()])
    pi_email = StringField("PI Email", validators=[DataRequired(), Email()])
    pi_phone = TelField("PI Phone")
    project_task_code = DataAttributeSelectField("Project-Task Code", validators=[DataRequired()])
    funding_source = DataAttributeSelectField("Funding Source", validators=[DataRequired()])
    requestor_name = StringField("Requestor Name", validators=[DataRequired()])
    requestor_position = StringField("Requestor Position", validators=[DataRequired()])
    requestor_email = StringField("Requestor Email", validators=[DataRequired(), Email()])
    requestor_phone = TelField("Requestor Phone")
    had_training = RadioField(
        "Have you taken the mandatory training?",
        choices=[("yes", "Yes"), ("no", "No")],
        validators=[DataRequired()]
    )
    submit = SubmitField("Submit Request")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.machine.choices = [
            (0, '--- Select Instrument ---') 
        ] + [
            (m.machine_name, m.machine_name)
            for m in Instrument.query.filter_by(flag=True)
                .order_by(Instrument.machine_name)
                .all()
        ]
        # Populate Department choices: value=department.code, label=department.name
        departments = Department.query.order_by(Department.name).all()
        dept_choices = [(d.code, d.code +" - "+ d.name) for d in departments]
        self.department_code.choices = [('', '--- Select a Department ---')] + dept_choices

        # PI Names
        rows = ProjectTaskCode.query.with_entities(
            ProjectTaskCode.pi_email, ProjectTaskCode.pi_name, ProjectTaskCode.project_task_code, ProjectTaskCode.funding_source_code, 
            ProjectTaskCode.funding_source
        ).distinct().all()

        # Step 2: build distinct sets
        # Distinct PI choices
        pi_set = {(r.pi_email, r.pi_name) for r in rows}
        # Distinct project/task codes
        project_set = {(r.project_task_code, r.pi_email) for r in rows}
        # Distinct funding sources
        funding_set = {(r.funding_source_code, r.funding_source, r.project_task_code) for r in rows}

        # Step 3: sort each list
        pi_choices_sorted = sorted(pi_set, key=lambda x: x[1])  # sort by PI name
        project_choices_sorted = sorted(project_set, key=lambda x: x[0])  # sort by code
        funding_choices_sorted = sorted(funding_set, key=lambda x: x[1])  # sort by funding source name

        # Step 4: assign to form
        self.pi_name.choices = [('', '--- Select a PI ---', {})] + [
            (name, name, {"data-email": email}) for email, name in pi_choices_sorted
        ]

        self.project_task_code.choices = [('', '--- Select Project/Task Code ---', {})] + [
            (code, code, {"data-email": email}) for code, email in project_choices_sorted
        ]

        self.funding_source.choices = [('', '--- Select Funding Source ---', {})] + [
            (fs_code, fs_name, {"data-project-task": project_task_code})
            for fs_code, fs_name, project_task_code in funding_choices_sorted
        ]

    def validate(self, extra_validators=None):
        rv = super().validate(extra_validators=extra_validators)
        if not rv:
            return False
        return True