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
    
#----------------------
# COMMITTEE TRACKER APP
#----------------------
class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

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
    meeting_duration_in_minutes = IntegerField('Meeting duration per frequency (in minutes)', validators=[Optional()])
    supplemental_minutes_per_frequency = IntegerField('Outside meeting workload per frequency (in minutes)', validators=[Optional()])
    chair_term_in_years = IntegerField('Chair term (in years)', validators=[Optional()])
    ex_officio_term_in_years = IntegerField('Ex-officio term (in years)', validators=[Optional()])
    member_term_in_years = IntegerField('Member term (in years)', validators=[Optional()])
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
    roles = SelectMultipleField('Member Role', 
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

#----------------------
# EXCHANGE CALENDAR APP
#----------------------
class CalendarGroupForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    ics_filename = StringField('ICS Filename', validators=[DataRequired()])
    submit = SubmitField('Save')

#----------------------
# STUDENT DB APP
#----------------------
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

#----------------------
# RECHARGE APP
#----------------------
class InstrumentRequestForm(FlaskForm):
    machine = SelectField("Instrument", validators=[DataRequired()])
    department_code = SelectField('Department', validators=[DataRequired()])
    pi_name = DataAttributeSelectField("PI Name", validators=[DataRequired()])
    pi_email = StringField("PI Email", validators=[DataRequired(), Email()])
    pi_phone = TelField("PI Phone", validators=[Optional()])
    requestor_name = StringField("Requestor Name", validators=[DataRequired()])
    requestor_email = StringField("Requestor Email", validators=[DataRequired(), Email()])

    submit = SubmitField("Submit Request")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.machine.choices = [
            ('', '--- Select Instrument ---') 
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

        # Step 3: sort each list
        pi_choices_sorted = sorted(pi_set, key=lambda x: x[1])  # sort by PI name

        # Step 4: assign to form
        self.pi_name.choices = [('', '--- Select a PI ---', {})] + [
            (name, name, {"data-email": email}) for email, name in pi_choices_sorted
        ]


    def validate(self, extra_validators=None):
        rv = super().validate(extra_validators=extra_validators)
        if not rv:
            return False
        return True
    
    
#----------------------
# DIRECTORY APP
#----------------------
CONTACT_TYPES = [
    ("", "-- Select One --"),
    ("Staff", "Staff"),
    ("Student", "Student"),
    ("Postdoctoral Scholar", "Postdoctoral Scholar"),
    ("Volunteer", "Volunteer"),
    ("GSR", "GSR"),
    ("Other", "Other")
]

class CategoryForm(FlaskForm):
    name = StringField("Category Name", validators=[DataRequired()],
        filters=[lambda x: x.strip() if x else x])
    building_room = StringField("Building / Room", validators=[Optional()],
        filters=[lambda x: x.strip() if x else x])
    office_phone = StringField("Office Phone", validators=[Optional()],
        filters=[lambda x: x.strip() if x else x])
    lab_phone = StringField("Lab Phone", validators=[Optional()],
        filters=[lambda x: x.strip() if x else x])
    is_lab = BooleanField("Is Lab?")
    show_in_directory = BooleanField("Show in Directory?")
    type = HiddenField("Type", validators=[DataRequired()])
    display_fields = SelectMultipleField(
        "Display Fields in Directory",
        choices=[
            ("first_name", "First Name"),
            ("last_name", "Last Name"),
            ("group_name", "Group Name"),
            ("email", "UCSD Email"),
            ("personal_email", "Personal Email"),
            ("job_title", "Job Title"),
            ("building_room", "Location"),
            ("mail_code", "Mail Code"),
            ("phone_number", "Phone Number")
        ],
        coerce=str,
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False),
    )


class ContactForm(FlaskForm):

    category_id = SelectField(
        "Category",
        coerce=int,
        validators=[DataRequired()]
    )
        
    group_name = StringField("Group Name")
    first_name = StringField("First Name")
    last_name = StringField("Last Name")
    middle_name = StringField("Middle Name")

    job_title = StringField("Job Title")
    email = StringField("UCSD Email", validators=[Optional(), Email()])
    building_room = StringField("Office Location")
    mail_code = StringField("Mail Code")
    phone_number = StringField("Phone Number")

    contact_type = SelectField("Contact Type", choices=CONTACT_TYPES)
   
    other_type = StringField("Other Type", validators=[Optional()])

    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])  

    personal_email = StringField("Personal Email", validators=[Optional(), Email()])
    pid = StringField("PID", description="If UCSD student volunteer, provide PID#")
    employee_id = StringField("Employee ID", description="If volunteer is a current UCSD employee, provide employee ID#")
    dob = DateField("Date of Birth", format='%Y-%m-%d', validators=[Optional()])
    
    other_info = StringField("Other Info", description="If Past UC Employment/Affiliation/Volunteer, provide email address, PID#, or Single SignOn")

    is_employee = BooleanField("Is UCSD Employee?")
    is_student = BooleanField("Is UCSD Student?")
    is_x_affiliate = BooleanField("Is Past UCSD Employee/Affiliate/Volunteer?")

    emailDSA = BooleanField("Email DSA?")
    emailHR = BooleanField("Email HR?")
    emailComms = BooleanField("Email Communications?")

    type = HiddenField("Type", validators=[DataRequired()])

    def validate(self, extra_validators=None):
        rv = super().validate(extra_validators)
        if not rv:
            return False

        first = self.first_name.data.strip() if self.first_name.data else ""
        last = self.last_name.data.strip() if self.last_name.data else ""
        group = self.group_name.data.strip() if self.group_name.data else ""

        if not ((first and last) or group):
            msg = "Please provide either First Name and Last Name, or a Group Name."
            self.first_name.errors.append(msg)
            self.last_name.errors.append(msg)
            self.group_name.errors.append(msg)
            return False

        return True
