"""
Qoder Autopilot — Configuration (pydantic-settings)
=====================================================
Settings loaded with priority chain (highest → lowest):
    1. Environment variables (QODER_*, .env)
    2. User config (~/.qoder-autopilot/config.json)
    3. Built-in defaults

Usage:
    from qoder_autopilot.config import settings      # Settings singleton
    from qoder_autopilot.config import WORKER_URL     # Module-level re-exports

CLI configuration:
    qoder-autopilot config show                       # Show all settings
    qoder-autopilot config set worker-url https://...  # Set a value
    qoder-autopilot config reset                       # Reset to defaults
"""

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .user_config import load_user_config

# ═══════════════════════════════════════════════════════════════════════════════
# PATHS (non-prefixed, resolved at import time)
# ═══════════════════════════════════════════════════════════════════════════════

PACKAGE_DIR = Path(__file__).parent
PROJECT_DIR = PACKAGE_DIR.parent.parent  # src/../.. = project root


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class Settings(BaseSettings):
    """
    Centralized configuration for Qoder Autopilot.

    All fields can be set via environment variables with the QODER_ prefix.
    Falls back to legacy env var names (SUMOPOD_*, WORKER_URL) for backward compat.
    Values are also loaded from .env file if present.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="QODER_",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def _load_user_config(cls) -> dict:
        """Load user config from ~/.qoder-autopilot/config.json."""
        try:
            return load_user_config()
        except Exception:
            return {}

    def __init__(self, **data):
        # Inject user config as base values, but don't override env vars or explicit kwargs
        user_cfg = self._load_user_config()
        for key, value in user_cfg.items():
            # Skip if explicit kwarg provided
            if key in data:
                continue
            # Skip if env var is set (env vars have priority over user config)
            env_key = f"QODER_{key.upper()}"
            if os.environ.get(env_key):
                continue
            data[key] = value
        super().__init__(**data)

    # ── Temp Mail ─────────────────────────────────────────────────────────
    mail_provider: str = Field(
        default="cloudflare",
        description="Temp mail provider: 'cloudflare' or 'moca'",
    )
    worker_url: str = Field(
        default=os.environ.get(
            "WORKER_URL",
            "https://hanzzcreator-mail.daivageralda831.workers.dev",
        ),
        description="Cloudflare Worker URL for temporary email generation",
    )
    moca_api_key: str = Field(
        default="",
        description="Moca Supabase temp mail API key (tmk_xxx)",
    )
    moca_base_url: str = Field(
        default="https://ijrccpgiulrmfpavazsl.supabase.co/functions/v1/temp-mail-api",
        description="Moca Supabase temp mail base URL",
    )

    # ── Qoder URLs (constants, rarely need override) ──────────────────────
    qoder_signup_url: str = Field(
        default="https://qoder.com/users/sign-up",
        description="Qoder sign-up page URL",
    )
    qoder_signin_url: str = Field(
        default="https://qoder.com/users/sign-in",
        description="Qoder sign-in page URL",
    )
    qoder_login_url: str = Field(
        default="https://qoder.com/device/selectAccounts",
        description="Qoder device login URL",
    )
    qoder_device_token_url: str = Field(
        default="https://openapi.qoder.sh/api/v1/deviceToken/poll",
        description="Qoder device token polling endpoint",
    )
    qoder_userinfo_url: str = Field(
        default="https://openapi.qoder.sh/api/v1/userinfo",
        description="Qoder user profile endpoint",
    )

    # ── 9Router Integration ───────────────────────────────────────────────
    ninerouter_url: str = Field(
        default="http://localhost:20128",
        description="9Router dashboard URL",
    )
    ninerouter_password: str = Field(
        default="",
        description="9Router password (optional, not needed for DB insert)",
    )
    ninerouter_db: str = Field(
        default="~/.9router/db/data.sqlite",
        description="Path to 9Router SQLite database",
    )

    # ── AI Captcha (optional) ─────────────────────────────────────────────
    ai_api_key: str = Field(
        default=os.environ.get("SUMOPOD_API_KEY", ""),
        description="API key for AI captcha solver (OpenAI-compatible)",
    )
    ai_base_url: str = Field(
        default=os.environ.get("SUMOPOD_BASE_URL", "https://ai.sumopod.com/v1"),
        description="OpenAI-compatible API base URL",
    )
    ai_model: str = Field(
        default=os.environ.get("SUMOPOD_MODEL", "gemini/gemini-2.5-flash"),
        description="AI model name for captcha solving",
    )

    # ── Behavior ──────────────────────────────────────────────────────────
    captcha_timeout: int = Field(
        default=120,
        description="Max seconds to wait for manual captcha solve",
    )
    otp_timeout: int = Field(
        default=20, description="Max seconds to wait for OTP email"
    )
    max_captcha_attempts: int = Field(
        default=8,
        description="Max automatic captcha solve attempts",
    )
    parallel_delay: int = Field(
        default=30,
        description="Delay between sequential account registrations (seconds)",
    )

    # ── File paths ────────────────────────────────────────────────────────
    screenshots_dir: Path = Field(
        default=Path("screenshots"),
        description="Directory for debug screenshots",
    )
    credentials_file: Path = Field(
        default=Path("qoder_accounts.json"),
        description="JSON file for storing account credentials",
    )

    # ── Computed properties ───────────────────────────────────────────────

    @property
    def has_ai_captcha(self) -> bool:
        """Check if AI captcha solver is configured."""
        return bool(self.ai_api_key)

    @property
    def has_ninerouter(self) -> bool:
        """Check if 9Router DB exists and is accessible."""
        db_path = os.path.expanduser(self.ninerouter_db)
        return os.path.exists(db_path)

    @property
    def ninerouter_db_path(self) -> str:
        """Expanded path to 9Router SQLite database."""
        return os.path.expanduser(self.ninerouter_db)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

settings = Settings()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL RE-EXPORTS (backward compat for existing code)
# ═══════════════════════════════════════════════════════════════════════════════

# Temp Mail
MAIL_PROVIDER = settings.mail_provider
WORKER_URL = settings.worker_url
MOCA_API_KEY = settings.moca_api_key
MOCA_BASE_URL = settings.moca_base_url

# Qoder URLs
QODER_SIGNUP_URL = settings.qoder_signup_url
QODER_SIGNIN_URL = settings.qoder_signin_url
QODER_LOGIN_URL = settings.qoder_login_url
QODER_DEVICE_TOKEN_URL = settings.qoder_device_token_url
QODER_USERINFO_URL = settings.qoder_userinfo_url

# 9Router
NINEROUTER_URL = settings.ninerouter_url
NINEROUTER_PASSWORD = settings.ninerouter_password
NINEROUTER_DB = settings.ninerouter_db_path

# AI Captcha
AI_API_KEY = settings.ai_api_key
AI_BASE_URL = settings.ai_base_url
AI_MODEL = settings.ai_model

# Behavior
CAPTCHA_TIMEOUT = settings.captcha_timeout
OTP_TIMEOUT = settings.otp_timeout
MAX_CAPTCHA_ATTEMPTS = settings.max_captcha_attempts
PARALLEL_DELAY = settings.parallel_delay

# File paths
SCREENSHOTS_DIR = settings.screenshots_dir
CREDENTIALS_FILE = settings.credentials_file


# ── Name Generation ───────────────────────────────
# Handled by Faker (id_ID locale) in identity.py
# These pools are kept as fallback only
FIRST_NAMES = [
    "Raihan", "Ahmad", "Budi", "Dimas", "Eko", "Fajar", "Gilang", "Hadi",
    "Irfan", "Joko", "Kevin", "Lukman", "Muhammad", "Naufal", "Omar",
    "Putra", "Rizky", "Satria", "Taufik", "Umar", "Vino", "Wahyu",
    "Yusuf", "Zaki", "Andi", "Bayu", "Cahya", "Dani", "Elang", "Faris",
]

LAST_NAMES = [
    "Geralda", "Pratama", "Saputra", "Wijaya", "Kurniawan", "Hidayat",
    "Nugraha", "Santoso", "Wibowo", "Permadi", "Ramadhan", "Setiawan",
    "Utama", "Firmansyah", "Gunawan", "Hakim", "Ibrahim", "Jaya",
    "Kusuma", "Lesmana", "Mulyadi", "Nurhadi", "Prasetyo", "Rahman",
]
