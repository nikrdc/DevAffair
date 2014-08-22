import os
from flask import Flask, render_template, redirect, session, url_for, abort, \
                  flash, g
from flask.ext.script import Manager, Shell
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.migrate import Migrate, MigrateCommand
from werkzeug.security import generate_password_hash, check_password_hash
from flask.ext.login import UserMixin, LoginManager



# Configuration

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['DEBUG'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = \
    'sqlite:///' + os.path.join(basedir, 'data.sqlite')
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True

manager = Manager(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)

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
        db.Column('developer_id', db.Integer, db.ForeignKey('users.id')))


class School(db.Model):
    __tablename__ = 'schools'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    shortname = db.Column(db.String(64), unique=True)

    students = db.relationship('User', backref='school', lazy='dynamic')
    projects = db.relationship('Project', backref='school', lazy='dynamic')

    def __repr__(self):
        return '<School %r>' % self.name


class Student(UserMixin, db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64))
    shortname = db.Column(db.String(64), unique=True)
    email = db.Column(db.String(64), unique=True)
    website = db.Column(db.String(64))
    description = db.Column(db.Text())

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
        return '<User %r>' % self.name


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

    projects = db.relationship('Project', secondary=taggers,
                               backref=db.backref('tags', lazy='dynamic'),
                               lazy='dynamic')
    students = db.relationship('Student', secondary=taggers,
                               backref=db.backref('tags', lazy='dynamic'),
                               lazy='dynamic')

    def __repr__(self):
        return '<Tag %r>' % self.name



# Errors

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500



# Routes

@app.route('/', methods=['GET'])
def index():
    schools = School.query.all()
    return render_template('index.html', schools=schools)



if __name__ == '__main__':
    manager.run()


