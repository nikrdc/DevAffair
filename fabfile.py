from fabric.api import *

# the user to use for the remote commands
env.user = 'dev'
# the servers where the commands are executed
env.hosts = ['nikrdc.com']

# def pack():
#     # create a new source distribution as tarball
#     local('tar -cvzf devaffair.tar.gz .')

def dependencies():
    with prefix(". /usr/local/bin/virtualenvwrapper.sh; workon devaffair"):
        run('pip install -r requirements.txt')

def migrate():
    with prefix(". /usr/local/bin/virtualenvwrapper.sh; workon devaffair"):
        run('python app.py db upgrade')

def deploy():
    with cd('~/devaffair'):
        run('git pull origin master')
        dependencies()
        migrate()

    with shell_env(SECRET_KEY='6VJenDI6V0w2nsXB9iSdj4UfOt8f'):
    	run('touch /tmp/reload_devaffair')
