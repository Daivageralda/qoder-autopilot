"""
Qoder Autopilot — Captcha Solver Orchestrator
===============================================
Coordinates captcha detection, solving strategies, and retry logic.

Strategies (in priority order):
    1. AI Vision (if API key configured) — most accurate
    2. OpenCV (always available) — 4-method fallback
    3. Manual (if requested) — user solves in browser

Usage:
    solver = CaptchaSolver(manual=False)
    ok = await solver.solve(page)
"""

import asyncio
import random
import time

from .. import config
from ..logger import log, log_err, log_ok
from .ai_vision import gemini_detect_gap
from .manual import handle_captcha_manual
from .opencv_detect import detect_gap_position
from .slider import slide_puzzle

# CSS selectors for detecting captcha presence
_CAPTCHA_DETECT_SELECTORS = """
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
"""

_CAPTCHA_STILL_SELECTORS = """
    const sels = ['#aliyunCaptcha-sliding-slider', '#aliyunCaptcha-window-float',
                  '#aliyunCaptcha-sliding', '.aliyunCaptcha', '#captcha-element',
                  '#nc_1_wrapper', '.nc-container'];
    for (const s of sels) {
        const el = document.querySelector(s);
        if (el && el.offsetParent !== null) return true;
    }
    return false;
"""


class CaptchaSolver:
    """Orchestrates captcha solving with multiple strategies and retries."""

    def __init__(
        self,
        manual: bool = False,
        use_ai: bool = True,
        max_attempts: int | None = None,
    ):
        self.manual = manual
        self.use_ai = use_ai and bool(config.AI_API_KEY)
        self.max_attempts = max_attempts or config.MAX_CAPTCHA_ATTEMPTS

    async def solve(self, page) -> bool:
        """Detect and solve the captcha on the current page.

        Args:
            page: Playwright/Camoufox page object.

        Returns:
            True if captcha was solved (or not present), False on failure.
        """
        if self.manual:
            return await handle_captcha_manual(page)

        await asyncio.sleep(2)

        # Check if captcha is present
        has_captcha = await page.evaluate(f"() => {{ {_CAPTCHA_DETECT_SELECTORS} }}")
        if not has_captcha:
            log("   ℹ️  No captcha detected")
            return True

        log("   🔒 Captcha detected! Solving...")
        config.SCREENSHOTS_DIR.mkdir(exist_ok=True)
        await page.screenshot(
            path=str(config.SCREENSHOTS_DIR / f"captcha_{int(time.time())}.png")
        )

        tried_positions: list[float] = []

        for attempt in range(self.max_attempts):
            # Wait for captcha image to load
            img_ready = {"ready": False, "src": ""}
            for _ in range(30):  # up to 6 seconds
                img_ready = await page.evaluate("""() => {
                    const bg = document.querySelector('#aliyunCaptcha-img');
                    if (!bg || !bg.src) return {ready: false, src: ''};
                    const isLoaded = bg.src.startsWith('data:')
                        ? bg.complete
                        : (bg.complete && bg.naturalWidth > 0);
                    return {ready: isLoaded, src: bg.src.substring(0, 80)};
                }""")
                if img_ready.get("ready"):
                    break
                await asyncio.sleep(0.2)
            else:
                log(f"   ⚠️ Image not loaded after 6s, src='{img_ready.get('src', 'N/A')}'")
            await asyncio.sleep(0.5)

            # Get track width
            track_w = await page.evaluate("""() => {
                const sels = ['#aliyunCaptcha-sliding-body',
                              '.aliyunCaptcha-sliding-track',
                              '.nc-container .nc_scale', '.slide-verify-track',
                              '[class*="track"]'];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el && el.getBoundingClientRect().width > 50)
                        return el.getBoundingClientRect().width;
                }
                return 300;
            }""")
            if track_w < 50:
                track_w = 300

            # ─── Detect gap position ───
            detected_x = None
            if self.use_ai:
                detected_x = await gemini_detect_gap(page)
            if detected_x is None:
                detected_x = await detect_gap_position(page)

            base = detected_x if detected_x is not None else track_w * 0.6

            # ─── Calculate target with retry offset strategy ───
            if attempt == 0:
                offset = random.uniform(-2, 2)
            elif attempt <= 2:
                offset = random.uniform(-5, 5)
            else:
                offset = (
                    random.choice([-15, -10, -5, 5, 10, 15])
                    + random.uniform(-3, 3)
                )
            target = max(10, min(track_w - 10, base + offset))
            tried_positions.append(target)

            if detected_x is not None:
                log(f"   🎯 Target: {target:.0f}/{track_w:.0f}px")
            else:
                log(f"   🎯 Fallback target: {target:.0f}/{track_w:.0f}px")

            log(f"   🖱️  Attempt {attempt + 1}: sliding {target:.0f}/{track_w:.0f}px")

            # ─── Execute the slide ───
            await slide_puzzle(page, target, track_w)

            # ─── Check if captcha is gone ───
            still = await page.evaluate(f"() => {{ {_CAPTCHA_STILL_SELECTORS} }}")
            if not still:
                log_ok("Captcha solved!")
                return True

            log(f"   ⚠️  Captcha still present (attempt {attempt + 1}/{self.max_attempts})")

        log_err(f"Failed to solve captcha after {self.max_attempts} attempts")
        return False
