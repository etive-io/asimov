"""
This module contains tools to log data from runs.
Unlike a conventional python process, processes run by
asimov may wish to send information to a number of different
locations, and store information for review purposes.
"""

import logging
import datetime
import asimov.database as database
from asimov import mattermost


logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("MARKDOWN").setLevel(logging.WARNING)
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("git").setLevel(logging.WARNING)


class AsimovLogger:
    def __init__(self, logfile):
        """
        An object for logging asimov productions.

        Parameters
        ----------
        logfile : str
           The location of the log file to be written.
        """
        self.logfile = logfile
        self.mattermost = mattermost.Mattermost()
        self.file_logger = logging.basicConfig(filename=logfile)

        logger_name = "asimov"
        self.logger = logging.getLogger(logger_name)

        formatter = logging.Formatter(
            "%(asctime)s [%(name)s][%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        print_formatter = logging.Formatter(
            "[%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )

        ch = logging.StreamHandler()
        ch.setFormatter(print_formatter)
        ch.setLevel(logging.ERROR)

        fh = logging.FileHandler(logfile)
        fh.setFormatter(formatter)
        fh.setLevel(logging.INFO)

        self.logger.addHandler(ch)
        self.logger.addHandler(fh)

    def log(
        self,
        level,
        message,
        event=None,
        production=None,
        pipeline=None,
        module=None,
        time=None,
    ):
        """
        Record a log message.

        Parameters
        ----------
        level : str, {DEBUG, INFO, WARNING, ERROR}
           The level of the logging message.
        event : ``asimov.event.Event``
           The event which this message is for.
        production : ``asimov.event.Production``, optional
           The production this message is for.
        message : str
           The free-form message for the log message.
        channels : list, or str, {"file", "mattermost"}, optional
           The list of places where the log message should be sent.
           Defaults to file only.
        """

        logger_levels = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "update": 9,
        }

        if not production:
            production = ""

        self.logger.log(logger_levels[level.lower()], message)

    def info(self, message, production=None, channels="file"):
        """
        Record an information message.

        Parameters
        ----------

        production : ``asimov.event.Production``, optional
           The production this message is for.
        message : str
           The free-form message for the log message.
        channels : list, or str, {"file", "mattermost"}, optional
           The list of places where the log message should be sent.
           Defaults to file only.
        """

        self.log("info", message, production, channels)

    def error(self, message, production=None, channels="file"):
        """
        Record an error message.

        Parameters
        ----------

        production : ``asimov.event.Production``, optional
           The production this message is for.
        message : str
           The free-form message for the log message.
        channels : list, or str, {"file", "mattermost"}, optional
           The list of places where the log message should be sent.
           Defaults to file only.
        """

        self.log("error", message, production, channels)

    def warning(self, message, production=None, channels="file"):
        """
        Record an warning message.

        Parameters
        ----------

        production : ``asimov.event.Production``, optional
           The production this message is for.
        message : str
           The free-form message for the log message.
        channels : list, or str, {"file", "mattermost"}, optional
           The list of places where the log message should be sent.
           Defaults to file only.
        """

        self.log("warning", message, production, channels)

    def list(self, offset=0, length=10, **filters):
        class LogEntry:
            def __init__(self, data):
                data = data.strip().split(":")
                self.level = data[0].lower()
                try:
                    self.module = data[1]
                    if self.module == "root":
                        self.module = "asimov"
                except KeyError:
                    self.module = None
                try:
                    self.message = data[2]
                except KeyError:
                    self.message = None

            def __dictrepr__(self):
                return dict(level=self.level, module=self.module, message=self.message)

        entries = []
        with open(self.logfile, "r") as filehandle:
            for line in filehandle:
                entries.append(LogEntry(line))

        def apply_filter(entries, parameter, value):
            entries = filter(lambda x: getattr(x, parameter) == value, entries)
            return entries

        if filters:
            for parameter, value in filters.items():
                entries = apply_filter(entries, parameter, value)
            entries = list(entries)

        if offset:
            return entries[-int(length) + int(offset): -int(offset)]
        else:
            return entries[-int(length):]


class DatabaseLogger(AsimovLogger):
    """
    This class implements a database-backed log collector.
    """

    def __init__(self):
        self.database = database.Logger

    def log(
        self, level, message, event=None, production=None, pipeline=None, module=None
    ):
        """
        Record a log message.

        Parameters
        ----------
        level : str, {DEBUG, INFO, WARNING, ERROR}
           The level of the logging message.
        production : ``asimov.event.Production``, optional
           The production this message is for.
        message : str
           The free-form message for the log message.
        channels : list, or str, {"file", "mattermost"}, optional
           The list of places where the log message should be sent.
           Defaults to file only.
        """

        entry = self.database(
            pipeline, module, level, datetime.datetime.now(), event, production, message
        )
        entry.save()

    def list(self, **filters):
        """
        Return all logging events which satisfy a set of ``filters``.

        Examples
        --------

        """

        events = self.database.list(**filters)
        return events
