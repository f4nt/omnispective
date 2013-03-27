import os.path
import textwrap
from datetime import datetime

from fabric import api as fab

fab.env.hosts = ['localhost', 'ubuntu@ec2-instance']
fab.env.key_filename = '/home/f4nt/.ssh/kingdomkeys.pem'
fab.env.roledefs = {
    'localhost': 'localhost',
    'webservers': ['ec2-instance', ]
}

ROOT = os.path.dirname(os.path.abspath(__file__))
REMOTE_ROOT = '/var/www/omnispective/src'
PROJECT_DL_ROOT = 'https://github.com/f4nt/omnispective/archive'


def _make_virtualenv(name, hidden=True):
    prefix = '.' if hidden else ''
    dir_ = os.path.join(ROOT, prefix + name)
    fab.local('virtualenv {0} --prompt="({1})"'.format(dir_, name))
    fab.puts(textwrap.dedent('''
        Activate virtual environment {0} with:
            source {1}/bin/activate
        '''.format(name, dir_)))
    return dir_


def _install(where, requirements, checkouts=()):
    reqs = ' '.join('-r {0}'.format(file_) for file_ in requirements)
    cos = ' '.join('-e {0}'.format(co) for co in checkouts)
    with fab.lcd(ROOT):
        fab.local('pip install -E {where}{reqs}{cos}'.format(
            where=where,
            reqs=(reqs and ' ' + reqs),
            cos=(cos and ' ' + cos),
        ))


def _build_server():
    env_dir = _make_virtualenv('server.env')
    test_requirements = os.path.join('server', 'test.requirements')
    _install(env_dir, [test_requirements], ['server'])


def _build_client():
    env_dir = _make_virtualenv('client.env')
    test_requirements = os.path.join('client', 'python', 'test.requirements')
    checkout = os.path.join('client', 'python')
    _install(env_dir, [test_requirements], [checkout])


def build(what):
    """Build a package for local development.

        build:server
        build:client

    """
    try:
        func = globals()["_build_%s" % what]
    except KeyError:
        pass
    else:
        if callable(func):
            func()
            return

    fab.abort("No such build target {0!r}".format(what))


def test(what=None):
    ''' Run unit tests locally for a given application

        test:history

    '''
    apps = ['history', ]
    if what:
        apps = [what, ]
    with fab.lcd('server/omniserver/'):
        fab.local('python manage.py test %s' % ''.join(apps))


def _deploy_build(build_tag='master'):
    ''' Build '''
    build_dir = os.path.join(REMOTE_ROOT, 'builds')
    repo_url = '%s/%s.zip' % (PROJECT_DL_ROOT, build_tag)
    timestamp = datetime.now().strftime('%Y-%m-%d-%H_%M_%S')
    build_name = 'omnispective-%s' % timestamp
    fab.run('mkdir -p %s' % build_dir)
    with fab.cd(build_dir):
        fab.run('rm -f %s.zip' % build_tag)
        fab.run('wget %s' % repo_url)
        fab.run('unzip %s.zip' % build_tag)
        fab.run('mv omnispective-%s %s' % (
            build_tag, build_name)
        )

    with fab.cd(REMOTE_ROOT):
        with fab.settings(fab.hide('warnings'), warn_only=True):
            fab.run('rm -f previous')
            fab.run('mv -f current previous')
        fab.run('ln -s %s current' % os.path.join(
            REMOTE_ROOT,
            'builds/%s' % build_name
        ))


def _restart_sites():
    ''' Restart the supervisor instances '''
    fab.sudo('supervisorctl restart omniserver')
    fab.sudo('service nginx reload')


@fab.roles('webservers')
@fab.with_settings(user='ubuntu')
def deploy_omni_server(build_tag='master'):
    ''' Deploys omnispective server TO THE CLOUD '''
    with fab.prefix('source %s/../bin/activate' % REMOTE_ROOT):
        with fab.cd(REMOTE_ROOT):
            _deploy_build(build_tag)
            fab.run('pip install -r current/deploy.requirements')
            _restart_sites()
