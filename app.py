import os
from flask import Flask, render_template, redirect, session, url_for, abort, \
                  flash, request, current_app, send_from_directory, Markup
from flask.ext.script import Manager, Shell
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.migrate import Migrate, MigrateCommand
from werkzeug.security import generate_password_hash, check_password_hash
from flask.ext.login import UserMixin, LoginManager, current_user, \
                            login_required, login_user, logout_user
from flask.ext.wtf import Form
from wtforms import StringField, PasswordField, BooleanField, SubmitField, \
                    TextAreaField
from wtforms.widgets import TextInput
from wtforms.validators import Length, Required, Email, URL, Optional, \
                               ValidationError
from flask.ext.mail import Mail, Message
from threading import Thread
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from random import sample
from datetime import datetime
from hashids import Hashids
import flask.ext.whooshalchemy as whooshalchemy
import sendgrid



# Configuration

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['DEBUG'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'no key set'
app.config['SQLALCHEMY_DATABASE_URI'] = \
                        'sqlite:///' + os.path.join(basedir, 'data.sqlite')
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True

app.config['WHOOSH_BASE'] = os.path.join(basedir, 'search.db')
MAX_SEARCH_RESULTS = 50

manager = Manager(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)

def make_shell_context():
    return dict(app=app, db=db, School=School, Student=Student, 
                Project=Project)
manager.add_command("shell", Shell(make_context=make_shell_context))
manager.add_command('db', MigrateCommand)

login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return Student.query.get(int(user_id))

hashids = Hashids(alphabet='abcdefghijklmnopqrstuvwxyz1234567890')
BLACKLIST = ['complete', 'request', 'search', 'new', 'settings', 'reset', 
             'confirm', 'unconfirmed', 'login', 'signup', 'explore']
POSTS_PER_PAGE = 25

sg = sendgrid.SendGridClient('nikrdc', '2EzHR42TJwuzZrTXS0eZ')



# Models

j_projects = db.Table('j_projects',
        db.Column('project_id', db.Integer, db.ForeignKey('projects.id')),
        db.Column('student_id', db.Integer, db.ForeignKey('students.id')))

r_projects = db.Table('r_projects',
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
    __searchable__ = ['name', 'username', 'description', 'website']

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    username = db.Column(db.String(64))
    email = db.Column(db.String(64), unique=True)
    website = db.Column(db.String(64))
    description = db.Column(db.Text())
    confirmed = db.Column(db.Boolean, default=False)
    time_joined = db.Column(db.DateTime)

    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    projects = db.relationship('Project', backref='student', lazy='dynamic')

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
    __searchable__ = ['name', 'description', 'website']

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    website = db.Column(db.String(64))
    description = db.Column(db.Text())
    time_posted = db.Column(db.DateTime)
    complete = db.Column(db.Boolean, default=False)
    hashid = db.Column(db.String(32))

    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))

    j_students = db.relationship('Student', secondary=j_projects,
                               backref=db.backref('j_projects', lazy='dynamic'),
                               lazy='dynamic')
    r_students = db.relationship('Student', secondary=r_projects,
                               backref=db.backref('r_projects', lazy='dynamic'),
                               lazy='dynamic')

    def __repr__(self):
        return '<Project %r>' % self.name



# Whoosh

whooshalchemy.whoosh_index(app, Student)
whooshalchemy.whoosh_index(app, Project)



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
                       validators=[Required(message='Your name is required.'),
                       Length(1, 64)])
    email = StringField('School Email Address', 
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

    password = PasswordField('Password', validators=[Length(8, message='Your \
                             password must be at least 8 characters long.')])
    submit = SubmitField('Sign up')


class ProjectForm(Form):
    name = StringField('Name', 
                       validators=[Required(message='A name is required.'),
                       Length(1, 64)])
    website = StringField('Website', validators=[URL(), Optional()])
    description = TextAreaField('Description', 
                  validators=[Required(message='A description is required.')])
    submit = SubmitField('Submit')


class StudentForm(Form):
    name = StringField('Name', 
                       validators=[Required(message='Your name is required.'),
                       Length(1, 64)])
    website = StringField('Website', validators=[URL(), Optional()])
    description = TextAreaField('Description')   
    submit = SubmitField('Update profile')


class PasswordForm(Form):
    current_password = PasswordField('Current password', 
        validators=[Required(message='Your current password is required.')])

    def validate_current_password(self, field):
        if not current_user.verify_password(field.data):
            raise ValidationError('Incorrect password')

    new_password = PasswordField('New password', 
            validators=[Required(message='Your new password is required.'),
                        Length(8, message='Your password must be at least 8 \
                        characters long.')])
    submit = SubmitField('Change password')


class DeleteForm(Form):
    password = PasswordField('Password', 
                validators=[Required(message='Your password is required.')])

    def validate_password(self, field):
        if not current_user.verify_password(field.data):
            raise ValidationError('Incorrect password')

    confirm = StringField(""" Type "ebullient" """, 
            validators=[Required(message='The confirmation text is required')])

    def validate_confirm(self, field):
        if field.data.lower() != "ebullient":
            raise ValidationError('Confirmation text entered incorrectly.')

    submit = SubmitField('Delete account')


class DeleteProjectForm(Form):
    confirm = StringField(""" Type "cynosure" """, 
            validators=[Required(message='The confirmation text is required')])

    def validate_confirm(self, field):
        if field.data.lower() != "cynosure":
            raise ValidationError('Confirmation text entered incorrectly.')

    submit = SubmitField('Delete')


class RequestResetForm(Form):
    email = StringField('Email', 
            validators=[Required(message='Your email address is required.'),
                        Length(1, 64), 
                        Email(message='This email address is invalid.')])

    def validate_email(self, field):
        if Student.query.filter_by(email=field.data).first() is None:
            raise ValidationError('This email address is unknown.')

    submit = SubmitField('Submit')


class ResetForm(Form):
    email = StringField('Email', 
            validators=[Required(message='Your email address is required.'),
                        Length(1, 64), 
                        Email(message='This email address is invalid.')])
    new_password = PasswordField('New password', 
            validators=[Required(message='Your new password is required.'),
                        Length(8, message='Your password must be at least 8 \
                        characters long.')])
    submit = SubmitField('Change password')


class SearchForm(Form):
    query = StringField('Query', validators=[Required()])
    submit = SubmitField('Go')



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
    abort(404)

def email_creator(recipient):
    message = sendgrid.Mail()
    message.set_from('dev@elephantsdontexist.com')
    message.set_from_name('The DevAffair Team')
    message.add_to(recipient.email)
    message.add_to_name(recipient.name)
    return message



# Routes

@app.before_request
def before_request():
    if current_user.is_authenticated() and not current_user.confirmed \
    and request.endpoint not in ['unconfirmed', 'reconfirm', 'confirm', 
                                 'logout', 'static']:
        return redirect(url_for('unconfirmed'))


@app.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated():
        search_form = SearchForm()
        if search_form.validate_on_submit():
            return redirect(url_for('search', query=search_form.query.data))
        incoming_requests = []
        for project in Project.query.filter_by(student=current_user, 
                                               complete=False).all():
            for student in project.r_students:
                incoming_requests.append((project, student))
        outgoing_requests = current_user.r_projects.all()
        active_projects = Project.query.filter_by(student=current_user, 
                          complete=False).all() + current_user.j_projects.all()
        explore_projects = Project.query.filter(Project.student!=current_user).\
            filter_by(school=current_user.school, complete=False).\
            order_by(Project.time_posted.desc()).\
            paginate(1, POSTS_PER_PAGE, False)
        if not current_user.description:
            message = Markup("""You haven't added a description yet! 
                             <a href="/settings">Complete your profile.</a>""")
            flash(message)
        return render_template('dashboard.html', 
                               search_form=search_form, 
                               incoming_requests=incoming_requests,
                               outgoing_requests=outgoing_requests,
                               active_projects=active_projects,
                               explore_projects=explore_projects)
    schools = School.query.all()
    return render_template('index.html', schools=schools)


@app.route('/explore/<int:page>', methods=['GET', 'POST'])
@login_required
def explore(page=2):
    search_form = SearchForm()
    if search_form.validate_on_submit():
        return redirect(url_for('search', query=search_form.query.data))
    explore_projects = Project.query.filter(Project.student!=current_user).\
                       filter_by(school=current_user.school, complete=False).\
                       order_by(Project.time_posted.desc()).\
                       paginate(page, POSTS_PER_PAGE, False)
    return render_template('explore.html', 
                           search_form=search_form,
                           explore_projects=explore_projects)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated():
        flash('You have already signed up and logged in!')
        return redirect(url_for('index'))
    form = SignupForm()
    if form.validate_on_submit():
        school = \
        School.query.filter_by(email_domain= \
                               form.email.data.split('@')[1]).first()
        username = form.email.data.split('@')[0]
        if username in BLACKLIST:
            flash('GET OUT OF HERE!')
            return redirect(url_for('index'))
        student = Student(name=form.name.data,
                          username=username,
                          email=form.email.data,
                          time_joined=datetime.now(),
                          password=form.password.data,
                          school=school)
        db.session.add(student)
        db.session.commit()
        login_user(student)
        token = student.generate_confirmation_token()
        message = email_creator(student)
        message.set_subject('DevAffair: confirm your account')
        message.set_text("Dear " + student.name + ", \n\n" + "Welcome to " +
            "DevAffair! To confirm your account please click on the following" +
            " link: \n\n" + url_for('confirm', token=token, _external=True) +
            "\n\nSincerely, \n\nThe DevAffair Team")
        status, msg = sg.send(message)
        flash('A confirmation email has been sent to you by email.')
        return redirect(url_for('index'))
    return render_template('signup.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated():
        flash('You have already logged in!')
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        student = Student.query.filter_by(email=form.email.data).first()
        if student and student.verify_password(form.password.data):
            login_user(student, form.remember_me.data)
            return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid username or password.')
    return render_template('login.html', form=form)


@app.route('/unconfirmed')
@login_required
def unconfirmed():
    if current_user.confirmed:
        flash('You have already confirmed your account!')
        return redirect(url_for('index'))
    return render_template('unconfirmed.html')


@app.route('/confirm')
@login_required
def reconfirm():
    if current_user.confirmed:
        flash('You have already confirmed your account!')
        return redirect(url_for('index'))
    token = current_user.generate_confirmation_token()
    message = email_creator(current_user)
    message.set_subject('DevAffair: confirm your account')
    message.set_message("Dear " + current_user.name + ", \n\n" + "Welcome to " +
        "DevAffair! To confirm your account please click on the following" +
        " link: \n\n" + url_for('confirm', token=token, _external=True) +
        "\n\nSincerely, \n\nThe DevAffair Team")
    status, msg = sg.send(message)
    logout_user()
    flash('A new confirmation email has been sent to you by email.')
    return redirect(url_for('index'))


@app.route('/confirm/<token>')
@login_required
def confirm(token):
    if current_user.confirmed:
        flash('You have already confirmed your account!')
        return redirect(url_for('index'))
    elif current_user.confirm(token):
        flash('Account successfully confirmed.')
        return redirect(url_for('index'))
    flash('The confirmation link is invalid or has expired.')
    return redirect(url_for('unconfirmed'))


@app.route('/reset', methods=['GET', 'POST'])
def request_reset():
    form = RequestResetForm()
    if form.validate_on_submit():
        student = Student.query.filter_by(email=form.email.data).first()
        token = student.generate_reset_token()
        message = email_creator(student)
        message.set_subject('DevAffair: reset your password')
        message.set_text("Dear " + student.name + ", \n\n" + 
            "We're sorry to hear you forgot your password! To reset your " + 
            "password please click on the following link: \n\n" + 
            url_for('reset', token=token, _external=True) + 
            "\n\nSincerely, \n\nThe DevAffair Team")
        status, msg = sg.send(message)
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
            flash('Password successfully updated.')
            return redirect(url_for('login'))
        flash('The password reset link is invalid or has expired.')
    return render_template('reset.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    search_form = SearchForm()
    profile_form = StudentForm(obj=current_user)
    password_form = PasswordForm()
    delete_form = DeleteForm()
    if request.form:
        submit_val = request.form['submit']
        if submit_val == 'Search':
            if search_form.validate_on_submit():
                return redirect(url_for('search', query=search_form.query.data))
            else:
                profile_form.name.data = current_user.name
                profile_form.website.data = current_user.website
                profile_form.description.data = current_user.description
        elif submit_val ==  'Update profile':
            if profile_form.validate_on_submit():
                current_user.name = profile_form.name.data
                current_user.website = profile_form.website.data
                current_user.description = profile_form.description.data
                db.session.commit()
                flash('Profile successfully updated.')
        elif submit_val == 'Change password':
            if password_form.validate_on_submit():
                current_user.password = password_form.new_password.data
                db.session.commit()
                flash('Password successfully updated.')
            profile_form.name.data = current_user.name
            profile_form.website.data = current_user.website
            profile_form.description.data = current_user.description
        elif submit_val == 'Delete account':
            if delete_form.validate_on_submit():
                deadman = finder(current_user.username, 'student', 
                                 current_user.school)
                for project in deadman.projects:
                    db.session.delete(project)
                logout_user()
                db.session.delete(deadman)
                db.session.commit()
                message = email_creator(deadman)
                message.set_subject('DevAffair: account deleted')
                message.set_text("Dear " + deadman.name + ", \n\nYour account" + 
                    " at DevAffair has been deleted!\n\nSincerely, \n\nThe " +
                    "DevAffair Team")
                status, msg = sg.send(message)
                flash('Account successfully deleted.')
                return redirect(url_for('index'))
            else:
                profile_form.name.data = current_user.name
                profile_form.website.data = current_user.website
                profile_form.description.data = current_user.description   
    return render_template('settings.html', 
                           profile_form=profile_form, 
                           password_form=password_form, 
                           delete_form=delete_form,
                           search_form=search_form)            



@app.route('/<shortname_username>', methods=['GET', 'POST'])
def school_student(shortname_username):
    if current_user.is_authenticated():
        search_form = SearchForm()
        if search_form.validate_on_submit():
            return redirect(url_for('search', query=search_form.query.data))
        student =  finder(shortname_username, 'student', current_user.school)
        incomplete_projects = Project.query.filter_by(student=student, 
                                                      complete=False)
        complete_projects = Project.query.filter_by(student=student, 
                                                    complete=True)
        return render_template('student.html', student=student, 
                               search_form=search_form,
                               incomplete_projects=incomplete_projects,
                               complete_projects=complete_projects)
    school = finder(shortname_username, 'school')
    if len(school.projects.all()) < 3:
        projects = school.projects.all()
    else:
        projects = sample(school.projects.filter_by(complete=False).all(), 3)
    return render_template('school.html', school=school, 
                           projects=projects)


@app.route('/<student_username>/<project_hashid>', methods=['GET', 'POST'])
@login_required
def project(student_username, project_hashid):
    student =  finder(student_username, 'student', current_user.school)
    project = finder(hashids.decode(project_hashid), 'project')
    if project.student is student:
        search_form = SearchForm()
        if search_form.validate_on_submit():
            return redirect(url_for('search', query=search_form.query.data))
        return render_template('project.html', project=project,
                               search_form=search_form)
    abort(404)


@app.route('/<student_username>/<project_hashid>/edit', methods=['GET', 'POST'])
@login_required
def edit(student_username, project_hashid):
    student =  finder(student_username, 'student', current_user.school)
    project = finder(hashids.decode(project_hashid), 'project')
    if project.student is student:
        if current_user == student and not project.complete:
            search_form = SearchForm()
            project_form = ProjectForm(obj=project)
            delete_form = DeleteProjectForm()
            if request.form:
                submit_val = request.form['submit']
                if submit_val == 'Search':
                    if search_form.validate_on_submit():
                        return redirect(url_for('search', query=search_form.query.data))
                    else:
                        project_form.name.data = project.name
                        project_form.website.data = project.website
                        project_form.description.data = project.description
                elif submit_val == 'Update':
                    if project_form.validate_on_submit():
                        project.name = project_form.name.data
                        project.website = project_form.website.data
                        project.description = project_form.description.data
                        db.session.commit()
                        flash('Project successfully updated.')
                        return redirect(url_for('project', 
                                                student_username=student_username,
                                                project_hashid=project_hashid))
                elif submit_val == 'Delete':
                    if delete_form.validate_on_submit():
                        db.session.delete(project)
                        db.session.commit()
                        flash('Project successfully deleted.')
                        return redirect(url_for('index'))
                    else:
                        project_form.name.data = project.name
                        project_form.website.data = project.website
                        project_form.description.data = project.description
            return render_template('edit.html', 
                                   project=project,
                                   project_form=project_form, 
                                   search_form=search_form,
                                   delete_form=delete_form)
        return redirect(url_for('project', 
                                student_username=student_username,
                                project_hashid=project_hashid))
    abort(404)


@app.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    search_form = SearchForm()
    if search_form.validate_on_submit():
        return redirect(url_for('search', query=search_form.query.data))
    project_form = ProjectForm()
    if request.form:
        submit_val = request.form['submit']
        if submit_val == 'Search':
            if search_form.validate_on_submit():
                return redirect(url_for('search', query=search_form.query.data))
        elif submit_val == 'Create':
            if project_form.validate_on_submit():
                project = Project(name=project_form.name.data,
                          website=project_form.website.data,
                          description=project_form.description.data,
                          time_posted=datetime.now(),
                          student=current_user,
                          school=current_user.school)
                db.session.add(project)
                db.session.commit()
                Project.query.get(project.id).hashid = \
                hashids.encode(project.id)
                db.session.commit()
                flash('Project successfully created.')
                return redirect(url_for('project', 
                                student_username=current_user.username,
                                project_hashid=project.hashid))
    return render_template('new.html', project_form=project_form, 
                           search_form=search_form)


@app.route('/search/<query>', methods=['GET', 'POST'])
@login_required
def search(query):
    search_form = SearchForm()
    if search_form.validate_on_submit():
        return redirect(url_for('search', query=search_form.query.data))
    student_results = Student.query.whoosh_search(query, MAX_SEARCH_RESULTS).\
                      filter_by(confirmed=True).all()
    project_results = Project.query.whoosh_search(query, MAX_SEARCH_RESULTS).\
                      filter_by(complete=False).all()
    return render_template('search.html', query=query, 
                           student_results=student_results,
                           project_results=project_results,
                           search_form = SearchForm())

@app.route('/search', methods=['GET', 'POST'])
@login_required
def empty_search():
    search_form = SearchForm()
    if search_form.validate_on_submit():
        return redirect(url_for('search', query=search_form.query.data))
    return render_template('search.html', query=None, 
                           student_results=None,
                           project_results=None,
                           search_form = SearchForm())

@app.route('/request/<student_username>/<project_hashid>/<type>', 
           methods=['GET'])
@login_required
def rj_request(student_username, project_hashid, type):
    student = finder(student_username, 'student', current_user.school)
    project = finder(hashids.decode(project_hashid), 'project')
    if type == 'r_append' and \
       current_user == student and \
       project not in student.r_projects and \
       project not in student.j_projects and \
       not project.complete:
        student.r_projects.append(project)
        project_creator = project.student
        message = email_creator(project_creator)
        message.set_subject('DevAffair: new request to join ' + project.name)
        message.set_text("Dear " + project_creator.name + ", \n\n" + 
            student.name + " requested to join your project " + project.name + 
            ". Accept or deny this request on DevAffair: \n\n" + 
            url_for('project', project_hashid=project_hashid, 
                               student_username=project_creator.username,
                               _external=True) + 
            "\n\nSincerely, \n\nThe DevAffair Team")
        status, msg = sg.send(message)
    elif type == 'r_remove' and \
         ((current_user == student) or (current_user == project.student)) and \
         project in student.r_projects and \
         project not in student.j_projects and \
         not project.complete:
        student.r_projects.remove(project)
    elif type == 'j_append' and \
         current_user == project.student and \
         project in student.r_projects and \
         project not in student.j_projects and \
         not project.complete:
        student.r_projects.remove(project)
        student.j_projects.append(project)
        project_creator = project.student
        message = email_creator(student)
        message.set_subject('DevAffair: request to join ' + project.name +
                            ' accepted')
        message.set_text("Dear " + student.name + ", \n\n" + 
            project_creator.name + " accepted your request to join " + 
            project.name + ". Visit the project on DevAffair: \n\n" + 
            url_for('project', project_hashid=project_hashid, 
                               student_username=project_creator.username,
                               _external=True) +
            "\n\nSincerely, \n\nThe DevAffair Team")
        status, msg = sg.send(message)
    elif type == 'j_remove' and \
         ((current_user == student) or (current_user == project.student)) and \
         project in student.j_projects and \
         project not in student.r_projects and \
         not project.complete:
        student.j_projects.remove(project)
    else:
        abort(400)
    db.session.commit()
    return redirect(request.referrer)


@app.route('/complete/<project_hashid>', methods=['GET'])
@login_required
def complete(project_hashid):
    project = finder(hashids.decode(project_hashid), 'project')
    if current_user == project.student and not project.complete:
        project.complete = True
        project.r_students = []
        db.session.commit()
        return redirect(url_for('project', 
                        student_username=current_user.username,
                        project_hashid=project.hashid))
    else:
        abort(404)


if __name__ == '__main__':
    manager.run()


