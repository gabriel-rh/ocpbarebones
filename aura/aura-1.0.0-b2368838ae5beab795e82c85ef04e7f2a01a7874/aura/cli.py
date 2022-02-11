from __future__ import print_function
import copy
import importlib
import logging
import os
import sys
from pkg_resources import iter_entry_points

import click

from aura import __version__, VIDEOS_NAME
from aura.compat import ConfigParser


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'], obj={'app_version': __version__})
CONFIG_DEFAULTS = dict(verify_certs="True")
WIN = sys.platform.startswith('win')
VERBOSE_LOG_LEVEL = logging.INFO - 1
log = logging.getLogger("aura")


class ExtendableCLI(click.MultiCommand):
    """A class that allows for the application to be extended with additional commands by dynamically loading the commands"""
    commands_dir = os.path.join(os.path.dirname(__file__), 'commands')
    plugin_group_name = "aura.commands"

    def list_commands(self, ctx):
        rv = set()
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.py') and filename.startswith("cmd_"):
                command_name = filename[4:-3].replace("_", "-")
                rv.add(command_name)
        for plugin in iter_entry_points(self.plugin_group_name):
            rv.add(plugin.name)
        return sorted(rv)

    def get_command(self, ctx, name):
        name = name.replace("-", "_")
        if sys.version_info[0] == 2:
            name = name.encode('ascii', 'replace')

        # check the plugins first
        for plugin in iter_entry_points(self.plugin_group_name):
            if plugin.name == name:
                return plugin.load()

        # try importing a built-in command
        try:
            mod = importlib.import_module('aura.commands.cmd_' + name)
        except ImportError as e:
            log.error(str(e))
            return
        return mod.cli


# See http://stackoverflow.com/a/2205909/1330640
class ColoredConsoleHandler(logging.StreamHandler, object):
    def emit(self, record):
        # Need to make a actual copy of the record
        # to prevent altering the message for other loggers
        myrecord = copy.copy(record)

        # Only add colors if we are not using windows
        if not WIN:
            levelno = myrecord.levelno
            if levelno >= logging.ERROR:
                myrecord.msg = click.style(str(myrecord.msg), fg="red", bold=True)
            elif levelno >= logging.WARN:
                myrecord.msg = click.style(str(myrecord.msg), fg="yellow")
            elif levelno == logging.DEBUG:
                myrecord.msg = click.style(str(myrecord.msg), fg="green")
        super(ColoredConsoleHandler, self).emit(myrecord)


def print_version(ctx, param, value):
    """Prints the application version to the console"""
    if not value or ctx.resilient_parsing:
        return

    # Find the app name and version
    name = ctx.find_root().info_name
    version = ctx.obj.get('app_version', 'n/a')

    # Print the information and exit
    # Note: Don't use the logger here since it's eagerly invoked and logging won't have been initialised
    click.echo("{0}, version {1}".format(name, version))
    ctx.exit()


def _init_config_parser(ctx, defaults=None, sections=None):
    """Creates a config parser instance and adds the default sections"""
    app_name = ctx.find_root().info_name

    config = ConfigParser(defaults=defaults)
    config.add_section(app_name)
    config.add_section(VIDEOS_NAME)

    # Add any additional sections
    if sections:
        for section in sections:
            config.add_section(section)
    return config


def init_logging(debug, verbose):
    """Sets up the logging format and log level"""
    if verbose:
        log_level = VERBOSE_LOG_LEVEL
    elif debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.ERROR

    handler = ColoredConsoleHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logging.root.addHandler(handler)
    logging.root.setLevel(log_level)

    # Capture warnings
    try:
        logging.captureWarnings(True)
    except AttributeError:
        import compat
        compat.capture_warnings(True)

    # Add the verbose logging level. See http://stackoverflow.com/a/13638084
    def log_verbose(self, message, *args, **kwargs):
        if self.isEnabledFor(VERBOSE_LOG_LEVEL):
            self._log(VERBOSE_LOG_LEVEL, message, args, **kwargs)
    logging.addLevelName(VERBOSE_LOG_LEVEL, "INFO")
    logging.Logger.verbose = log_verbose

    # Set the log level to INFO, if we aren't debugging
    if not debug and not verbose:
        log.setLevel(logging.INFO)


def init_sys_config(ctx, config_file=None, config_defaults=CONFIG_DEFAULTS, config_sections=None):
    """Parses the configuration file and stores it in the click context"""
    config = _init_config_parser(ctx, config_defaults, config_sections)

    # Use the default location if no config file was passed
    if not config_file:
        app_name = ctx.find_root().info_name
        config_file = '/etc/{0}/{1}.conf'.format(app_name, app_name)

    # Make sure the configuration file exists
    if not os.path.isfile(config_file):
        log.error("Failed loading the global configuration from %s", config_file)
        ctx.exit(1)

    log.debug("Loading global configuration from %s", config_file)
    config.read(config_file)
    ctx.obj['CONFIG'] = config
    return config


def init_user_config(ctx, config_file, config_defaults=None, config_sections=None):
    """Parses the users configuration file and stores it in the click context"""
    config = _init_config_parser(ctx, config_defaults, config_sections)
    default_config = False

    # Use the default location if no config file was passed
    if not config_file:
        app_name = ctx.find_root().info_name
        config_file = os.path.join(click.get_app_dir(app_name), app_name + ".conf")
        default_config = True

    # Make sure the configuration file exists
    if not default_config and not os.path.isfile(config_file):
        log.error("Failed loading the user configuration from %s", config_file)
        ctx.exit(1)
    elif os.path.isfile(config_file):
        log.debug("Loading user configuration from %s", config_file)
        config.read(config_file)

    ctx.obj['USER_CONFIG'] = config
    return config


def print_parsed_debug_details(ctx):
    """Prints information useful for debugging the command"""
    if ctx.obj.get("DEBUG", False):
        log.debug("--debug is on")
    if ctx.obj.get("VERBOSE", False):
        log.debug("--verbose is on")


def init_cli_context(ctx, debug=False, verbose=False):
    # add the debug and verbose option values to the context
    ctx.obj = {'DEBUG': debug, 'VERBOSE': verbose, 'CONFIG': None}


def init_cli(ctx, config, debug=False, verbose=False, app_defaults=CONFIG_DEFAULTS, config_sections=None):
    # Initial the cli context
    init_cli_context(ctx, debug, verbose)

    # Set up the logging
    init_logging(debug, verbose)

    # Parse the configuration files
    init_sys_config(ctx, config_defaults=app_defaults, config_sections=config_sections)
    init_user_config(ctx, config, config_sections=config_sections)

    # Print the version when verbose logging
    if verbose or debug:
        name = ctx.find_root().info_name
        log.verbose("%s, version %s", name, __version__)

    # Print the debugging information if requested
    if debug:
        print_parsed_debug_details(ctx)


@click.command(cls=ExtendableCLI, context_settings=CONTEXT_SETTINGS)
@click.option("-c", "--config", metavar="CONFIG", help="Specify a config file to use.", type=click.Path(exists=True, readable=True))
@click.option("--debug", help="Print debugging information.", is_flag=True, default=False)
@click.option("--verbose", help="Print detailed information about each step.", is_flag=True, default=False)
@click.option("-v", "--version", is_flag=True, help="Print the version of the application.", callback=print_version, expose_value=False,
              is_eager=True)
@click.pass_context
def cli(ctx, config, debug, verbose):
    # If help is in a sub command, don't setup the logging and config
    if not any(x in ctx.help_option_names for x in ctx.args):
        init_cli(ctx, config, debug, verbose)


if __name__ == '__main__':
    cli()
