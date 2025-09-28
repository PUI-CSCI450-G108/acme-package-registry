import logging

import pytest


def _reset_logging_state():
    for h in list(logging.root.handlers):
        try:
            h.flush()
        except Exception:
            pass
        logging.root.removeHandler(h)
    logging.root.setLevel(logging.NOTSET)


@pytest.fixture(autouse=True)
def isolate_logging():
    _reset_logging_state()
    yield
    _reset_logging_state()
