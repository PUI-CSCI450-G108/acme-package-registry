"""Utility script to exercise structured logging configuration.

This script invokes ``setup_logging`` and emits a sample JSON log entry via
``lambda_handlers.utils.log_event``.  It is designed to work uniformly across
Windows ``cmd.exe`` and POSIX shells, so users can quickly confirm the logging
pipeline without worrying about shell-specific syntax.
"""
from __future__ import annotations

import argparse
import os
from types import SimpleNamespace
from typing import Optional

from lambda_handlers import utils
from src.logging_config import setup_logging


def _build_event(user: Optional[str], endpoint: Optional[str], request_id: Optional[str]):
    request_context = {}
    if request_id:
        request_context["requestId"] = request_id
    http_context = {}
    if endpoint:
        http_context["path"] = endpoint
    if http_context:
        request_context["http"] = http_context
    if user:
        request_context.setdefault("identity", {})["user"] = user
    if request_context:
        return {"requestContext": request_context}
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit a sample structured log entry")
    parser.add_argument("message", nargs="?", default="Structured logging smoke test")
    parser.add_argument("--log-file", dest="log_file", help="Target log file path")
    parser.add_argument(
        "--log-level",
        dest="log_level",
        type=int,
        choices=[0, 1, 2],
        help="Numeric log level matching LOG_LEVEL semantics",
    )
    parser.add_argument("--user", dest="user", help="Simulated caller identity")
    parser.add_argument("--endpoint", dest="endpoint", help="Simulated endpoint path")
    parser.add_argument(
        "--request-id",
        dest="request_id",
        help="Request identifier placed into the event context",
    )
    parser.add_argument(
        "--context-id",
        dest="context_id",
        help="aws_request_id used on the synthetic Lambda context",
    )
    parser.add_argument("--model-id", dest="model_id", help="Associated model identifier")
    parser.add_argument(
        "--latency",
        dest="latency",
        type=float,
        help="Simulated latency value in seconds",
    )
    parser.add_argument(
        "--status",
        dest="status",
        type=int,
        default=200,
        help="HTTP status code to embed in the log entry",
    )
    parser.add_argument("--error-code", dest="error_code", help="Optional error code")
    parser.add_argument(
        "--level",
        dest="level",
        default="info",
        help="Logging level name (e.g. info, warning, error)",
    )

    args = parser.parse_args()

    if args.log_file:
        os.environ["LOG_FILE"] = args.log_file
    if args.log_level is not None:
        os.environ["LOG_LEVEL"] = str(args.log_level)

    setup_logging()

    event = _build_event(args.user, args.endpoint, args.request_id)
    context_id = args.context_id or args.request_id
    context = SimpleNamespace(aws_request_id=context_id) if context_id else None

    utils.log_event(
        args.level,
        args.message,
        event=event,
        context=context,
        model_id=args.model_id,
        latency=args.latency,
        status=args.status,
        error_code=args.error_code,
    )


if __name__ == "__main__":
    main()
