"""
Supervisor: A package for interacting with
long-running data analysis jobs.
"""

__author__ = """Daniel Williams"""
__email__ = "daniel.williams@ligo.org"
__packagename__ = __name__

import os
import logging
from logging.handlers import RotatingFileHandler

try:
    from importlib.metadata import version, PackageNotFoundError
    from importlib.resources import files
except ImportError:
    from importlib_metadata import version, PackageNotFoundError
    from importlib_resources import files

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # package is not installed
    __version__ = "dev"

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

default_config = files(__name__).joinpath(f"{__packagename__}.conf").read_bytes()

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

logger.addHandler(ch)

# File handler is not added by default - it's lazy-loaded when needed
_file_handler = None
import threading
_file_handler_lock = threading.Lock()

def setup_file_logging(logfile=None):
    """
    Set up file logging for asimov.

    This function should be called by commands that need to write logs to a file.
    Read-only commands like --help or --version should not call this.

    Parameters
    ----------
    logfile : str, optional
        Path to the log file. If None, uses configuration or default location.
    """
    global _file_handler

    # Only set up file handler once (thread-safe check)
    with _file_handler_lock:
        if _file_handler is not None:
            return
    
        # Determine log file location
        if logfile is None:
            try:
                log_directory = config.get("logging", "location")
                try:
                    if not os.path.exists(log_directory):
                        # Create directory with appropriate permissions
                        os.makedirs(log_directory, mode=0o755)
                    logfile = os.path.join(log_directory, "asimov.log")
                except OSError as e:
                    # If we cannot create or use the configured log directory, fall back to current directory
                    logger.error(
                        "Failed to create or access log directory '%s': %s. "
                        "Falling back to current directory for logging.",
                        log_directory,
                        e,
                    )
                    logfile = "asimov.log"
            except (configparser.NoOptionError, configparser.NoSectionError):
                # Fall back to current directory if no config
                logfile = "asimov.log"
        
        # Use RotatingFileHandler to prevent log files from growing too large
        # Default: 10 MB per file, keep 5 backup files
        max_bytes = 10 * 1024 * 1024  # 10 MB
        backup_count = 5
        
        try:
            # Try to get custom values from config
            max_bytes = int(config.get("logging", "max_bytes"))
        except (configparser.NoOptionError, configparser.NoSectionError):
            # No config value provided, use default
            pass
        except ValueError as e:
            logger.warning(f"Invalid value for logging.max_bytes in config, using default: {e}")
        
        try:
            backup_count = int(config.get("logging", "backup_count"))
        except (configparser.NoOptionError, configparser.NoSectionError):
            # No config value provided, use default
            pass
        except ValueError as e:
            logger.warning(f"Invalid value for logging.backup_count in config, using default: {e}")
        
        try:
            _file_handler = RotatingFileHandler(
                logfile, maxBytes=max_bytes, backupCount=backup_count
            )
            formatter = logging.Formatter(
                "%(asctime)s [%(name)s][%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
            )
            _file_handler.setFormatter(formatter)
            _file_handler.setLevel(LOGGER_LEVEL)
            logger.addHandler(_file_handler)
        except (OSError, IOError) as e:
            # Log to stderr if file logging cannot be set up
            import sys
            sys.stderr.write(
                f"Warning: Failed to set up file logging to '{logfile}': {e}\n"
                "Continuing without file logging.\n"
            )
            _file_handler = None  # Mark as attempted but failed


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
