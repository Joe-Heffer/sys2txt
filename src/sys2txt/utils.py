"""Utility functions."""

import logging
import shutil

logger = logging.getLogger(__name__)


def which(cmd: str) -> str:
    """Find command in PATH or raise RuntimeError if not found."""
    path = shutil.which(cmd)
    if not path:
        raise RuntimeError(f"Required command not found: {cmd}. Please install it and try again.")
    logger.debug("Resolved command '%s' to %s", cmd, path)
    return path
