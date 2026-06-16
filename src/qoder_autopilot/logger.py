"""
Qoder Autopilot — Logger
==========================
Colored, structured logging with per-account context tags for parallel mode.
Zero extra dependencies — uses ANSI escape codes directly.

Usage:
    from qoder_autopilot.logger import log, log_ok, log_err, log_step, log_warn
    from qoder_autopilot.logger import set_account_tag, get_account_tag
    from qoder_autopilot.logger import set_log_file, close_log_file
"""

import contextvars
import re
import sys
from datetime import datetime

# ── ANSI Colors ───────────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_COLORS = {
    "reset": _RESET,
    "bold": _BOLD,
    "dim": _DIM,
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
}

# Level → (color, label)
_LEVELS: dict[str, tuple[str, str]] = {
    "DEBUG": ("gray", "DBG"),
    "INFO": ("white", "INF"),
    "OK": ("green", " OK"),
    "WARN": ("yellow", "WRN"),
    "ERROR": ("red", "ERR"),
    "STEP": ("cyan", "STP"),
}

# Context variable for parallel mode account labeling
_acct_tag: contextvars.ContextVar[str] = contextvars.ContextVar("acct_tag", default="")

# Whether to use colors (auto-detect terminal)
_use_colors: bool = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

# Verbosity: 0=quiet, 1=normal (default), 2=verbose
_verbosity: int = 1

# Log file handle (F6)
_log_file = None
_ansi_re = re.compile(r"\033\[[0-9;]*m")


def set_verbosity(level: int) -> None:
    """Set logging verbosity. 0=quiet (errors only), 1=normal, 2=verbose (debug)."""
    global _verbosity  # noqa: PLW0603
    _verbosity = level


def get_verbosity() -> int:
    """Get current verbosity level."""
    return _verbosity


def set_log_file(path: str):
    """Enable writing all log output to a file (in addition to terminal).

    Args:
        path: File path to write logs to.

    Returns:
        The opened file handle.
    """
    global _log_file  # noqa: PLW0603
    _log_file = open(path, "a", encoding="utf-8")  # noqa: SIM115
    return _log_file


def close_log_file() -> None:
    """Close the log file handle if open."""
    global _log_file  # noqa: PLW0603
    if _log_file:
        _log_file.close()
        _log_file = None


def _c(color: str, text: str) -> str:
    """Wrap text in ANSI color codes (no-op if colors disabled)."""
    if not _use_colors:
        return text
    return f"{_COLORS.get(color, '')}{text}{_RESET}"


# ── Public API ────────────────────────────────────────────────────────────


def log(
    msg: str,
    level: str = "INFO",
    acct: str | None = None,
) -> None:
    """Log a message with timestamp, level badge, and optional account tag.

    Args:
        msg: The message to log.
        level: Log level (DEBUG, INFO, OK, WARN, ERROR, STEP).
        acct: Override account tag for this message.
    """
    ts = datetime.now().strftime("%H:%M:%S")
    color, label = _LEVELS.get(level, ("white", level[:3]))

    tag = acct if acct else _acct_tag.get()
    tag_str = _c("bold", f"[{tag}]") + " " if tag else ""

    # Respect verbosity
    if _verbosity == 0 and level not in ("ERROR", "WARN"):
        return
    if _verbosity < 2 and level == "DEBUG":
        return

    timestamp = _c("gray", ts)
    badge = _c(color, f"{_BOLD}{label}")
    message = _c(color, msg) if level in ("ERROR", "WARN") else msg

    output = f"{timestamp} {badge} {tag_str}{message}"
    print(output)

    # F6: Write to log file (strip ANSI codes)
    if _log_file:
        plain_ts = ts
        plain_tag = f"[{tag}] " if tag else ""
        plain_msg = _ansi_re.sub("", msg)
        _log_file.write(f"{plain_ts} {label} {plain_tag}{plain_msg}\n")
        _log_file.flush()


def log_ok(msg: str) -> None:
    """Log a success message (green ✅)."""
    log(f"✅ {msg}", "OK")


def log_err(msg: str) -> None:
    """Log an error message (red ❌)."""
    log(f"❌ {msg}", "ERROR")


def log_warn(msg: str) -> None:
    """Log a warning message (yellow ⚠️)."""
    log(f"⚠️  {msg}", "WARN")


def log_step(step: int, total: int, msg: str) -> None:
    """Log a step in a multi-step process (cyan 📋)."""
    log(f"📋 Step {step}/{total}: {msg}", "STEP")


def log_debug(msg: str) -> None:
    """Log a debug message (gray, dim)."""
    log(msg, "DEBUG")


def set_account_tag(tag: str) -> None:
    """Set the account tag for all subsequent log calls in this async context."""
    _acct_tag.set(tag)


def get_account_tag() -> str:
    """Get the current account tag."""
    return _acct_tag.get()
