# """
# Logging utilities module.
#
# This module provides functionality for logging to the console and files,
# as well as the ability to redirect log messages through custom callables.
# Users can enable a redirection and choose whether to redirect all logs or only
# those logs that would also be output to the console (i.e. those that meet the
# current log level threshold).
# """
#
# import inspect
# import logging
# import os
# import atexit
# import threading
# from datetime import datetime
# from dataclasses import dataclass
# from typing import Callable
#
# from core.utils import colors
# from core.utils import string_utils as string_utils
#
# # Define mapping for log level names to numeric levels
# LOG_LEVELS = {
#     "CRITICAL": logging.CRITICAL,
#     "ERROR": logging.ERROR,
#     "WARNING": logging.WARNING,
#     "INFO": logging.INFO,
#     "DEBUG": logging.DEBUG,
#     "NOTSET": logging.NOTSET,
#     "IMPORTANT": 25,
# }
#
# # Central color map by numeric log level (importable from other modules)
# LOGGING_COLORS = {
#     logging.DEBUG: colors.DARK_GREY,
#     LOG_LEVELS['IMPORTANT']: colors.MEDIUM_GREEN,
#     logging.INFO: colors.WHITE,
#     logging.WARNING: colors.MEDIUM_ORANGE,
#     logging.ERROR: colors.RED,
#     logging.CRITICAL: colors.RED,
# }
#
# logging.addLevelName(LOG_LEVELS["IMPORTANT"], "IMPORTANT")
#
# # List to store all enabled redirections
# redirections = []
#
# # Global variable to manage file logging state
# log_files: dict = {}
#
# # Global dictionary to store custom Logger instances to prevent duplicates.
# custom_loggers = {}
#
# _show_log_file = False
# _show_log_level = False
#
#
# # === SET LOGGING SETTINGS =============================================================================================
# def setLoggingSettings(show_log_file=False, show_log_level=False):
#     """
#     Update global formatting flags and reconfigure all existing Logger instances
#     so they pick up the new settings immediately.
#     """
#     global _show_log_file, _show_log_level
#     _show_log_file = show_log_file
#     _show_log_level = show_log_level
#
#     # Re-apply formatter settings on every existing Logger
#     for lg in custom_loggers.values():
#         if hasattr(lg, '_apply_formatter_settings'):
#             lg._apply_formatter_settings()
#
#
# @atexit.register
# def cleanup(*args, **kwargs):
#     """
#     Closes all open log files when the program exits.
#     """
#     global log_files
#     for filename, data in log_files.items():
#         data['file'].close()
#
#
# @dataclass
# class LogRedirection:
#     """
#     Class representing a log redirection.
#
#     Attributes:
#         func (callable): The function to call for redirection.
#         redirect_all (bool): If True, all logs are redirected. If False, only
#                              logs that meet or exceed the console log level.
#     """
#     func: Callable
#     minium_level: int = logging.NOTSET
#     redirect_all: bool = False
#
#
# def addLogRedirection(func, redirect_all: bool = False, minimum_level: int | str = logging.NOTSET):
#     """
#     Enables a log redirection.
#
#     Parameters:
#         minimum_level: Minimum log level to redirect.
#         func (callable): The function to be called for log redirection.
#         redirect_all (bool): If True, redirect all log messages. If False, only
#                              redirect logs that meet or exceed the console log level.
#     """
#     global redirections
#     if isinstance(minimum_level, str):
#         minimum_level = LOG_LEVELS.get(minimum_level, logging.NOTSET)
#
#     redirections.append(LogRedirection(func, minium_level=minimum_level, redirect_all=redirect_all))
#
#
# def removeLogRedirection(func):
#     """
#     Disables a previously enabled log redirection.
#
#     Parameters:
#         func (callable): The redirection function to disable.
#     """
#     global redirections
#     redirections[:] = [redir for redir in redirections if redir.func != func]
#
#
# def enable_file_logging(filename, path='./', custom_header: str = '', log_all_levels=False):
#     """
#     Enables file logging. Creates a log file with the name "<filename>_yyyymmdd_hhmmss.log".
#
#     Parameters:
#         filename (str): The base name of the log file.
#         path (str): Directory where the log file will be saved.
#         custom_header (str): Optional header information to include in the log.
#         log_all_levels (bool): If True, all logs are written to the file regardless of level.
#     """
#     global log_files
#
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     log_filename = f"{path}/{filename}_{timestamp}.log"
#
#     try:
#         log_file = open(log_filename, 'a')
#         log_file.write("BILBO Log\n")
#         log_file.write(f"Time {timestamp}: {custom_header}\n")
#         log_file.write("YYYY-MM-DD_hh-mm-ss-ms \t Logger \t Level \t Log\n")
#         log_files[filename] = {
#             'file': log_file,
#             'all_levels': log_all_levels,
#             'lock': threading.Lock()
#         }
#         print(f"File logging enabled. Logging to file: {log_filename}")
#     except IOError as e:
#         print(f"Failed to open log file {log_filename}: {e}")
#
#
# def stop_file_logging(filename=None):
#     """
#     Stops file logging and closes the log file(s).
#
#     Parameters:
#         filename (str, optional): If provided, only the log file with this base name is stopped.
#                                   Otherwise, all log files are closed.
#     """
#     global log_files
#
#     if filename is not None:
#         if filename in log_files:
#             log_files[filename]['file'].close()
#             log_files.pop(filename)
#             print(f"File logging stopped for {filename}.")
#     else:
#         for filename, data in log_files.items():
#             data['file'].close()
#             print(f"File logging stopped for {filename}.")
#         log_files = {}
#
#
# def handle_log(log, logger: 'Logger', level):
#     """
#     Handles a log message by formatting it and sending it to any enabled redirections and file loggers.
#
#     Parameters:
#         log (str): The log message.
#         logger (Logger): The logger instance issuing the log.
#         level (int or str): The numeric or string log level.
#     """
#     global log_files
#
#     # Convert level from string to numeric value if necessary
#     if isinstance(level, str):
#         level = LOG_LEVELS.get(level, logging.NOTSET)
#
#     # Create reverse mapping to get level name from numeric level
#     reversed_levels = {v: k for k, v in LOG_LEVELS.items()}
#     level_name = reversed_levels.get(level, "NOTSET")
#
#     current_time = datetime.now().strftime("%Y-%m-%d:%H-%M-%S-%f")[:-3]
#     log_entry = f"{current_time}\t{logger.name}\t{level_name}\t{log}\n"
#
#     # Process redirections: if a redirection is set to redirect_all, send all logs;
#     # otherwise, only send logs that meet or exceed the logger's threshold.
#     for redir in redirections:
#         if redir.redirect_all or (level >= logger.level and level >= redir.minium_level):
#             redir.func(log_entry, log, logger, level)
#
#     # Write log entries to file(s) if file logging is enabled
#     try:
#         for filename, log_file_data in log_files.items():
#             with log_file_data['lock']:
#                 if level >= logger.level or log_file_data['all_levels']:
#                     log_file_data['file'].write(log_entry)
#                     log_file_data['file'].flush()
#     except IOError as e:
#         print(f"Failed to write to log file: {e}")
#
#
# def disableAllOtherLoggers(module_name=None):
#     """
#     Disables all loggers except the one associated with the provided module name.
#
#     Parameters:
#         module_name (str, optional): The module name whose logger should remain enabled.
#     """
#     for log_name, log_obj in logging.Logger.manager.loggerDict.items():
#         if log_name != module_name:
#             log_obj.disabled = True
#
#
# def disableLoggers(loggers: list):
#     """
#     Disables loggers whose names are in the provided list.
#
#     Parameters:
#         loggers (list): A list of logger names to disable.
#     """
#     for log_name, log_obj in logging.Logger.manager.loggerDict.items():
#         if log_name in loggers:
#             log_obj.disabled = True
#
#
# def getLoggerByName(logger_name: str):
#     """
#     Retrieves a logger by its name.
#
#     Parameters:
#         logger_name (str): The name of the logger to retrieve.
#
#     Returns:
#         Logger or None: The logger object if found, otherwise None.
#     """
#     for log_name, log_obj in logging.Logger.manager.loggerDict.items():
#         if log_name == logger_name:
#             return log_obj
#     return None
#
#
# def setLoggerLevel(logger, level=logging.DEBUG):
#     """
#     Sets the logging level for one or more loggers.
#
#     Parameters:
#         logger (str, list, or list of tuples): The logger name(s) or a list of tuples
#                                                (logger_name, level) to set levels.
#         level (int or str): The logging level to set (used if logger is a single name or list of names).
#     """
#     # Convert level if it's a string.
#     if isinstance(level, str):
#         level = LOG_LEVELS.get(level, logging.NOTSET)
#
#     if isinstance(logger, str):
#         l = logging.getLogger(logger)
#         l.setLevel(level)
#     elif isinstance(logger, list) and all(isinstance(l, tuple) for l in logger):
#         for logger_tuple in logger:
#             logger_name, lvl = logger_tuple
#             if isinstance(lvl, str):
#                 lvl = LOG_LEVELS.get(lvl, logging.NOTSET)
#             l = getLoggerByName(logger_name)
#             if l is not None:
#                 l.setLevel(lvl)
#     elif isinstance(logger, list) and all(isinstance(l, str) for l in logger):
#         for logger_name in logger:
#             logger_object = getLoggerByName(logger_name)
#             if logger_object is not None:
#                 logger_object.setLevel(level)
#
#
# class CustomFormatter(logging.Formatter):
#     """
#     Custom log formatter that applies color formatting based on the log level.
#     """
#     _filename: str | None
#
#     def __init__(self):
#         super().__init__()
#
#         # Remove any existing handlers from the root logger
#         for handler in logging.root.handlers[:]:
#             logging.root.removeHandler(handler)
#
#         if _show_log_level:
#             if _show_log_file:
#                 self.str_format = "%(asctime)s.%(msecs)03d %(levelname)-12s  %(name)-20s %(filename)-30s  %(message)s"
#             else:
#                 self.str_format = "%(asctime)s.%(msecs)03d %(levelname)-12s  %(name)-20s  %(message)s"
#         else:
#             if _show_log_file:
#                 self.str_format = "%(asctime)s.%(msecs)03d %(name)-20s %(filename)-30s  %(message)s"
#             else:
#                 self.str_format = "%(asctime)s.%(msecs)03d %(name)-20s  %(message)s"
#
#         self._filename = None
#
#         # Build per-level formats from RAW colors by escaping here
#         self.FORMATS = {
#             lvl: string_utils.escapeCode(raw_color) + self.str_format + string_utils.reset
#             for lvl, raw_color in LOGGING_COLORS.items()
#         }
#         self.DEFAULT_FORMAT = self.str_format
#
#     def setFileName(self, filename):
#         """
#         Sets the filename to be included in log records.
#
#         Parameters:
#             filename (str): The filename to display in the log.
#         """
#         self._filename = filename
#
#     def format(self, record):
#         """
#         Formats the log record with the appropriate colors and formatting.
#         """
#         log_fmt = self.FORMATS.get(record.levelno, self.DEFAULT_FORMAT)
#         formatter = logging.Formatter(log_fmt, "%H:%M:%S")
#         record.filename = self._filename
#         record.levelname = f'[{record.levelname}]'
#         record.filename = f'({record.filename})'
#         record.name = f'[{record.name}]'
#         record.filename = f'{record.filename}:'
#         return formatter.format(record)
#
#
# class Logger:
#     """
#     Custom Logger class that wraps Python's standard logging.Logger.
#     Provides methods for colored console output, file logging, log redirection,
#     and the ability to remap log levels on the fly.
#     """
#     _logger: logging.Logger
#     name: str
#     color: list
#
#     def __new__(cls, name, *args, **kwargs):
#         global custom_loggers
#         if name in custom_loggers:
#             return custom_loggers[name]
#         instance = super(Logger, cls).__new__(cls)
#         custom_loggers[name] = instance
#         return instance
#
#     def __init__(self, name, level: str = 'INFO', info_color=colors.LIGHT_GREY, background=None, color=None):
#         # Ensure mapping dict exists even if re-initializing existing logger
#         if not hasattr(self, '_level_map'):
#             self._level_map = {}
#
#         self.name = name
#         self._logger = logging.getLogger(name)
#         # Check if the underlying logger has already been configured.
#         if getattr(self._logger, '_custom_initialized', False):
#             self.setLevel(level)
#             return
#
#         self.setLevel(level)
#         self.color = color
#
#         # Convert RGB tuple/list to 256-color escape if necessary.
#         if isinstance(info_color, tuple) or isinstance(info_color, list):
#             info_color = string_utils.rgb_to_256color_escape(info_color, background)
#
#         # Create a new formatter and add a stream handler only once.
#         self.formatter = CustomFormatter()
#         self.stream_handler = logging.StreamHandler()
#         self.stream_handler.setFormatter(self.formatter)
#         self._logger.addHandler(self.stream_handler)
#         self._logger.propagate = False
#         self._logger._custom_initialized = True
#
#     def _apply_formatter_settings(self):
#         """
#         Re-create the CustomFormatter (respecting the current
#         _show_log_file/_show_log_level flags) and re-attach it
#         to the stream handler.
#         """
#         new_fmt = CustomFormatter()
#         self.formatter = new_fmt
#         self.stream_handler.setFormatter(new_fmt)
#
#     @staticmethod
#     def getFileName():
#         """
#         Retrieves the filename of the caller.
#
#         Returns:
#             str: The base name of the caller's file.
#         """
#         frame = inspect.currentframe().f_back.f_back
#         filename = frame.f_globals.get('__file__', 'unknown')
#         return os.path.basename(filename)
#
#     def _mapped_log(self, original_level, msg, *args, **kwargs):
#         """
#         Internal helper to remap a log call from original_level to a mapped
#         level (if configured), then emit the log and handle redirections/file output.
#         """
#         self.formatter.setFileName(self.getFileName())
#         # Determine mapped level (defaults to the original)
#         mapped_level = self._level_map.get(original_level, original_level)
#         # Emit via underlying logger
#         self._logger.log(mapped_level, msg, *args, **kwargs)
#         # Handle redirections and file output
#         handle_log(msg, logger=self, level=mapped_level)
#
#     def debug(self, msg, *args, **kwargs):
#         """
#         Logs a debug-level message.
#         """
#         self._mapped_log(logging.DEBUG, msg, *args, **kwargs)
#
#     def info(self, msg, *args, **kwargs):
#         """
#         Logs an info-level message.
#         """
#         self._mapped_log(logging.INFO, msg, *args, **kwargs)
#
#     def warning(self, msg, *args, **kwargs):
#         """
#         Logs a warning-level message.
#         """
#         self._mapped_log(logging.WARNING, msg, *args, **kwargs)
#
#     def error(self, msg, *args, **kwargs):
#         """
#         Logs an error-level message.
#         """
#         self._mapped_log(logging.ERROR, msg, *args, **kwargs)
#
#     def critical(self, msg, *args, **kwargs):
#         """
#         Logs a critical-level message.
#         """
#         self._mapped_log(logging.CRITICAL, msg, *args, **kwargs)
#
#     def important(self, msg, *args, **kwargs):
#         """
#         Logs an important-level message.
#         """
#         self._mapped_log(LOG_LEVELS['IMPORTANT'], msg, *args, **kwargs)
#
#     def setLevel(self, level):
#         """
#         Sets the logging level for this logger.
#
#         Parameters:
#             level (str or int): The logging level to set. If a string, it must be one of the keys in LOG_LEVELS.
#         """
#         if isinstance(level, str):
#             if level not in LOG_LEVELS:
#                 raise ValueError('Invalid log level')
#             numeric_level = LOG_LEVELS[level]
#         elif isinstance(level, int):
#             numeric_level = level
#         else:
#             raise ValueError('Level must be a string or integer')
#
#         self._logger.setLevel(numeric_level)
#
#     @property
#     def level(self):
#         """
#         Retrieves the current logging level from the underlying logger.
#         """
#         return self._logger.level
#
#     def switchLoggingLevel(self, level_from, level_to):
#         """
#         Remaps log calls from level_from to level_to for this logger.
#
#         For example, downgrade all INFO calls to DEBUG so that calls to .info()
#         will be emitted as DEBUG-level logs.
#
#         Parameters:
#             level_from (str or int): The original logging level name (e.g. "INFO")
#                                      or numeric value to remap.
#             level_to (str or int): The new logging level name or numeric value.
#         """
#         # Convert level_from to numeric
#         if isinstance(level_from, str):
#             lvl_from = LOG_LEVELS.get(level_from.upper())
#             if lvl_from is None:
#                 raise ValueError(f"Invalid level_from: {level_from}")
#         elif isinstance(level_from, int):
#             lvl_from = level_from
#         else:
#             raise ValueError("level_from must be a string or integer")
#
#         # Convert level_to to numeric
#         if isinstance(level_to, str):
#             lvl_to = LOG_LEVELS.get(level_to.upper())
#             if lvl_to is None:
#                 raise ValueError(f"Invalid level_to: {level_to}")
#         elif isinstance(level_to, int):
#             lvl_to = level_to
#         else:
#             raise ValueError("level_to must be a string or integer")
#
#         # Save the mapping
#         self._level_map[lvl_from] = lvl_to
#
#
# if __name__ == '__main__':
#     logger = Logger('test', 'DEBUG')
#     setLoggingSettings(show_log_file=False, show_log_level=False)
#
#     # Example: remap INFO to DEBUG
#     logger.switchLoggingLevel('INFO', 'DEBUG')
#
#     logger.info('This is an info message (will be logged as DEBUG)')
#     logger.warning('This is a warning message')
#     logger.debug('This is a debug message')
#     logger.important('This is an important message')
#     logger.error('This is an error message')
#     logger.critical('This is a critical message')


"""
Logging utilities module.

This module provides functionality for logging to the console and files,
as well as the ability to redirect log messages through custom callables.
Users can enable a redirection and choose whether to redirect all logs or only
those logs that would also be output to the console (i.e. those that meet the
current log level threshold).

New in this version:
- Module-wide buffer of recent logs (time-pruned and size-limited).
- addLogRedirection(..., past_time=seconds) to immediately replay buffered logs
  from the last `seconds` seconds into the provided redirection function, subject
  to the same filtering as live redirection (redirect_all / minimum_level and the
  logger's current level).
"""

import inspect
import logging
import os
import atexit
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Callable

from core.utils import colors
from core.utils import string_utils as string_utils

# Define mapping for log level names to numeric levels
LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
    "IMPORTANT": 25,
}

# Central color map by numeric log level (importable from other modules)
LOGGING_COLORS = {
    logging.DEBUG: colors.DARK_GREY,
    LOG_LEVELS['IMPORTANT']: colors.MEDIUM_GREEN,
    logging.INFO: colors.WHITE,
    logging.WARNING: colors.MEDIUM_ORANGE,
    logging.ERROR: colors.RED,
    logging.CRITICAL: colors.RED,
}

logging.addLevelName(LOG_LEVELS["IMPORTANT"], "IMPORTANT")

# List to store all enabled redirections
redirections = []

# Global variable to manage file logging state
log_files: dict = {}

# Global dictionary to store custom Logger instances to prevent duplicates.
custom_loggers = {}

_show_log_file = False
_show_log_level = False

# === MODULE-WIDE LOG BUFFER (for replay to new redirections) ====================
# Each buffered item is a dict:
# {
#   't': datetime,
#   'entry': str,          # formatted single-line entry used for files/redirection
#   'msg': str,            # original log message passed by user
#   'logger_name': str,    # Logger.name
#   'level': int           # numeric level
# }
_log_buffer = []
_buffer_lock = threading.Lock()

# Defaults: keep up to 10,000 entries and up to 10 minutes of history (whichever prunes first)
_buffer_max_items = 10000
_buffer_max_seconds = 600  # 10 minutes


def setLogBufferLimits(max_items: int | None = None, max_seconds: int | None = None):
    """
    Configure limits for the in-memory log buffer used to replay past logs.

    Parameters:
        max_items (int | None): Maximum number of log records to keep in memory.
                                If None, leaves unchanged.
        max_seconds (int | None): Maximum age (in seconds) of records to retain.
                                  If None, leaves unchanged.
    """
    global _buffer_max_items, _buffer_max_seconds
    if max_items is not None and max_items > 0:
        _buffer_max_items = max_items
    if max_seconds is not None and max_seconds >= 0:
        _buffer_max_seconds = max_seconds


def _buffer_prune_locked(now: datetime | None = None):
    """
    Prune the buffer by age and size. Caller must hold _buffer_lock.
    """
    global _log_buffer
    if now is None:
        now = datetime.now()

    # Age-based prune
    if _buffer_max_seconds >= 0:
        cutoff = now - timedelta(seconds=_buffer_max_seconds)
        # Find first index >= cutoff
        first_valid_idx = 0
        for i, item in enumerate(_log_buffer):
            if item['t'] >= cutoff:
                first_valid_idx = i
                break
        else:
            # All entries older than cutoff
            _log_buffer = []
            return
        if first_valid_idx > 0:
            _log_buffer = _log_buffer[first_valid_idx:]

    # Size-based prune
    if _buffer_max_items > 0 and len(_log_buffer) > _buffer_max_items:
        _log_buffer = _log_buffer[-_buffer_max_items:]


# === SET LOGGING SETTINGS =============================================================================================
def setLoggingSettings(show_log_file=False, show_log_level=False):
    """
    Update global formatting flags and reconfigure all existing Logger instances
    so they pick up the new settings immediately.
    """
    global _show_log_file, _show_log_level
    _show_log_file = show_log_file
    _show_log_level = show_log_level

    # Re-apply formatter settings on every existing Logger
    for lg in custom_loggers.values():
        if hasattr(lg, '_apply_formatter_settings'):
            lg._apply_formatter_settings()


@atexit.register
def cleanup(*args, **kwargs):
    """
    Closes all open log files when the program exits.
    """
    global log_files
    for filename, data in log_files.items():
        data['file'].close()


@dataclass
class LogRedirection:
    """
    Class representing a log redirection.

    Attributes:
        func (callable): The function to call for redirection.
        minium_level (int): Minimum level a message must have to be redirected (if not redirect_all).
        redirect_all (bool): If True, redirect all logs; otherwise respect levels.
    """
    func: Callable
    minium_level: int = logging.NOTSET
    redirect_all: bool = False


def addLogRedirection(func, redirect_all: bool = False, minimum_level: int | str = logging.NOTSET,
                      past_time: float | int | None = None):
    """
    Enables a log redirection.

    Parameters:
        func (callable): The function to be called for log redirection. Signature:
                         func(formatted_entry: str, raw_message: str, logger: 'Logger', level: int)
        redirect_all (bool): If True, redirect all log messages. If False, only
                             redirect logs that meet or exceed the console log level.
        minimum_level (int | str): Minimum log level to redirect (applies only if not redirect_all).
        past_time (float | int | None): If provided and > 0, immediately feed this redirection
                                        with buffered logs from the last `past_time` seconds that
                                        match this redirection's criteria.
    """
    global redirections
    if isinstance(minimum_level, str):
        minimum_level = LOG_LEVELS.get(minimum_level, logging.NOTSET)

    redir = LogRedirection(func, minium_level=minimum_level, redirect_all=redirect_all)
    redirections.append(redir)

    # If asked, replay recent buffered logs into this redirection
    if past_time is not None and past_time > 0:
        now = datetime.now()
        earliest = now - timedelta(seconds=float(past_time))
        with _buffer_lock:
            # prune first to keep things tight
            _buffer_prune_locked(now=now)
            # Gather matching items (preserve chronological order)
            snapshot = [item for item in _log_buffer if item['t'] >= earliest]

        # Emit to this redirection if criteria match
        for item in snapshot:
            level = item['level']
            logger_obj = custom_loggers.get(item['logger_name'])
            if logger_obj is None:
                # If the original custom Logger no longer exists, skip
                continue
            if redir.redirect_all or (level >= logger_obj.level and level >= redir.minium_level):
                # Call with the same signature as live redirection
                redir.func(item['entry'], item['msg'], logger_obj, level)


def removeLogRedirection(func):
    """
    Disables a previously enabled log redirection.

    Parameters:
        func (callable): The redirection function to disable.
    """
    global redirections
    redirections[:] = [redir for redir in redirections if redir.func != func]


def enable_file_logging(filename, path='./', custom_header: str = '', log_all_levels=False):
    """
    Enables file logging. Creates a log file with the name "<filename>_yyyymmdd_hhmmss.log".

    Parameters:
        filename (str): The base name of the log file.
        path (str): Directory where the log file will be saved.
        custom_header (str): Optional header information to include in the log.
        log_all_levels (bool): If True, all logs are written to the file regardless of level.
    """
    global log_files

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{path}/{filename}_{timestamp}.log"

    try:
        log_file = open(log_filename, 'a')
        log_file.write("BILBO Log\n")
        log_file.write(f"Time {timestamp}: {custom_header}\n")
        log_file.write("YYYY-MM-DD_hh-mm-ss-ms \t Logger \t Level \t Log\n")
        log_files[filename] = {
            'file': log_file,
            'all_levels': log_all_levels,
            'lock': threading.Lock()
        }
        print(f"File logging enabled. Logging to file: {log_filename}")
    except IOError as e:
        print(f"Failed to open log file {log_filename}: {e}")


def stop_file_logging(filename=None):
    """
    Stops file logging and closes the log file(s).

    Parameters:
        filename (str, optional): If provided, only the log file with this base name is stopped.
                                  Otherwise, all log files are closed.
    """
    global log_files

    if filename is not None:
        if filename in log_files:
            log_files[filename]['file'].close()
            log_files.pop(filename)
            print(f"File logging stopped for {filename}.")
    else:
        for filename, data in log_files.items():
            data['file'].close()
            print(f"File logging stopped for {filename}.")
        log_files = {}


def handle_log(log, logger: 'Logger', level):
    """
    Handles a log message by formatting it and sending it to any enabled redirections and file loggers.

    Parameters:
        log (str): The log message.
        logger (Logger): The logger instance issuing the log.
        level (int or str): The numeric or string log level.
    """
    global log_files

    # Convert level from string to numeric value if necessary
    if isinstance(level, str):
        level = LOG_LEVELS.get(level, logging.NOTSET)

    # Create reverse mapping to get level name from numeric level
    reversed_levels = {v: k for k, v in LOG_LEVELS.items()}
    level_name = reversed_levels.get(level, "NOTSET")

    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d:%H-%M-%S-%f")[:-3]
    log_entry = f"{current_time}\t{logger.name}\t{level_name}\t{log}\n"

    # Buffer the entry for potential future replay
    with _buffer_lock:
        _log_buffer.append({
            't': now,
            'entry': log_entry,
            'msg': log,
            'logger_name': logger.name,
            'level': level
        })
        _buffer_prune_locked(now=now)

    # Process redirections: if a redirection is set to redirect_all, send all logs;
    # otherwise, only send logs that meet or exceed the logger's threshold.
    for redir in redirections:
        if redir.redirect_all or (level >= logger.level and level >= redir.minium_level):
            redir.func(log_entry, log, logger, level)

    # Write log entries to file(s) if file logging is enabled
    try:
        for filename, log_file_data in log_files.items():
            with log_file_data['lock']:
                if level >= logger.level or log_file_data['all_levels']:
                    log_file_data['file'].write(log_entry)
                    log_file_data['file'].flush()
    except IOError as e:
        print(f"Failed to write to log file: {e}")


def disableAllOtherLoggers(module_name=None):
    """
    Disables all loggers except the one associated with the provided module name.

    Parameters:
        module_name (str, optional): The module name whose logger should remain enabled.
    """
    for log_name, log_obj in logging.Logger.manager.loggerDict.items():
        if log_name != module_name:
            log_obj.disabled = True


def disableLoggers(loggers: list):
    """
    Disables loggers whose names are in the provided list.

    Parameters:
        loggers (list): A list of logger names to disable.
    """
    for log_name, log_obj in logging.Logger.manager.loggerDict.items():
        if log_name in loggers:
            log_obj.disabled = True


def getLoggerByName(logger_name: str):
    """
    Retrieves a logger by its name.

    Parameters:
        logger_name (str): The name of the logger to retrieve.

    Returns:
        Logger or None: The logger object if found, otherwise None.
    """
    for log_name, log_obj in logging.Logger.manager.loggerDict.items():
        if log_name == logger_name:
            return log_obj
    return None


def setLoggerLevel(logger, level=logging.DEBUG):
    """
    Sets the logging level for one or more loggers.

    Parameters:
        logger (str, list, or list of tuples): The logger name(s) or a list of tuples
                                               (logger_name, level) to set levels.
        level (int or str): The logging level to set (used if logger is a single name or list of names).
    """
    # Convert level if it's a string.
    if isinstance(level, str):
        level = LOG_LEVELS.get(level, logging.NOTSET)

    if isinstance(logger, str):
        l = logging.getLogger(logger)
        l.setLevel(level)
    elif isinstance(logger, list) and all(isinstance(l, tuple) for l in logger):
        for logger_tuple in logger:
            logger_name, lvl = logger_tuple
            if isinstance(lvl, str):
                lvl = LOG_LEVELS.get(lvl, logging.NOTSET)
            l = getLoggerByName(logger_name)
            if l is not None:
                l.setLevel(lvl)
    elif isinstance(logger, list) and all(isinstance(l, str) for l in logger):
        for logger_name in logger:
            logger_object = getLoggerByName(logger_name)
            if logger_object is not None:
                logger_object.setLevel(level)


class CustomFormatter(logging.Formatter):
    """
    Custom log formatter that applies color formatting based on the log level.
    """
    _filename: str | None

    def __init__(self):
        super().__init__()

        # Remove any existing handlers from the root logger
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        if _show_log_level:
            if _show_log_file:
                self.str_format = "%(asctime)s.%(msecs)03d %(levelname)-12s  %(name)-20s %(filename)-30s  %(message)s"
            else:
                self.str_format = "%(asctime)s.%(msecs)03d %(levelname)-12s  %(name)-20s  %(message)s"
        else:
            if _show_log_file:
                self.str_format = "%(asctime)s.%(msecs)03d %(name)-20s %(filename)-30s  %(message)s"
            else:
                self.str_format = "%(asctime)s.%(msecs)03d %(name)-20s  %(message)s"

        self._filename = None

        # Build per-level formats from RAW colors by escaping here
        self.FORMATS = {
            lvl: string_utils.escapeCode(raw_color) + self.str_format + string_utils.reset
            for lvl, raw_color in LOGGING_COLORS.items()
        }
        self.DEFAULT_FORMAT = self.str_format

    def setFileName(self, filename):
        """
        Sets the filename to be included in log records.

        Parameters:
            filename (str): The filename to display in the log.
        """
        self._filename = filename

    def format(self, record):
        """
        Formats the log record with the appropriate colors and formatting.
        """
        log_fmt = self.FORMATS.get(record.levelno, self.DEFAULT_FORMAT)
        formatter = logging.Formatter(log_fmt, "%H:%M:%S")
        record.filename = self._filename
        record.levelname = f'[{record.levelname}]'
        record.filename = f'({record.filename})'
        record.name = f'[{record.name}]'
        record.filename = f'{record.filename}:'
        return formatter.format(record)


class Logger:
    """
    Custom Logger class that wraps Python's standard logging.Logger.
    Provides methods for colored console output, file logging, log redirection,
    and the ability to remap log levels on the fly.
    """
    _logger: logging.Logger
    name: str
    color: list

    def __new__(cls, name, *args, **kwargs):
        global custom_loggers
        if name in custom_loggers:
            return custom_loggers[name]
        instance = super(Logger, cls).__new__(cls)
        custom_loggers[name] = instance
        return instance

    def __init__(self, name, level: str = 'INFO', info_color=colors.LIGHT_GREY, background=None, color=None):
        # Ensure mapping dict exists even if re-initializing existing logger
        if not hasattr(self, '_level_map'):
            self._level_map = {}

        self.name = name
        self._logger = logging.getLogger(name)
        # Check if the underlying logger has already been configured.
        if getattr(self._logger, '_custom_initialized', False):
            self.setLevel(level)
            return

        self.setLevel(level)
        self.color = color

        # Convert RGB tuple/list to 256-color escape if necessary.
        if isinstance(info_color, tuple) or isinstance(info_color, list):
            info_color = string_utils.rgb_to_256color_escape(info_color, background)

        # Create a new formatter and add a stream handler only once.
        self.formatter = CustomFormatter()
        self.stream_handler = logging.StreamHandler()
        self.stream_handler.setFormatter(self.formatter)
        self._logger.addHandler(self.stream_handler)
        self._logger.propagate = False
        self._logger._custom_initialized = True

    def _apply_formatter_settings(self):
        """
        Re-create the CustomFormatter (respecting the current
        _show_log_file/_show_log_level flags) and re-attach it
        to the stream handler.
        """
        new_fmt = CustomFormatter()
        self.formatter = new_fmt
        self.stream_handler.setFormatter(new_fmt)

    @staticmethod
    def getFileName():
        """
        Retrieves the filename of the caller.

        Returns:
            str: The base name of the caller's file.
        """
        frame = inspect.currentframe().f_back.f_back
        filename = frame.f_globals.get('__file__', 'unknown')
        return os.path.basename(filename)

    def _mapped_log(self, original_level, msg, *args, **kwargs):
        """
        Internal helper to remap a log call from original_level to a mapped
        level (if configured), then emit the log and handle redirections/file output.
        """
        self.formatter.setFileName(self.getFileName())
        # Determine mapped level (defaults to the original)
        mapped_level = self._level_map.get(original_level, original_level)
        # Emit via underlying logger
        self._logger.log(mapped_level, msg, *args, **kwargs)
        # Handle redirections and file output
        handle_log(msg, logger=self, level=mapped_level)

    def debug(self, msg, *args, **kwargs):
        """
        Logs a debug-level message.
        """
        self._mapped_log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """
        Logs an info-level message.
        """
        self._mapped_log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """
        Logs a warning-level message.
        """
        self._mapped_log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """
        Logs an error-level message.
        """
        self._mapped_log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """
        Logs a critical-level message.
        """
        self._mapped_log(logging.CRITICAL, msg, *args, **kwargs)

    def important(self, msg, *args, **kwargs):
        """
        Logs an important-level message.
        """
        self._mapped_log(LOG_LEVELS['IMPORTANT'], msg, *args, **kwargs)

    def setLevel(self, level):
        """
        Sets the logging level for this logger.

        Parameters:
            level (str or int): The logging level to set. If a string, it must be one of the keys in LOG_LEVELS.
        """
        if isinstance(level, str):
            if level not in LOG_LEVELS:
                raise ValueError('Invalid log level')
            numeric_level = LOG_LEVELS[level]
        elif isinstance(level, int):
            numeric_level = level
        else:
            raise ValueError('Level must be a string or integer')

        self._logger.setLevel(numeric_level)

    @property
    def level(self):
        """
        Retrieves the current logging level from the underlying logger.
        """
        return self._logger.level

    def switchLoggingLevel(self, level_from, level_to):
        """
        Remaps log calls from level_from to level_to for this logger.

        For example, downgrade all INFO calls to DEBUG so that calls to .info()
        will be emitted as DEBUG-level logs.

        Parameters:
            level_from (str or int): The original logging level name (e.g. "INFO")
                                     or numeric value to remap.
            level_to (str or int): The new logging level name or numeric value.
        """
        # Convert level_from to numeric
        if isinstance(level_from, str):
            lvl_from = LOG_LEVELS.get(level_from.upper())
            if lvl_from is None:
                raise ValueError(f"Invalid level_from: {level_from}")
        elif isinstance(level_from, int):
            lvl_from = level_from
        else:
            raise ValueError("level_from must be a string or integer")

        # Convert level_to to numeric
        if isinstance(level_to, str):
            lvl_to = LOG_LEVELS.get(level_to.upper())
            if lvl_to is None:
                raise ValueError(f"Invalid level_to: {level_to}")
        elif isinstance(level_to, int):
            lvl_to = level_to
        else:
            raise ValueError("level_to must be a string or integer")

        # Save the mapping
        self._level_map[lvl_from] = lvl_to


if __name__ == '__main__':
    logger = Logger('test', 'DEBUG')
    setLoggingSettings(show_log_file=False, show_log_level=False)

    # Example: remap INFO to DEBUG
    logger.switchLoggingLevel('INFO', 'DEBUG')

    logger.info('This is an info message (will be logged as DEBUG)')
    logger.warning('This is a warning message')
    logger.debug('This is a debug message')
    logger.important('This is an important message')
    logger.error('This is an error message')
    logger.critical('This is a critical message')
