from flask_wtf import FlaskForm
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms import widgets, SelectMultipleField, StringField, PasswordField, BooleanField, SelectField, HiddenField, TextAreaField, DateField, TimeField, SubmitField, FileField
from wtforms.validators import InputRequired, Email, Length, DataRequired, ValidationError, Optional
from app.models import User, Employee, Role, Permission, Committee

MONTHS = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'),
    ('4', 'April'), ('5', 'May'), ('6', 'June'),
    ('7', 'July'), ('8', 'August'), ('9', 'September'),
    ('10', 'October'), ('11', 'November'), ('12', 'December')
]

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
    # active = BooleanField('Default')

class FrequencyTypeForm(FlaskForm):
    type = StringField('Frequency', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})
    # active = BooleanField('Default')

class MemberTypeForm(FlaskForm):
    type = StringField('Member Type', validators=[InputRequired(), Length(max=50)], render_kw={'autofocus': True})
    # active = BooleanField('Default')

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
    
    # logo = FileField('Logo', render_kw={'accept': "image/*"})

class CommitteeReportForm(FlaskForm):
    # academic_year = SelectField('Academic Year', validators=[DataRequired()], coerce=int, render_kw={'multiple': True})
    academic_year = SelectField('Academic Year', 
                            validators=[DataRequired()], 
                            coerce=int, 
                            choices=[], 
                            # render_kw={'multiple': True}
                            )  # Allow multiple selections
    committee = SelectField('Committee', 
                            validators=[DataRequired()], 
                            coerce=int, 
                            choices=[]
                            )  
    users = SelectField('Employee', 
                            validators=[DataRequired()], 
                            coerce=int, 
                            choices=[]
                            ) 
    committee_type = SelectField('Committee Type', 
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

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.academic_year.choices = [(ay.id, ay.name) for ay in AcademicYear.query.order_by(AcademicYear.name.desc()).all()]

class MemberForm(FlaskForm):
    ay_committee_id = HiddenField('AYCommittee', validators=[DataRequired()])
    employee_id = SelectField('Select Member', choices=[], validators=[DataRequired()])
    member_role_id = SelectField('Select Role', choices=[], validators=[DataRequired()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])    
    voting = BooleanField('Voting Member')
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