import os
from flask import Flask, render_template, redirect, session, url_for, abort, \
                  flash, request, current_app, send_from_directory
from flask.ext.script import Manager, Shell
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.migrate import Migrate, MigrateCommand
from werkzeug.security import generate_password_hash, check_password_hash
from flask.ext.login import UserMixin, LoginManager, current_user, \
                            login_required, login_user, logout_user
from flask.ext.wtf import Form
from wtforms import Field, StringField, PasswordField, BooleanField, \
                    SubmitField
from wtforms.widgets import TextInput
from wtforms.validators import Length, Required, Email, ValidationError
from flask.ext.mail import Mail, Message
from threading import Thread
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from random import sample



# Configuration

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['DEBUG'] = True
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'substitute key'
app.config['SQLALCHEMY_DATABASE_URI'] = \
                        'sqlite:///' + os.path.join(basedir, 'data.sqlite')
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

manager = Manager(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)

def make_shell_context():
    return dict(app=app, db=db, School=School, Student=Student, 
                Project=Project, Tag=Tag)
manager.add_command("shell", Shell(make_context=make_shell_context))
manager.add_command('db', MigrateCommand)

login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return Student.query.get(int(user_id))



# Models

taggers = db.Table('taggers',
        db.Column('tag_id', db.Integer, db.ForeignKey('tags.id')),
        db.Column('project_id', db.Integer, db.ForeignKey('projects.id')),
        db.Column('student_id', db.Integer, db.ForeignKey('students.id')))

j_students = db.Table('j_students',
        db.Column('student_id', db.Integer, db.ForeignKey('students.id')),
        db.Column('project_id', db.Integer, db.ForeignKey('projects.id')))


class School(db.Model):
    __tablename__ = 'schools'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    shortname = db.Column(db.String(64), unique=True)
    email_domain = db.Column(db.String(64), unique=True)

    students = db.relationship('Student', backref='school', lazy='dynamic')
    projects = db.relationship('Project', backref='school', lazy='dynamic')

    def __repr__(self):
        return '<School %r>' % self.name
        

class Student(UserMixin, db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    username = db.Column(db.String(64))
    email = db.Column(db.String(64), unique=True)
    website = db.Column(db.String(64))
    description = db.Column(db.Text())
    confirmed = db.Column(db.Boolean, default=False)

    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    projects = db.relationship('Project', backref='student', lazy='dynamic')

    j_projects = db.relationship('Project', secondary=j_students,
                            backref=db.backref('j_students', lazy='dynamic'),
                            lazy='dynamic')

    password_hash = db.Column(db.String(128))

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return '<Student %r>' % self.name

    def generate_confirmation_token(self, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'confirm': self.id})

    def confirm(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except:
            return False
        if data.get('confirm') != self.id:
            return False
        self.confirmed = True
        db.session.add(self)
        return True

    def generate_reset_token(self, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'reset': self.id})

    def reset_password(self, token, new_password):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except:
            return False
        if data.get('reset') != self.id:
            return False
        self.password = new_password
        db.session.add(self)
        return True


class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    description = db.Column(db.Text())
    time_posted = db.Column(db.DateTime)
    complete = db.Column(db.Boolean, default=False)

    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))

    def __repr__(self):
        return '<Project %r>' % self.name


class Tag(db.Model):
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    description = db.Column(db.Text())

    projects = db.relationship('Project', secondary=taggers,
                               backref=db.backref('tags', lazy='dynamic'),
                               lazy='dynamic')
    students = db.relationship('Student', secondary=taggers,
                               backref=db.backref('tags', lazy='dynamic'),
                               lazy='dynamic')

    def __repr__(self):
        return '<Tag %r>' % self.name



# Fields

class TagListField(Field):
    widget = TextInput()

    def _value(self):
        if self.data:
            return u' '.join(self.data)
        return u''

    def process_formatdata(self, valuelist):
        if valuelist:
            self.data = [tag for tag in valuelist[0].split(' ')]
    # edit as needed once site renders on browser



# Forms

class LoginForm(Form):
    email = StringField('Email', 
            validators=[Required(message='Your email address is required.'),
                        Length(1, 64), 
                        Email(message='This email address is invalid.')])
    password = PasswordField('Password')
    remember_me = BooleanField('Keep me logged in') 
    submit = SubmitField('Log in')


class SignupForm(Form):
    name = StringField('Name', 
                    validators=[Required(message='Your name is required.')])
    email = StringField('Email', 
            validators=[Required(message='Your email address is required.'),
                        Length(1, 64), 
                        Email(message='This email address is invalid.')])

    def validate_email(self, field):
        if Student.query.filter_by(email=field.data).first():
            raise ValidationError('This email address is already in use.')
        elif len(field.data.split('@')) == 2 and \
not School.query.filter_by(email_domain=field.data.split('@')[1]).first() \
        and 'This email address is invalid.' not in field.errors:
            raise ValidationError("Sorry! We don't support this school yet.")            

    password = PasswordField('Password')
    submit = SubmitField('Sign up')


class ProjectForm(Form):
    name = StringField('Name', 
                        validators=[Required(message='A name is required.')])
    description = StringField('Description', 
                validators=[Required(message='A description is required.')])
    tags = TagListField('Tags')
    create = SubmitField('Create')
    update = SubmitField('Update')


class StudentForm(Form):
    name = StringField('Name', 
                    validators=[Required(message='Your name is required.')])
    website = StringField('Website')
    description = StringField('Description')
    tags = TagListField('Tags')
    submit = SubmitField('Update profile')


class PasswordForm(Form):
    current_password = PasswordField('Current password', 
        validators=[Required(message='Your current password is required.')])

    def validate_current_password(self, field):
        if not current_user.verify_password(field.data):
            raise ValidationError('Incorrect password')

    new_password = PasswordField('New password', 
            validators=[Required(message='Your new password is required.')])
    submit = SubmitField('Update password')


class DeleteForm(Form):
    password = PasswordField('Password', 
                validators=[Required(message='Your password is required.')])

    def validate_password(self, field):
        if not current_user.verify_password(field.data):
            raise ValidationError('Incorrect password')

    submit = SubmitField('Delete account')


class RequestResetForm(Form):
    email = StringField('Email', 
            validators=[Required(message='Your email address is required.'),
                        Length(1, 64), 
                        Email(message='This email address is invalid.')])

    def validate_email(self, field):
        if Student.query.filter_by(email=field.data).first() is None:
            raise ValidationError('This email address is unknown.')

    submit = SubmitField('Submit request')


class ResetForm(Form):
    email = StringField('Email', 
            validators=[Required(message='Your email address is required.'),
                        Length(1, 64), 
                        Email(message='This email address is invalid.')])
    new_password = PasswordField('New password', 
            validators=[Required(message='Your new password is required.')])
    submit = SubmitField('Reset password')



# Errors

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500



# Helpers

def finder(key, type, key2=None):
    if type == 'school':
        return School.query.filter_by(shortname=key).first_or_404()
    if type == 'student':
        return Student.query.filter_by(username=key, school=key2).first() or \
               abort(404)
    if type == 'project':
        return Project.query.get(key) or abort(404)
    if type == 'tag':
        return Tag.query.filter_by(name=key).first_or_404()
    abort(404)



# Email

def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)


def send_email(to, subject, template, **kwargs):
    msg = Message('DevAffair: ' + subject, sender = 'DevAffair', 
                  recipients = [to])
    msg.body = render_template(template + '.txt', **kwargs)
    msg.html = render_template(template + '.html', **kwargs)
    thr = Thread(target = send_async_email, args = [app, msg])
    thr.start()
    return thr



# Routes

@app.before_request
def before_request():
    if current_user.is_authenticated() and not current_user.confirmed \
    and request.endpoint not in ['unconfirmed', 'reconfirm', 'confirm', 
                                 'logout', 'static']:
        return redirect(url_for('unconfirmed'))


@app.route('/')
def index():
    schools = School.query.all()
    return render_template('index.html', schools=schools)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated():
        flash('You have already signed up and logged in!')
        return redirect(url_for('school', 
                                school_shortname=current_user.school.shortname))
    form = SignupForm()
    if form.validate_on_submit():
        school = \
        School.query.filter_by(email_domain= \
                               form.email.data.split('@')[1]).first()
        student = Student(name=form.name.data,
                          username=form.email.data.split('@')[0],
                          email=form.email.data,
                          password=form.password.data,
                          school=school)
        db.session.add(student)
        db.session.commit()
        login_user(student)
        token = student.generate_confirmation_token()
        '''
        send_email(student.email, 'Confirm your account', 'mail/confirm', 
                   student=student, token=token)
        '''
        flash('A confirmation email has been sent to you by email.')
        return redirect(url_for('school', 
                                school_shortname=student.school.shortname))
    return render_template('signup.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated():
        flash('You have already logged in!')
        return redirect(url_for('school', 
                                school_shortname=current_user.school.shortname))
    form = LoginForm()
    if form.validate_on_submit():
        student = Student.query.filter_by(email=form.email.data).first()
        if student and student.verify_password(form.password.data):
            login_user(student, form.remember_me.data)
            return redirect(request.args.get('next') or \
                url_for('school', school_shortname=student.school.shortname))
        flash('Invalid username or password.')
    return render_template('login.html', form=form)


@app.route('/unconfirmed')
def unconfirmed():
    if current_user.confirmed:
        flash('You have already confirmed your account!')
        return redirect(url_for('school', 
                                school_shortname=current_user.school.shortname))
    return render_template('unconfirmed.html')


@app.route('/confirm')
@login_required
def reconfirm():
    if current_user.confirmed:
        flash('You have already confirmed your account!')
        return redirect(url_for('school', 
                                school_shortname=current_user.school.shortname))
    token = current_user.generate_confirmation_token()
    send_email(student.email, 'Confirm your account', 'mail/confirm', 
               student=student, token=token)
    flash('A new confirmation email has been sent to you by email.')
    return redirect(url_for('index'))


@app.route('/confirm/<token>')
@login_required
def confirm(token):
    if current_user.confirmed:
        flash('You have already confirmed your account!')
        return redirect(url_for('school', 
                                school_shortname=current_user.school.shortname))
    elif current_user.confirm(token):
        flash('Account confirmed successfully')
        return redirect(url_for('school', 
                                school_shortname=student.school.shortname))
    flash('The confirmation link is invalid or has expired.')
    return redirect(url_for('unconfirmed'))


@app.route('/reset', methods=['GET', 'POST'])
def request_reset():
    form = RequestResetForm()
    if form.validate_on_submit():
        student = Student.query.filter_by(email=form.email.data).first()
        token = student.generate_reset_token()
        send_email(student.email, 'Reset your password', 'mail/reset',
                   student=student, token=token, next=request.args.get('next'))
        flash('An email with instructions to reset your password has been \
              sent to you.')
        return redirect(url_for('index'))
    return render_template('request_reset.html', form=form)


@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset(token):
    form = ResetForm()
    if form.validate_on_submit():
        student = Student.query.filter_by(email=form.email.data).first()
        if student.reset_password(token, form.new_password.data):
            flash('Password updated successfully')
            return redirect(url_for('login'))
        flash('The password reset link is invalid or has expired.')
    return render_template('reset.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/settings')
@login_required
def settings():
    profile_form = StudentForm(obj=student)
    password_form = PasswordForm()
    delete_form = DeleteForm()
    if profile_form.validate_on_submit():
        current_user.name = profile_form.name.data
        current_user.website = profile_form.website.data
        current_user.description = profile_form.description.data
        current_user.tags = \
                        [finder(tag, 'tag') for tag in profile_form.tags.data]
        db.session.add(current_user)
        db.session.commit()
        flash('Profile updated successfully')
    if password_form.validate_on_submit():
        current_user.password = password_form.new_password.data
        db.session.add(current_user)
        db.session.commit()
        flash('Password updated successfully')
    if delete_form.validate_on_submit():
        deadman = current_user
        logout_user()
        db.session.delete(deadman)
        db.session.commit()
        send_email(deadman.email, 'Account deleted', 'mail/deleted', 
                   student=deadman)
        flash('Account deleted successfully')
        return redirect(url_for('index'))
    return render_template('settings.html', profile_form=profile_form, 
                           password_form=password_form, 
                           delete_form=delete_form)


@app.route('/tags')
def tags():
    tags = Tag.query.all()
    render_template('tags.html', tags=tags)


@app.route('/<school_shortname>')
def school(school_shortname):
    school = finder(school_shortname, 'school')
    if current_user.is_authenticated() and current_user.school is school:
        return render_template('school.html', school=school)
    #projects = sample(school.projects.filter_by(complete=False).all(), 5)
    projects = school.projects.filter_by(complete=False).all()
    return render_template('public_school.html', school=school, 
                           projects=projects)


@app.route('/<school_shortname>/<student_username>')
@login_required
def student(school_shortname, student_username):
    school = finder(school_shortname, 'school')
    if current_user.school is not school:
        return render_template('incorrect_school.html')
    student =  finder(student_username, 'student', school)
    if student.school is school:
        return render_template('student.html', student=student)
    abort(404)


@app.route('/<school_shortname>/<student_username>/<project_id>')
@login_required
def project(school_shortname, student_username, project_id):
    school = finder(school_shortname, 'school')
    if current_user.school is not school:
        return render_template('incorrect_school.html')
    student =  finder(student_username, 'student', school)
    project = finder(project_id, 'project')
    if student.school is school and project.student is student:
        return render_template('project.html', project=project)
    abort(404)


@app.route('/<school_shortname>/<student_username>/<project_id>/edit', 
           methods=['GET', 'POST'])
@login_required
def edit(school_shortname, student_username, project_id):
    school = finder(school_shortname, 'school')
    if current_user.school is not school:
        return render_template('incorrect_school.html')
    student =  finder(student_username, 'student', school)
    project = finder(project_id, 'project')
    if student.school is school and project.student is student:
        if current_user == student:
            form = ProjectForm(obj=project)
            if form.validate_on_submit():
                project.name = form.name.data
                project.description = form.description.data
                project.tags = [finder(tag, 'tag') for tag in form.tags.data]
                db.session.add(project)
                db.session.commit()
                flash('Project updated successfully')
            return render_template('edit.html', form=form)
        return redirect(url_for('project', project_id=project.id))
    abort(404)


@app.route('/<school_shortname>/<student_username>/<project_id>/delete', 
           methods=['POST'])
@login_required
def delete(school_shortname, student_id, project_id):
    check_school(school)
    school = finder(school_shortname, 'school')
    student =  finder(student_id, 'student')
    project = finder(project_id, 'project')
    if student.school is school and project.student is student:
        if current_user == student:
            db.session.delete(project)
            db.session.commit()
            flash('Project deleted successfully')
            return redirect(url_for('school', 
                                    school_shortname=student.school.shortname))
        return redirect(url_for('project', project_id=project.id))
    abort(404)


@app.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    form = ProjectForm()
    if form.validate_on_submit():
        project = Project(name=form.name.data,
                          description=form.description.data,
                          time_posted=datetime.now(),
                          student=current_user,
                          school=current_user.school,
                          tags=[finder(tag, 'tag') for tag in form.tags.data])
        db.session.add(project)
        db.session.commit()
        return redirect(url_for('project', project_id=project.id))
    return render_template('new.html', form=form)



if __name__ == '__main__':
    manager.run()


