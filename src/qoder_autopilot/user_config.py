"""
Qoder Autopilot — User Config Manager
=======================================
Persistent user configuration stored in ~/.qoder-autopilot/config.json.

Priority chain (highest → lowest):
    1. Environment variables (QODER_*, .env)
    2. User config (~/.qoder-autopilot/config.json)
    3. Built-in defaults

Usage:
    from qoder_autopilot.user_config import load_user_config, save_user_config

    cfg = load_user_config()
    cfg["worker_url"] = "https://my-worker.example.com"
    save_user_config(cfg)
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".qoder-autopilot"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Keys that users can configure + their descriptions
USER_CONFIGURABLE = {
    "mail_provider": {
        "description": "Temp mail provider: 'cloudflare' or 'moca'",
        "cli_flag": "mail-provider",
        "type": "str",
    },
    "worker_url": {
        "description": "Cloudflare Worker URL for temp email",
        "cli_flag": "worker-url",
        "type": "str",
    },
    "moca_api_key": {
        "description": "Moca Supabase temp mail API key (tmk_xxx)",
        "cli_flag": "moca-api-key",
        "type": "str",
    },
    "moca_base_url": {
        "description": "Moca Supabase temp mail base URL",
        "cli_flag": "moca-base-url",
        "type": "str",
    },
    "ai_api_key": {
        "description": "API key for AI captcha solver (OpenAI-compatible)",
        "cli_flag": "ai-api-key",
        "type": "str",
    },
    "ai_base_url": {
        "description": "OpenAI-compatible API base URL for captcha AI",
        "cli_flag": "ai-base-url",
        "type": "str",
    },
    "ai_model": {
        "description": "AI model name for captcha solving",
        "cli_flag": "ai-model",
        "type": "str",
    },
    "otp_timeout": {
        "description": "Max seconds to wait for OTP email",
        "cli_flag": "otp-timeout",
        "type": "int",
    },
    "captcha_timeout": {
        "description": "Max seconds to wait for manual captcha solve",
        "cli_flag": "captcha-timeout",
        "type": "int",
    },
    "parallel_delay": {
        "description": "Delay between parallel account starts (seconds)",
        "cli_flag": "parallel-delay",
        "type": "int",
    },
    "ninerouter_db": {
        "description": "Path to 9Router SQLite database",
        "cli_flag": "ninerouter-db",
        "type": "str",
    },
}


def load_user_config() -> dict:
    """Load user config from ~/.qoder-autopilot/config.json.

    Returns:
        Dict of user-configured values. Empty dict if file doesn't exist.
    """
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_user_config(cfg: dict) -> Path:
    """Save user config to ~/.qoder-autopilot/config.json.

    Args:
        cfg: Dictionary of config values to save.

    Returns:
        Path to the config file.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Only save known keys
    clean = {k: v for k, v in cfg.items() if k in USER_CONFIGURABLE}

    with open(CONFIG_FILE, "w") as f:
        json.dump(clean, f, indent=2)

    return CONFIG_FILE


def delete_user_config() -> bool:
    """Delete the user config file (reset to defaults).

    Returns:
        True if file was deleted, False if it didn't exist.
    """
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        return True
    return False


def get_user_config_value(key: str) -> str | int | None:
    """Get a single value from user config.

    Args:
        key: Config key name.

    Returns:
        The value, or None if not set.
    """
    cfg = load_user_config()
    return cfg.get(key)


def set_user_config_value(key: str, value: str) -> bool:
    """Set a single value in user config.

    Args:
        key: Config key name (must be in USER_CONFIGURABLE).
        value: Value to set (string, will be cast to correct type).

    Returns:
        True if set successfully, False if key is invalid.
    """
    if key not in USER_CONFIGURABLE:
        return False

    cfg = load_user_config()

    # Cast to correct type
    expected_type = USER_CONFIGURABLE[key]["type"]
    if expected_type == "int":
        try:
            cfg[key] = int(value)
        except ValueError:
            return False
    else:
        cfg[key] = value

    save_user_config(cfg)
    return True
