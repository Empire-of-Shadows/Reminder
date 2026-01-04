import os
import logging
from logging.handlers import RotatingFileHandler


class IndentedFormatter(logging.Formatter):
    """
    Custom logging formatter to place the log message on a new line and indent it.
    """
    def format(self, record):
        # Process the log message using the base formatter
        original_message = super().format(record)

        # Add a newline and indent the log message part
        if ": " in original_message:
            # Split the log parts: 'timestamp [level]:' and 'message'
            parts = original_message.split(": ", 1)
            formatted_message = f"{parts[0]}:\n                         {parts[1]}"
        else:
            formatted_message = original_message  # Fallback if format is unexpected

        return formatted_message


def get_logger(module_name: str, log_dir: str = "logs", level: int = logging.DEBUG) -> logging.Logger:
    """
    Sets up and returns a logger specific to a module.

    :param module_name: The name of the module using the logger (usually `__name__`).
    :param log_dir: The directory where log files are stored.
    :param level: The default logging level (DEBUG by default).
    :return: Configured logger instance.
    """

    # Ensure the logs directory exists
    os.makedirs(log_dir, exist_ok=True)

    # Logger instance
    logger = logging.getLogger(module_name)
    if logger.hasHandlers():  # Avoid adding duplicate handlers
        return logger

    logger.setLevel(level)

    # Create a file handler for rotating logs
    log_file = os.path.join(log_dir, f"{module_name.replace('.', '_')}.log")
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB per log file
        backupCount=3,  # Keep up to 3 old log files
        encoding="utf-8",
    )

    # Use the custom IndentedFormatter
    file_formatter = IndentedFormatter(
        "%(asctime)s [%(levelname)s]: %(message)s"
    )
    file_handler.setFormatter(file_formatter)

    # Add the file handler to the logger
    logger.addHandler(file_handler)

    # Optional: Add a console handler, with the same formatter
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(file_formatter)
    logger.addHandler(console_handler)

    return logger