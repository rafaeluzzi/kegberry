# Copyright (C) 2014 Bevbot LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Kegberry tool: Kegbot installer for Raspberry Pi."""

from contextlib import closing
import getpass
import gflags
import logging
import os
import pkg_resources
import pwd
import random
import subprocess
import sys
import tempfile

from kegberry import templates

FLAGS = gflags.FLAGS

DEFAULT_USER = 'kegberry' if os.path.exists('/home/kegberry') else 'kegbot'

gflags.DEFINE_string('kegbot_user', DEFAULT_USER,
    'The user account which will be used for kegberry files.')

gflags.DEFINE_string('kegbot_home', os.path.join('/home', DEFAULT_USER),
    'Path to the data directory for Kegberry.')

gflags.DEFINE_boolean('pycore', True,
    'Whether to install pycore along with server.')

gflags.DEFINE_boolean('verbose', False,
    'Log extra stuff.')

gflags.DEFINE_string('mysql_database', 'kegbot',
    'Database for the MySQL server.')

gflags.DEFINE_string('mysql_user', 'root',
    'User for the MySQL server.')

gflags.DEFINE_string('mysql_password', '',
    'Password for the MySQL user, if any.')

gflags.DEFINE_boolean('upgrade_system_packages', False,
    'If set, performs "apt-get upgrade" during install/upgrade.')

gflags.DEFINE_string('kegbot_server_package', 'kegbot==1.2.3',
    '(Advanced use only.) Version of Kegbot Server to install.')

gflags.DEFINE_string('kegbot_pycore_package', 'kegbot-pycore==1.2.0',
    '(Advanced use only.) Version of Kegbot Pycore to install.')

gflags.DEFINE_boolean('fake', False,
    '(Advanced use only.) If true, external commands are not run.')

gflags.DEFINE_boolean('allow_root', False,
    '(Advanced use only.) DANGEROUS. Run kegberry command as root user.')

BANNER = r"""
     oOOOOOo
    ,|    oO  Kegberry v{} - http://kegberry.com
   //|     |
   \\|     |  "{}"
    `|     |      -- {}
     `-----`
"""

QUOTES = (
    ('He was a wise man who invented beer.', 'Plato'),
    ('Beer is made by men, wine by God.', 'Martin Luther'),
    ('Who cares how time advances? I am drinking ale today.', 'Edgar Allen Poe'),
    ('It takes beer to make thirst worthwhile.', 'German proverb'),
    ('Beer: So much more than just a breakfast drink.', 'Homer Simpson'),
    ('History flows forward on a river of beer.', 'Anonymous'),
    ('Work is the curse of the drinking classes.', 'Oscar Wilde'),
    ('For a quart of ale is a dish for a king.', 'William Shakespeare, "A Winter\'s Tale"'),
    ('Beer. Now there\'s a temporary solution.', 'Homer Simpson'),
)

SERVER_VENV = 'kegbot-server.venv'
PYCORE_VENV = 'kegbot-pycore.venv'

REQUIRED_PACKAGES = (
    'build-essential',
    'nginx-light',
    'libjpeg-dev',
    'supervisor',
    'python-setuptools',
    'python-dev',
    'default-libmysqlclient-dev',
    'mysql-server',
    'redis-server',
)

logger = logging.getLogger(__name__)

class KegberryError(Exception): pass
class CommandError(KegberryError): pass

def get_version():
    try:
        return pkg_resources.get_distribution('kegberry').version
    except pkg_resources.DistributionNotFound:
        return '0.0.0'


def run_command(cmd, fail_silently=False, call=False):
    logger.debug('Running command: {}'.format(cmd))
    if FLAGS.fake:
        return 0
    try:
        path = os.environ['PATH']
        logger.debug('PATH: {}'.format(path))
        logger.debug(' CMD: {}'.format(cmd))
        if call:
            fn = subprocess.call
        else:
            fn = subprocess.check_output
        return fn(cmd, stderr=subprocess.STDOUT, shell=True,
            env={'PATH': path})
    except subprocess.CalledProcessError as e:
        if call:
            return
        if not fail_silently:
            print e.output
            print ''
            logger.error('Command returned error:')
            logger.error('  Command: {}'.format(cmd))
            logger.error('  Return code: {}'.format(e.returncode))
        raise e


def run_as_kegberry(cmd, **kwargs):
    cmd = cmd.replace('"', '\\"')
    wrapped = 'sudo su -l {} -c "{}"'.format(FLAGS.kegbot_user, cmd)
    return run_command(wrapped, **kwargs)


def run_in_virtualenv(venv, cmd, **kwargs):
    virtualenv = os.path.join(FLAGS.kegbot_home, venv)
    cmd = '. {}/bin/activate && {}'.format(virtualenv, cmd)
    return run_as_kegberry(cmd, **kwargs)


def run_mysql(subcommand, command='mysql', **kwargs):
    cmd = '{} -u {} '.format(command, FLAGS.mysql_user)
    if FLAGS.mysql_password:
        cmd += '-p="{}" '.format(FLAGS.mysql_password)
    cmd += subcommand
    return run_command(cmd, **kwargs)


def print_banner():
    version = get_version()
    quote, author = random.choice(QUOTES)
    print BANNER.format(version, quote, author)


def write_tempfile(data):
    fd, path = tempfile.mkstemp()
    with closing(os.fdopen(fd, 'w')) as tmp:
        tmp.write(data)
    return path


class KegberryApp(object):
    """Main command-line application."""
    def run(self):
        try:
            extra_argv = FLAGS(sys.argv)[1:]
        except gflags.FlagsError, e:
            self._usage(error=e, exit=1)
        if FLAGS.verbose:
            level = logging.DEBUG
        else:
            level = logging.INFO
        # logging.basicConfig(level=level,
        #     format='%(asctime)s %(levelname)-8s (%(name)s) %(message)s')
        logging.basicConfig(level=level,
            format='%(levelname)-8s: %(message)s')

        if getpass.getuser() == 'root':
            if not FLAGS.allow_root:
                print 'Error: Do not run `kegberry` as root or with sudo.'
                sys.exit(1)

        if not extra_argv:
            self._usage('Must give at least one command.', exit=1)

        command = extra_argv[0]
        args = extra_argv[1:]

        command_fn = getattr(self, command, None)
        if not command_fn or command.startswith('_'):
            self._usage('Error: command does not exist', exit=1)

        print_banner()
        command_fn(*args)

    def _usage(self, error=None, exit=None):
        """Prints help information."""
        print 'Usage: {} ARGS\n{}\n\n'.format(sys.argv[0], FLAGS)
        if error:
            print 'Error: %s' % (error,)
        if exit is not None:
            print 'Exiting ...'
            sys.exit(exit)

    def status(self, *args):
        """Print Kegberry/Kegbot status."""
        print 'App version: {}'.format(get_version())

    def _update_packages(self):
        logger.info('Updating package list ...')
        run_command('sudo bash -c "DEBIAN_FRONTEND=noninteractive apt-get -yq update"')

        if FLAGS.upgrade_system_packages:
            logger.info('Upgrading packages, this may take a while ...')
            run_command('sudo bash -c "DEBIAN_FRONTEND=noninteractive apt-get -yq upgrade"')

        logger.info('Installing required packages ...')
        run_command('sudo bash -c "DEBIAN_FRONTEND=noninteractive apt-get -yq install {}"'.format(
            ' '.join(REQUIRED_PACKAGES)))

        logger.info('Cleaning up ...')
        run_command('sudo bash -c "DEBIAN_FRONTEND=noninteractive apt-get -yq clean"')

    def install(self, *args):
        """Performs an first-time Kegberry install."""
        self._update_packages()

        logger.info('Checking if database exists ...')
        try:
            run_mysql(command='mysqlshow', subcommand=FLAGS.mysql_database, fail_silently=True)
        except subprocess.CalledProcessError:
            logger.info('Creating database ...')
            run_mysql('-e "create database {} CHARACTER SET latin1;"'.format(FLAGS.mysql_database))

        logger.info('Installing MySQL timezones ...')
        cmd = 'mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -u {}'.format(FLAGS.mysql_user)
        if FLAGS.mysql_password:
            cmd += ' -p={}'.format(FLAGS.mysql_password)
        cmd += ' mysql'
        run_command(cmd)

        user = FLAGS.kegbot_user
        try:
            pwd.getpwnam(user)
        except KeyError:
            logger.info('User "{}" does not exist, creating ...'.format(user))
            run_command('sudo useradd -G dialout -m {}'.format(user))

        venv_cmd = run_command('which virtualenv').strip()
        if not venv_cmd:
            logger.error('Could not find virtualenv command.')
            logger.error('PATH: {}'.format(os.envrion['PATH']))
            sys.exit(1)

        venvs = (SERVER_VENV,)
        if FLAGS.pycore:
            venvs += (PYCORE_VENV,)

        for venv_name in venvs:
            logger.info('Checking/installing virtualenv "{}"...'.format(venv_name))
            virtualenv = os.path.join(FLAGS.kegbot_home, venv_name)
            run_as_kegberry('if [ ! -e {} ]; then {} {}; fi'.format(virtualenv, venv_cmd, virtualenv))

        logger.info('Installing python server packages, this may take a while ...')
        run_in_virtualenv(SERVER_VENV, 'pip install {}'.format(FLAGS.kegbot_server_package))

        if FLAGS.pycore:
            logger.info('Installing pycore packages, this may take a while ...')
            run_in_virtualenv(PYCORE_VENV, 'pip install {}'.format(FLAGS.kegbot_pycore_package))

        logger.info('Installing Kegbot ...')
        cmd = 'setup-kegbot.py --interactive=false --db_type=mysql --db_database="{}"'.format(FLAGS.mysql_database)
        data_root = os.path.join(FLAGS.kegbot_home, 'kegbot-data')
        cmd += ' --data_root={}'.format(data_root)
        if FLAGS.mysql_password:
            cmd += ' --db_password="{}"'.format(FLAGS.mysql_password)
        run_in_virtualenv(SERVER_VENV, cmd)

        logger.info('Generating API key ...')
        api_key = run_in_virtualenv(SERVER_VENV, 'kegbot create_api_key Kegberry')

        api_cfg = "--api_url=http://localhost/api\\n--api_key={}\\n".format(api_key)
        run_as_kegberry('echo -e "{}" > ~/.kegbot/pycore-flags.txt'.format(api_cfg))
        run_as_kegberry('chmod 600 ~/.kegbot/pycore-flags.txt'.format(api_cfg))

        logger.info('Installing config files ...')
        template_vars = {
            'USER': FLAGS.kegbot_user,
            'HOME_DIR': FLAGS.kegbot_home,
            'DATA_DIR': data_root,
            'PYCORE_VENV': os.path.join(FLAGS.kegbot_home, PYCORE_VENV),
            'SERVER_VENV': os.path.join(FLAGS.kegbot_home, SERVER_VENV),
        }

        nginx_conf = write_tempfile(templates.NGINX_CONF.substitute(**template_vars))
        run_command('sudo bash -c "mv {} /etc/nginx/sites-available/default"'.format(nginx_conf))

        supervisor_tmpl = templates.SUPERVISOR_CONF if FLAGS.pycore else templates.SUPERVISOR_CONF_NO_PYCORE
        supervisor_conf = write_tempfile(supervisor_tmpl.substitute(**template_vars))
        run_command('sudo bash -c "mv {} /etc/supervisor/conf.d/kegbot.conf"'.format(supervisor_conf))

        logger.info('Reloading daemons ...')
        run_command('sudo bash -c "supervisorctl reload"')
        run_command('sudo bash -c "service nginx restart"')

    def upgrade(self, *args):
        """Upgrades an existing Kegbot/Kegberry install."""
        logger.info('Checking for `kegberry` command update')
        output = run_command('sudo bash -c "pip install -U kegberry"')
        logger.debug(output)
        if 'already up-to-date' in output:
            logger.info('Updating kegbot-server distribution ...')
            run_in_virtualenv(SERVER_VENV, 'pip install -U {}'.format(FLAGS.kegbot_server_package))

            if FLAGS.pycore:
                logger.info('Updating kegbot-pycore distribution ...')
                run_in_virtualenv(PYCORE_VENV, 'pip install -U {}'.format(FLAGS.kegbot_pycore_package))

            logger.info('Running `kegberry kegbot upgrade` ...')
            self.kegbot('upgrade')

            logger.info('Restarting services ...')
            run_command('sudo supervisorctl restart kegbot:*')

            logger.info('Done!')
        else:
            logger.info('Kegberry command upgraded.')
            logger.info('Please run "kegberry upgrade" again.')
            return

    def kegbot(self, *args):
        """Runs the `kegbot` command with any additional arguments."""
        cmd = 'kegbot {}'.format(' '.join(args))
        return run_in_virtualenv(SERVER_VENV, cmd, call=True)

    def delete(self, *args):
        """Erases all Kegberry software and user data."""
        confirm = raw_input('REALLY delete all Kegbot data? This is irreversible. Type YES: ')
        if confirm.strip() != 'YES':
            print 'Delete aborted.'
            sys.exit(1)

        logger.info('Stopping services ...')
        run_command('sudo supervisorctl stop kegbot:*')

        logger.info('Deleting user "{}" ...'.format(FLAGS.kegbot_user))
        run_command('sudo userdel -r -f {}; true'.format(FLAGS.kegbot_user))

        logger.info('Dropping database "{}"'.format(FLAGS.mysql_database))
        run_mysql('-e "drop database {}"'.format(FLAGS.mysql_database))

    def stop(self, *args):
        logger.info('Stopping services ...')
        run_command('sudo supervisorctl stop kegbot:*')

    def start(self, *args):
        logger.info('Starting services ...')
        run_command('sudo supervisorctl start kegbot:*')

    def restart(self, *args):
        logger.info('Restarting services ...')
        run_command('sudo supervisorctl restart kegbot:*')

