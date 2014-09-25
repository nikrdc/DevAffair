import os
from flask import Flask, render_template, redirect, session, url_for, abort, \
                  flash, request
from flask.ext.script import Manager, Shell
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.migrate import Migrate, MigrateCommand
from werkzeug.security import generate_password_hash, check_password_hash
from flask.ext.login import UserMixin, LoginManager, current_user, \
                            login_required
from flask.ext.wtf import Form
from wtforms import Field, StringField, PasswordField, BooleanField, \
                    SubmitField
from wtforms.widgets import TextInput
from wtforms.validators import Length, Required, Email, ValidationError, \
                               EqualTo
from flask.ext.mail import Mail, Message
from threading import Thread



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
    email = db.Column(db.String(64), unique=True)
    website = db.Column(db.String(64))
    description = db.Column(db.Text())
    confirmed = db.Column(db.Boolean, default=False)

    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    projects = db.relationship('Project', backref='group', lazy='dynamic')

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


class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    description = db.Column(db.Text())

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
        else:
            return u''

    def process_formatdata(self, valuelist):
        if valuelist:
            self.data = [tag for tag in valuelist[0].split(' ')]
    # edit as needed once site renders on browser



# Forms

class LoginForm(Form):
    email = StringField('Email', 
                validators=[Required(message='An email address is required.'),
                            Length(1, 64), 
                            Email(message='This email address is invalid.')])
    password = PasswordField('Password')
    remember_me = BooleanField('Keep me logged in')
    submit = SubmitField('Log in')


class SignupForm(Form):
    name = StringField('Name', 
                        validators=[Required(message='A name is required.')])
    email = StringField('Email', 
                validators=[Required(message='An email address is required.'),
                            Length(1, 64), 
                            Email(message='This email address is invalid.')])

    def validate_email(self, field):
        if Student.query.filter_by(email=field.data).first():
            raise ValidationError('This email is already in use.')

    password = PasswordField('Password')
    submit = SubmitField('Sign up')


class ProjectForm(Form):
    name = StringField('Name', 
                        validators=[Required(message='A name is required.')])
    description = StringField('Description', 
                validators=[Required(message='A description is required.')])
    tags = TagListField('Tags')
    submit = SubmitField('Create')
    update = SubmitField('Update')


class StudentForm(Form):
    name = StringField('Name', 
                        validators=[Required(message='A name is required.')])
    website = StringField('Website')
    description = StringField('Description')
    tags = TagListField('Tags')
    submit = SubmitField('Update profile')


class PasswordForm(Form):
    current_password = PasswordField('Current password', 
                                     validators=[Required()])
    new_password = PasswordField('New password', validators=[Required(), 
                    EqualTo('new_password2', message='Passwords must match')])
    new_password2 = PasswordField('Confirm new password', 
                                  validators=[Required()])
    submit = SubmitField('Update password')



# Errors

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500



# Helpers

def finder(key, type):
    if type == 'school':
        return School.query.filter_by(shortname=key).first_or_404()
    if type == 'student':
        return Student.query.get(key) or abort(404)
    if type == 'project':
        return Project.query.get(key) or abort(404)
    if type == 'tag':
        return Tag.query.filter_by(name=key).first_or_404()
    else:
        abort(404)


def check_confirmed():
    if not current_user.confirmed:
        return render_template('unconfirmed.html')


def check_school(school):
    check_confirmed()
    if current_user.school is school:
        pass
    else:
        return render_template('incorrect_school.html')



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

@app.route('/')
def index():
    schools = School.query.all()
    return render_template('index.html', schools=schools)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        school = \
        School.query.filter_by(email_domain=form.email.data.split('@')[1])
        if school:
            student = Student(name=form.name.data,
                              email=form.email.data,
                              password=form.password.data,
                              school=school)
            db.session.add(student)
            db.session.commit()
            login_user(student)
            return redirect(url_for('school', 
                                    school_shortname=student.school.shortname))
        else:
            return render_template('signup.html', form=form, found=False)
    else:
        return render_template('signup.html', form=form, found=True)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        student = Student.query.filter_by(email=form.email.data).first()
        if student and student.verify_password(form.password.data):
            login_user(student, form.remember_me.data)
            return redirect(request.args.get('next') or \
                url_for('school', school_shortname=student.school.shortname))
        else:
            flash('Invalid username or password.')
    else:
        return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/settings')
@login_required
def settings():
    check_confirmed()
    profile_form = StudentForm(obj=student)
    password_form = PasswordForm()
    if profile_form.validate_on_submit():
        current_user.name = form.name.data
        current_user.website = form.website.data
        current_user.description = form.description.data
        current_user.tags = [finder(tag, 'tag') for tag in form.tags.data]
        db.session.add(current_user)
        db.session.commit()
        flash('Profile updated successfully.')
    if password_form.validate_on_submit():
        if current_user.verify_password(form.current_password.data):
            current_user.password = form.new_password.data
            db.session.add(current_user)
            db.session.commit()
            flash('Password updated successfully.')
        else:
            flash('Invalid password.')
    return render_template('settings.html', profile_form=profile_form, 
                           password_form=password_form)


@app.route('/tags')
def tags():
    check_confirmed()
    tags = Tag.query.all()
    render_template('tags.html', tags=tags)


@app.route('/<school_shortname>')
def school(school_shortname):
    school = finder(school_shortname, 'school')
    if current_user.is_authenticated():
        check_confirmed()
        if current_user.school is school:
            return render_template('school.html', school=school)
        else:
            return render_template('public_school.html')
    else:
        return render_template('public_school.html')


@app.route('/<school_shortname>/<student_id>')
@login_required
def student(school_shortname, student_id):
    school = finder(school_shortname, 'school')
    student =  finder(student_id, 'student')
    if student.school is school:
        check_school(school)
        return render_template('student.html', student=student)
    else:
        abort(404)


@app.route('/<school_shortname>/<student_id>/<project_id>')
@login_required
def project(school_shortname, student_id, project_id):
    school = finder(school_shortname, 'school')
    student =  finder(student_id, 'student')
    project = finder(project_id, 'project')
    if student.school is school and project.student is student:
        check_school(school)
        return render_template('project.html', project=project)
    else:
        abort(404)


@app.route('/<school_shortname>/<student_id>/<project_id>/edit', 
           methods=['GET', 'POST'])
@login_required
def edit(school_shortname, student_id, project_id):
    school = finder(school_shortname, 'school')
    student =  finder(student_id, 'student')
    project = finder(project_id, 'project')
    if student.school is school and project.student is student:
        check_school(school)
        if current_user == student:
            form = ProjectForm(obj=project)
            if form.validate_on_submit():
                project.name = form.name.data
                project.description = form.description.data
                project.tags = [finder(tag, 'tag') for tag in form.tags.data]
                db.session.add(project)
                db.session.commit()
                flash('Project updated successfully.')
            return render_template('edit.html', form=form)
        else: redirect(url_for('project', project_id=project.id))
    else:
        abort(404)


@app.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    check_confirmed()
    form = ProjectForm()
    if form.validate_on_submit():
        project = Project(name=form.name.data,
                          description=form.description.data,
                          student=current_user,
                          school=current_user.school)
                          #tags=[finder(tag, 'tag') for tag in form.tags.data])
        db.session.add(project)
        db.session.commit()
        return redirect(url_for('project', project_id=project.id))
    else:
        return render_template('new.html', form=form)



if __name__ == '__main__':
    manager.run()


