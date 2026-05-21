# -*- coding: utf-8 -*-
"""Standardized logging configuration for the research toolkit."""

import logging
import sys
from typing import Optional


FORMAT_DETAILED = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
FORMAT_SIMPLE = "%(levelname)-7s %(message)s"


def configure_logging(
    level: int = logging.INFO,
    fmt: str = FORMAT_SIMPLE,
    stream=None,
) -> None:
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)


def verbose() -> None:
    configure_logging(logging.DEBUG, FORMAT_DETAILED)


def quiet() -> None:
    configure_logging(logging.WARNING, FORMAT_SIMPLE)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger(name)
