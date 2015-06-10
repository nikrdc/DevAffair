from fabric.api import *

# the user to use for the remote commands
env.user = 'dev'
# the servers where the commands are executed
env.hosts = ['elephantsdontexist.com']

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
    	with shell_env(MAIL_USERNAME='dev@elephantsdontexist.com', MAIL_PASSWORD='hermione'):
	        run('git pull origin master')
	        dependencies()
	        migrate()

    run('touch /tmp/reload_devaffair')
