"""
Supervisor: A package for interacting with
long-running data analysis jobs.
"""

__author__ = """Daniel Williams"""
__email__ = "daniel.williams@ligo.org"
__packagename__ = __name__

import os
import logging

from pkg_resources import DistributionNotFound, get_distribution, resource_string

try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    # package is not installed
    __version__ = "dev"
    pass

try:
    import ConfigParser as configparser
except ImportError:
    import configparser
default_config = resource_string(__name__, "{}.conf".format(__packagename__))

config = configparser.ConfigParser()
# if not config_file:

config.read_string(default_config.decode("utf8"))
config_locations = [
    os.path.join(os.curdir, ".asimov", "{}.conf".format(__packagename__)),
    os.path.join(
        os.path.expanduser("~"),
        ".config",
        __packagename__,
        "{}.conf".format(__packagename__),
    ),
    os.path.join(os.path.expanduser("~"), ".{}".format(__packagename__)),
    "/etc/{}".format(__packagename__),
]

config_locations.reverse()

config.read([conffile for conffile in config_locations])


logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("MARKDOWN").setLevel(logging.WARNING)
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("git").setLevel(logging.WARNING)


logger_name = "asimov"
logger = logging.getLogger(logger_name)

logger_levels = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "update": 9,
}
try:
    LOGGER_LEVEL = logger_levels[config.get("logging", "logging level")]
except configparser.NoOptionError:
    LOGGER_LEVEL = logging.INFO

try:
    PRINT_LEVEL = logger_levels[config.get("logging", "print level")]
except configparser.NoOptionError:
    PRINT_LEVEL = logging.ERROR

ch = logging.StreamHandler()
print_formatter = logging.Formatter("[%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
ch.setFormatter(print_formatter)
ch.setLevel(PRINT_LEVEL)

logfile = "asimov.log"
fh = logging.FileHandler(logfile)
formatter = logging.Formatter(
    "%(asctime)s [%(name)s][%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
)
fh.setFormatter(formatter)
fh.setLevel(LOGGER_LEVEL)

logger.addHandler(ch)
logger.addHandler(fh)


try:
    if config.get("ledger", "engine") == "yamlfile":
        from .ledger import YAMLLedger

        current_ledger = YAMLLedger(config.get("ledger", "location"))
    elif config.get("ledger", "engine") == "gitlab":
        logger.error("The gitlab interface has been removed from v0.6 of asimov")
    else:
        current_ledger = None
except FileNotFoundError:
    # logger.error("Could not find a valid ledger file.")
    current_ledger = None
