"""
Qoder Autopilot — Camoufox Browser Launcher
==============================================
Launch and configure Camoufox (anti-detect Firefox fork) browser instances.
Camoufox provides C++-level stealth fingerprinting to bypass bot detection.
"""

import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ..logger import log


@asynccontextmanager
async def launch_browser(
    headless: bool = True,
    window_width: int = 900,
    window_height: int = 600,
    proxy: str | None = None,
) -> AsyncIterator:
    """Launch a Camoufox browser instance with stealth settings.

    Args:
        headless: Run in headless mode (no visible window).
        window_width: Browser window width in pixels.
        window_height: Browser window height in pixels.
        proxy: Proxy URL (e.g. socks5://host:port, http://host:port).

    Yields:
        Camoufox browser context manager.
    """
    from camoufox.async_api import AsyncCamoufox

    os_choice = random.choice(["windows", "macos", "linux"])
    log(f"   🦊 Launching Camoufox (headless={headless}, os={os_choice})...")

    kwargs: dict = {
        "headless": headless,
        "os": os_choice,
        "window": (window_width, window_height),
    }
    if proxy:
        kwargs["proxy"] = {"server": proxy}
        log(f"   🌐 Using proxy: {proxy}")

    async with AsyncCamoufox(**kwargs) as browser:
        yield browser


async def setup_page(page) -> None:
    """Apply standard page setup for stealth and stability.

    - Forces 100% zoom on every page load

    Note: pageerror listener intentionally omitted — Playwright's internal
    handler crashes on Node.js v24+ when pageError.location is undefined.
    Adding our own listener doesn't prevent the internal crash.

    Args:
        page: Playwright/Camoufox page object.
    """

    # Force 100% zoom on every page load
    await page.add_init_script("""() => {
        document.addEventListener('DOMContentLoaded', () => {
            document.body.style.zoom = '100%';
        });
    }""")
