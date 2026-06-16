"""
Qoder Autopilot — Manual Captcha Solving
==========================================
Pauses the automation and lets the user solve the captcha manually
in the visible browser window. Auto-detects when captcha disappears.
"""

import asyncio
import time

from .. import config
from ..logger import log, log_err, log_ok


async def handle_captcha_manual(page) -> bool:
    """Manual captcha mode: pause, let user solve it, auto-detect completion.

    The browser must be visible (non-headless) for this to work.
    Polls for captcha disappearance every second with a configurable timeout.

    Args:
        page: Playwright/Camoufox page object.

    Returns:
        True if captcha was solved, False on timeout.
    """
    await asyncio.sleep(2)

    has_captcha = await page.evaluate("""() => {
        const sels = ['#aliyunCaptcha-sliding', '.aliyunCaptcha', '#nc_1_wrapper',
                      '.nc-container', 'iframe[src*="captcha"]', '.slide-verify',
                      '[class*="captcha"]', '[id*="captcha"]'];
        for (const s of sels) {
            const el = document.querySelector(s);
            if (el && el.offsetParent !== null) return true;
        }
        return document.querySelectorAll(
            'iframe[src*="captcha"], iframe[src*="aliyun"]'
        ).length > 0;
    }""")

    if not has_captcha:
        log("   ℹ️  No captcha detected")
        return True

    log("")
    log("   ╔══════════════════════════════════════════════════╗")
    log("   ║  🧑 MANUAL CAPTCHA MODE                         ║")
    log("   ║                                                  ║")
    log("   ║  Captcha detected! Please solve it manually      ║")
    log("   ║  in the browser window (slide the puzzle).       ║")
    log("   ║                                                  ║")
    log("   ║  Script will auto-continue once captcha is gone. ║")
    log(f"   ║  Timeout: {config.CAPTCHA_TIMEOUT} seconds.{' ' * 22}║")
    log("   ╚══════════════════════════════════════════════════╝")
    log("")

    # Take screenshot for reference
    config.SCREENSHOTS_DIR.mkdir(exist_ok=True)
    await page.screenshot(
        path=str(config.SCREENSHOTS_DIR / f"manual_captcha_{int(time.time())}.png")
    )

    # Poll until captcha disappears or timeout
    start = time.time()
    last_dot = 0

    while time.time() - start < config.CAPTCHA_TIMEOUT:
        elapsed = int(time.time() - start)

        # Print a status every 5 seconds
        if elapsed // 5 > last_dot:
            last_dot = elapsed // 5
            log(f"   ⏳ Waiting for manual solve... ({elapsed}s)")

        still_present = await page.evaluate("""() => {
            const sels = ['#aliyunCaptcha-sliding-slider', '#aliyunCaptcha-window-float',
                          '#aliyunCaptcha-sliding', '.aliyunCaptcha', '#captcha-element',
                          '#nc_1_wrapper', '.nc-container'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent !== null) return true;
            }
            return false;
        }""")

        if not still_present:
            log_ok(f"Manual captcha solved in {elapsed}s! 🎉")
            return True

        await asyncio.sleep(1)

    log_err(f"Manual captcha timeout ({config.CAPTCHA_TIMEOUT}s) — user didn't solve it")
    await page.screenshot(
        path=str(config.SCREENSHOTS_DIR / "manual_captcha_timeout.png")
    )
    return False
