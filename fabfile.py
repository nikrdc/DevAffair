from fabric.api import *

# the user to use for the remote commands
env.user = 'dev'
# the servers where the commands are executed
env.hosts = ['elephantsdontexist.com']

# def pack():
#     # create a new source distribution as tarball
#     local('tar -cvzf devaffair.tar.gz .')

def dependencies():
    run('workon devaffair')
    run('pip install -r requirements.txt')

def migrate():
    run('python app.py db upgrade')

def deploy():
    with cd('~/devaffair'):
        run('git pull origin master')
        dependencies()
        migrate()

    run('touch /tmp/reload_devaffair')
