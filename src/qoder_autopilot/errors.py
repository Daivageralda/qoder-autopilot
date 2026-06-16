"""
Qoder Autopilot — Custom Exceptions
=====================================
Hierarchical exception classes for clean error handling.

Usage:
    from qoder_autopilot.errors import (
        QoderAutopilotError,
        TempMailError,
        CaptchaError,
        RegistrationError,
        OAuthError,
        NineRouterError,
    )

Exception Hierarchy:
    QoderAutopilotError          (base)
    ├── TempMailError            (email generation / inbox)
    ├── CaptchaError             (captcha solving failed)
    │   ├── CaptchaTimeoutError  (manual solve timed out)
    │   └── CaptchaAIFailed      (AI vision failed)
    ├── RegistrationError        (signup flow failed)
    │   ├── OTPTimeoutError      (OTP email not received)
    │   └── FormSubmitError      (form step failed)
    ├── OAuthError               (PKCE / device token)
    │   └── DeviceTokenTimeout   (polling timed out)
    └── NineRouterError          (DB insert failed)
        └── NineRouterDBNotFound (SQLite file missing)
"""


class QoderAutopilotError(Exception):
    """Base exception for all Qoder Autopilot errors."""

    def __init__(self, message: str = "", detail: str = ""):
        self.message = message
        self.detail = detail
        super().__init__(self.format())

    def format(self) -> str:
        if self.detail:
            return f"{self.message} — {self.detail}"
        return self.message


# ── Temp Mail ─────────────────────────────────────────────────────────────

class TempMailError(QoderAutopilotError):
    """Failed to generate email or access inbox."""


# ── Captcha ───────────────────────────────────────────────────────────────

class CaptchaError(QoderAutopilotError):
    """Captcha solving failed."""


class CaptchaTimeoutError(CaptchaError):
    """Manual captcha solve timed out."""

    def __init__(self, timeout: int = 120):
        super().__init__(
            "Captcha solve timed out",
            f"waited {timeout}s for manual solve",
        )


class CaptchaAIFailed(CaptchaError):  # noqa: N818
    """AI vision captcha solving failed."""

    def __init__(self, reason: str = "unknown"):
        super().__init__("AI captcha solver failed", reason)


# ── Registration ──────────────────────────────────────────────────────────

class RegistrationError(QoderAutopilotError):
    """Registration flow failed."""


class OTPTimeoutError(RegistrationError):
    """OTP email not received within timeout."""

    def __init__(self, email: str, timeout: int = 120):
        super().__init__(
            "OTP not received",
            f"no email at {email} within {timeout}s",
        )


class FormSubmitError(RegistrationError):
    """Form submission step failed."""

    def __init__(self, step: str, reason: str = ""):
        super().__init__(f"Form submit failed at: {step}", reason)


# ── OAuth ─────────────────────────────────────────────────────────────────

class OAuthError(QoderAutopilotError):
    """OAuth / PKCE flow error."""


class DeviceTokenTimeout(OAuthError):  # noqa: N818
    """Device token polling timed out."""

    def __init__(self, max_wait: int = 240):
        super().__init__(
            "Device token poll timed out",
            f"waited {max_wait}s for user authorization",
        )


# ── 9Router ───────────────────────────────────────────────────────────────

class NineRouterError(QoderAutopilotError):
    """9Router integration error."""


class NineRouterDBNotFound(NineRouterError):  # noqa: N818
    """9Router SQLite database file not found."""

    def __init__(self, path: str):
        super().__init__(
            "9Router DB not found",
            f"expected at: {path}",
        )
