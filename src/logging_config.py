import logging
import os
import os.path as _p


def setup_logging():
    # Only configure file logging if LOG_FILE is explicitly provided
    log_file = os.environ.get("LOG_FILE")
    if not log_file:
        # no file logging requested
        return
    # Must point to an existing file
    if not _p.exists(log_file):
        # Let caller decide how to handle (process_cmd exits with 1)
        raise FileNotFoundError(f"LOG_FILE not found: {log_file}")
    log_level = int(os.environ.get("LOG_LEVEL", "0"))
    if log_level == 0:
        level = logging.CRITICAL
    elif log_level == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(
        filename=log_file,
        filemode="a",
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )
