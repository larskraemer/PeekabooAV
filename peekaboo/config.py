###############################################################################
#                                                                             #
# Peekaboo Extended Email Attachment Behavior Observation Owl                 #
#                                                                             #
# config.py                                                                   #
###############################################################################
#                                                                             #
# Copyright (C) 2016-2018  science + computing ag                             #
#                                                                             #
# This program is free software: you can redistribute it and/or modify        #
# it under the terms of the GNU General Public License as published by        #
# the Free Software Foundation, either version 3 of the License, or (at       #
# your option) any later version.                                             #
#                                                                             #
# This program is distributed in the hope that it will be useful, but         #
# WITHOUT ANY WARRANTY; without even the implied warranty of                  #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU           #
# General Public License for more details.                                    #
#                                                                             #
# You should have received a copy of the GNU General Public License           #
# along with this program.  If not, see <http://www.gnu.org/licenses/>.       #
#                                                                             #
###############################################################################

""" The configuration for the main program as well as the ruleset. Handles
defaults as well as reading a configuration file. """


import os
import sys
import logging
from ConfigParser import SafeConfigParser, NoSectionError, NoOptionError
from peekaboo.exceptions import PeekabooConfigException


logger = logging.getLogger(__name__)


class PeekabooConfig(object):
    """
    This class represents the Peekaboo configuration.

    :author: Sebastian Deiss
    """
    def __init__(self, config_file=None, log_level=None):
        """ Initialise the configuration with defaults, overwrite with command
        line options and finally read the configuration file. """
        # hard defaults: The idea here is that every config option has a
        # default that would in principle enable Peekaboo to run. Code using
        # the option should still cope with no or an empty value being handed
        # to it.
        self.user = 'peekaboo'
        self.group = 'peekaboo'
        self.pid_file = '/var/run/peekaboo/peekaboo.pid'
        self.sock_file = '/var/run/peekaboo/peekaboo.sock'
        self.log_level = logging.INFO
        self.log_format = '%(asctime)s - %(name)s - (%(threadName)s) - ' \
                          '%(levelname)s - %(message)s'
        self.interpreter = '/usr/bin/python -u'
        self.worker_count = 3
        self.sample_base_dir = '/tmp'
        self.job_hash_regex = '/var/lib/amavis/tmp/([^/]+)/parts.*'
        self.use_debug_module = False
        self.keep_mail_data = False
        self.db_url = 'sqlite:////var/lib/peekaboo/peekaboo.db'
        self.config_file = '/opt/peekaboo/etc/peekaboo.conf'
        self.ruleset_config = '/opt/peekaboo/etc/ruleset.conf'
        self.cuckoo_mode = "api"
        self.cuckoo_url = 'http://127.0.0.1:8090'
        self.cuckoo_poll_interval = 5
        self.cuckoo_storage = '/var/lib/peekaboo/.cuckoo/storage'
        self.cuckoo_exec = '/opt/cuckoo/bin/cuckoo'
        self.cuckoo_submit = '/opt/cuckoo/bin/cuckoo submit'
        self.cluster_instance_id = 0
        self.cluster_stale_in_flight_threshold = 1*60*60
        self.cluster_duplicate_check_interval = 60

        # section and option names for the configuration file. key is the above
        # variable name whose value will be overwritten by the configuration
        # file value. Third item can be getter function if special parsing is
        # required.
        config_options = {
            'log_level': ['logging', 'log_level', self.get_log_level],
            'log_format': ['logging', 'log_format'],
            'user': ['global', 'user'],
            'group': ['global', 'group'],
            'pid_file': ['global', 'pid_file'],
            'sock_file': ['global', 'socket_file'],
            'interpreter': ['global', 'interpreter'],
            'worker_count': ['global', 'worker_count'],
            'sample_base_dir': ['global', 'sample_base_dir'],
            'job_hash_regex': ['global', 'job_hash_regex'],
            'use_debug_module': ['global', 'use_debug_module'],
            'keep_mail_data': ['global', 'keep_mail_data'],
            'db_url': ['db', 'url'],
            'ruleset_config': ['ruleset', 'config'],
            'cuckoo_mode': ['cuckoo', 'mode'],
            'cuckoo_url': ['cuckoo', 'url'],
            'cuckoo_poll_interval': ['cuckoo', 'poll_interval'],
            'cuckoo_storage': ['cuckoo', 'storage_path'],
            'cuckoo_exec': ['cuckoo', 'exec'],
            'cuckoo_submit': ['cuckoo', 'submit'],
            'cluster_instance_id': ['cluster', 'instance_id'],
            'cluster_stale_in_flight_threshold': ['cluster', 'stale_in_flight_threshold'],
            'cluster_duplicate_check_interval': ['cluster', 'duplicate_check_interval'],
        }

        # overrides from outside, e.g. by command line arguments whose values
        # are needed while reading the configuration file already (most notably
        # log level and path to the config file).
        if log_level:
            self.log_level = log_level
        if config_file:
            self.config_file = config_file

        # setup default logging to log any errors during the
        # parsing of the config file.
        self.setup_logging()

        # read configuration file. Note that we require a configuration file
        # here. We may change that if we decide that we want to allow the user
        # to run us with the above defaults only.
        if not os.path.isfile(self.config_file):
            raise PeekabooConfigException(
                'Configuration file "%s" does not exist or is not a file.' %
                self.config_file)

        if not os.access(self.config_file, os.R_OK):
            raise PeekabooConfigException(
                'Configuration file "%s" is not accessible for reading.' %
                self.config_file)

        self.__config = SafeConfigParser()
        self.__config.read(self.config_file)

        # overwrite above defaults in our member variables via indirect access
        settings = vars(self)
        for (option, config_names) in config_options.items():
            # maybe use special getter
            get = self.get
            if len(config_names) == 3:
                get = config_names[2]

            # e.g.:
            # self.log_format = self.get('logging', 'log_format',
            #                            self.log_format)
            settings[option] = get(config_names[0], config_names[1],
                                   settings[option])

        # Update logging with what we just parsed from the config
        self.setup_logging()

        # here we could overwrite defaults and config file with additional
        # command line arguments if required

        # log the configuration options if we are in debug mode
        if self.log_level == logging.DEBUG:
            logger.debug(self)

    def get(self, section, option, default=None, option_type=None):
        """ Get an option from the configuration file parser. Automatically
        detects the type from the type of the default if given and calls the
        right getter method to coerce the value to the correct type.

        :param section: Which section to look for option in.
        :type section: string
        :param option: The option to read.
        :type option: string
        :param default: (optional) Default value to return if option is not
                        found. Defaults itself to None so that the method will
                        return None if the option is not found.
        :type default: int, bool, str or None.
        :param option_type: Override the option type.
        :param type: int, bool, str or None. """
        if option_type is None and default is not None:
            option_type = type(default)

        getter = {
            int: self.__config.getint,
            bool: self.__config.getboolean,
            str: self.__config.get,
            None: self.__config.get,
        }

        try:
            return getter[option_type](section, option)
        except NoSectionError:
            logger.debug('Configuration section %s not found - using '
                         'default %s', section, default)
        except NoOptionError:
            logger.debug('Configuration option %s not found in section '
                         '%s - using default: %s', option, section, default)

        return default

    def get_log_level(self, section, option, default=None):
        """ Get the log level from the configuration file and parse the string
        into a logging loglevel such as logging.CRITICAL. Raises config
        exception if the log level is unknown. Options identical to get(). """
        levels = {
            'CRITICAL': logging.CRITICAL,
            'ERROR': logging.ERROR,
            'WARNING': logging.WARNING,
            'INFO': logging.INFO,
            'DEBUG': logging.DEBUG
        }

        level = self.get(section, option, None)
        if level is None:
            return default

        if not levels.has_key(level):
            raise PeekabooConfigException('Unknown log level %s' % level)

        return levels[level]

    def setup_logging(self):
        """ Setup logging to console by reconfiguring the root logger so that
        it affects all loggers everywhere.  """
        _logger = logging.getLogger()

        # Check if we already have a log handler
        if _logger.handlers:
            # Remove all handlers
            for handler in _logger.handlers:
                _logger.removeHandler(handler)
        # log format
        log_formatter = logging.Formatter(self.log_format)
        # create console handler and set level to debug
        to_console_log_handler = logging.StreamHandler(sys.stdout)
        to_console_log_handler.setFormatter(log_formatter)
        _logger.addHandler(to_console_log_handler)
        _logger.setLevel(self.log_level)

    def __str__(self):
        settings = {}
        for (option, value) in vars(self).items():
            if not option.startswith('_'):
                settings[option] = value

        return '<PeekabooConfig(%s)>' % str(settings)

    __repr__ = __str__


class PeekabooRulesetConfiguration(object):
    """
    This class represents the ruleset configuration file "ruleset.conf".

    The ruleset configuration is stored as a dictionary in the form of
    ruleset_config[rule_name][config_option] = value | [value1, value2, ...]

    @author: Sebastian Deiss
    @since: 1.6
    """
    def __init__(self, config_file):
        self.config_file = config_file
        self.ruleset_config = {}
        config = SafeConfigParser()
        try:
            config.read(self.config_file)
            for section in config.sections():
                if section not in self.ruleset_config.keys():
                    self.ruleset_config[section] = {}
                for setting, value in config.items(section):
                    if '.' in setting:
                        key = setting.split('.')[0]
                        if key not in self.ruleset_config[section]:
                            self.ruleset_config[section][key] = []
                        self.ruleset_config[section][key].append(value)
                    else:
                        self.ruleset_config[section][setting] = value
        except NoSectionError as e:
            logger.exception(e)
        except NoOptionError as e:
            logger.exception(e)

    def rule_config(self, rule):
        # potentially do some validity checks here

        # arbitrary interface definition: return an empty hash if no rule
        # config exists as empty rule config so the rule func can rely on it
        # and does not need to do any type checking
        return self.ruleset_config.get(rule, {})

    # rule is enabled as long as:
    # - no config section for that rule is present
    # - enabled keyword is not present in that section or
    # - enabled is not equal to 'no'
    def rule_enabled(self, rule):
        return (self.rule_config(rule).get('enabled', 'yes') != 'no')

    def __str__(self):
        return '<PeekabooRulesetConfiguration(filepath="%s")>' % self.config_file

    __repr__ = __str__
