import logging
import os
import tempfile
from importlib import reload

import pytest

import src.logging_config as logging_config


def _reset_logging():
    # Remove all handlers so basicConfig can reconfigure
    for h in list(logging.root.handlers):
        logging.root.removeHandler(h)
    logging.root.setLevel(logging.NOTSET)


def test_logging_level_critical_when_level_0(monkeypatch):
    _reset_logging()
    fd, log_path = tempfile.mkstemp(prefix="crit_", suffix=".log")
    os.close(fd)
    monkeypatch.setenv("LOG_FILE", log_path)
    monkeypatch.setenv("LOG_LEVEL", "0")
    reload(logging_config)
    logging_config.setup_logging()
    try:
        assert logging.getLogger().level == logging.CRITICAL
    finally:
        for h in list(logging.root.handlers):
            h.close()
        os.remove(log_path)


def test_logging_level_info_when_level_1(monkeypatch):
    _reset_logging()
    fd, log_path = tempfile.mkstemp(prefix="info_", suffix=".log")
    os.close(fd)
    monkeypatch.setenv("LOG_FILE", log_path)
    monkeypatch.setenv("LOG_LEVEL", "1")
    reload(logging_config)
    logging_config.setup_logging()
    try:
        assert logging.getLogger().level == logging.INFO
    finally:
        for h in list(logging.root.handlers):
            h.close()
        os.remove(log_path)


def test_logging_level_debug_when_level_other(monkeypatch):
    _reset_logging()
    fd, log_path = tempfile.mkstemp(prefix="debug_", suffix=".log")
    os.close(fd)
    monkeypatch.setenv("LOG_FILE", log_path)
    monkeypatch.setenv("LOG_LEVEL", "2")
    reload(logging_config)
    logging_config.setup_logging()
    try:
        assert logging.getLogger().level == logging.DEBUG
    finally:
        for h in list(logging.root.handlers):
            h.close()
        os.remove(log_path)


def test_logging_writes_to_file(monkeypatch):
    _reset_logging()
    fd, log_path = tempfile.mkstemp(prefix="write_", suffix=".log")
    os.close(fd)
    monkeypatch.setenv("LOG_FILE", log_path)
    monkeypatch.setenv("LOG_LEVEL", "2")
    reload(logging_config)
    logging_config.setup_logging()
    logging.info("Hello world")
    for h in list(logging.root.handlers):
        h.flush()
    with open(log_path, "r", encoding="utf-8") as f:
        contents = f.read()
    try:
        assert "Hello world" in contents
    finally:
        for h in list(logging.root.handlers):
            h.close()
        os.remove(log_path)
