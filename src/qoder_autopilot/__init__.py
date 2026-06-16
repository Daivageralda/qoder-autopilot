"""
Qoder Autopilot
================
Automated Qoder account registration with anti-detect browser (Camoufox),
captcha solving (AI + OpenCV), and 9Router OAuth device token integration.

Quick start::

    from qoder_autopilot import run_one
    import asyncio

    result = asyncio.run(run_one(manual_captcha=True))
"""

__version__ = "0.6.1"

from .auth.oauth import initiate_device_flow, poll_device_token
from .captcha import CaptchaSolver
from .cli import run_one
from .errors import (
    CaptchaAIFailed,
    CaptchaError,
    CaptchaTimeoutError,
    DeviceTokenTimeout,
    FormSubmitError,
    NineRouterDBNotFound,
    NineRouterError,
    OAuthError,
    OTPTimeoutError,
    QoderAutopilotError,
    RegistrationError,
    TempMailError,
)
from .infra.temp_mail import TempMail
from .register import register_and_verify

__all__ = [
    # Core functions
    "register_and_verify",
    "run_one",
    # Services
    "TempMail",
    "initiate_device_flow",
    "poll_device_token",
    "CaptchaSolver",
    # Exceptions
    "QoderAutopilotError",
    "TempMailError",
    "CaptchaError",
    "CaptchaTimeoutError",
    "CaptchaAIFailed",
    "RegistrationError",
    "OTPTimeoutError",
    "FormSubmitError",
    "OAuthError",
    "DeviceTokenTimeout",
    "NineRouterError",
    "NineRouterDBNotFound",
]
