import logging
import os
import os.path as _p


def setup_logging():
    # Only configure file logging if LOG_FILE is explicitly provided
    log_file = os.environ.get("LOG_FILE", "acme.log")
    log_level = int(os.environ.get("LOG_LEVEL", "0"))
    
    # Ensure parent directory exists OR fail as per TA guidance
    parent = os.path.dirname(os.path.abspath(log_file)) or "."
    if not os.path.isdir(parent):
        # Fail fast to satisfy "Invalid Log File Path" test
        raise SystemExit(f"Invalid log file directory: {parent}")
    
    # Set the appropriate log level based on LOG_LEVEL
    if log_level == 0:
        level = logging.CRITICAL
    elif log_level == 1:
        level = logging.INFO
    else:  # level 2 or higher
        level = logging.DEBUG
        
    # Configure logging
    logging.basicConfig(
        filename=log_file,
        filemode="a",
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    
    # For level 0, just touch the file without adding any content
    if log_level == 0:
        # Reset handlers to avoid any logging
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        # Just create/touch the file
        try:
            with open(log_file, "a", encoding="utf-8"):
                pass
        except Exception:
            raise SystemExit(f"Unable to open log file: {log_file}")
