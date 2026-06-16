"""
Qoder Autopilot — Registration Flow
======================================
Full multi-step Qoder registration:
    1. Navigate to auth URL (OAuth) or direct sign-up
    2. Fill name + email + ToS (Step 1)
    3. Enter password (Step 2)
    4. Solve captcha (AI / OpenCV / Manual)
    5. Wait for OTP email
    6. Enter OTP
    7. Verify success
"""

import asyncio
import random
import time

from . import config
from .browser.window_tiler import tile_all_camoufox_windows
from .captcha.solver import CaptchaSolver
from .logger import log, log_err, log_ok, log_step
from .otp import extract_otp
from .temp_mail import TempMail


async def register_and_verify(
    page,
    email: str,
    identity: dict,
    auth_url: str | None = None,
    manual_captcha: bool = False,
    acct_num: int = 0,
) -> bool:
    """Full registration flow via OAuth or direct sign-up.

    If auth_url is provided, opens the OAuth URL and clicks 'Sign up'.
    Otherwise navigates directly to the Qoder sign-up page.

    Args:
        page: Playwright/Camoufox page object.
        email: Temporary email address to register with.
        identity: Dict with first_name, last_name, display_name, password.
        auth_url: Optional OAuth auth URL from initiate_device_flow().
        manual_captcha: If True, pause for manual captcha solving.
        acct_num: Account number for logging (parallel mode).

    Returns:
        True if registration was verified, False otherwise.
    """
    config.SCREENSHOTS_DIR.mkdir(exist_ok=True)
    captcha_solver = CaptchaSolver(manual=manual_captcha)

    try:
        # ═══ STEP 0: Navigate ═══
        if auth_url:
            log_step(1, 7, "Opening OAuth auth URL...")
            await page.goto(auth_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(0.8)
            tile_all_camoufox_windows()
            # Click "Sign up" link on the sign-in page
            log("   🔗 Clicking 'Sign up' link...")
            try:
                signup_link = page.locator(
                    'a:has-text("Sign up"), a[href*="sign-up"]'
                ).first
                await signup_link.click(timeout=5000)
            except Exception:
                await page.evaluate("""() => {
                    const links = document.querySelectorAll('a');
                    for (const a of links) {
                        if (a.textContent.trim().toLowerCase().includes('sign up')) {
                            a.click(); return true;
                        }
                    }
                }""")
            await asyncio.sleep(1)

            # Verify we're on sign-up page, if not navigate directly
            current_url = page.url
            if "sign-up" not in current_url:
                log("   ⚠️ Still on sign-in page — navigating directly to sign-up...")
                # Swap sign-in → sign-up in the URL, preserve all params
                signup_url = auth_url.replace("/users/sign-in", "/users/sign-up")
                await page.goto(signup_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(0.5)
        else:
            log_step(1, 7, "Opening Qoder sign-up...")
            await page.goto(
                config.QODER_SIGNUP_URL,
                wait_until="networkidle",
                timeout=30000,
            )
            await asyncio.sleep(0.8)
            tile_all_camoufox_windows()

        # ═══ STEP 1: Name + Email + ToS ═══
        log_step(2, 7, f"Step 1 — Filling: {identity['display_name']} / {email}")
        await asyncio.sleep(0.3)

        # Scroll to form to ensure it's in viewport
        try:
            await page.locator("#basic_firstName").first.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            # Fallback: scroll via JS
            await page.evaluate("() => window.scrollTo(0, 0)")

        for selector, value in [
            ("#basic_firstName", identity["first_name"]),
            ("#basic_lastName", identity["last_name"]),
            ("#basic_email", email),
        ]:
            inp = page.locator(selector).first
            await inp.scroll_into_view_if_needed()
            await inp.fill(value)

        # ToS checkbox
        log_step(3, 7, "Accepting ToS...")
        await page.evaluate("""() => {
            const cb = document.querySelector('.ant-checkbox-input, input[type="checkbox"]');
            if (cb && !cb.checked) cb.click();
        }""")
        await asyncio.sleep(0.1)

        # Continue → Step 2
        for attempt in range(3):
            try:
                await page.locator('button[type="submit"]').first.click(
                    force=True, timeout=5000
                )
            except Exception:
                await page.evaluate("""() => {
                    const btns = document.querySelectorAll('button[type="submit"]');
                    for (const b of btns) {
                        if (b.offsetParent !== null) { b.click(); return; }
                    }
                }""")
                await page.keyboard.press("Enter")
            await asyncio.sleep(1)

            # Check if step 2 appeared (password field visible)
            pw_visible = await page.evaluate("""() => {
                const inputs = document.querySelectorAll('input[type="password"]');
                return inputs.length > 0 && inputs[0].offsetParent !== null;
            }""")
            if pw_visible:
                log(f"   ✅ Step 2 appeared (attempt {attempt + 1})")
                break
            else:
                log(f"   ⚠️ Step 2 not visible yet (attempt {attempt + 1}/3)")
                if attempt == 2:
                    await page.screenshot(
                        path=str(config.SCREENSHOTS_DIR / "step1_stuck.png")
                    )
                    log("   ❌ Step 2 never appeared!")
                    return False

        # ═══ STEP 2: Password ═══
        log_step(4, 7, "Step 2 — Entering password...")
        try:
            pw_input = page.locator('input[type="password"]').first
            await pw_input.scroll_into_view_if_needed()
            await pw_input.wait_for(state="visible", timeout=10000)
            await pw_input.fill(identity["password"])
            log("   ✅ Password filled")

            try:
                continue_btn = page.locator('button:has-text("Continue")').first
                await continue_btn.click(force=True, timeout=3000)
                log("   📤 Submitted")
            except Exception:
                await page.evaluate("""() => {
                    const btn = document.querySelector('button[type="submit"]');
                    if (btn) btn.click();
                }""")
                log("   📤 JS submitted")
                await asyncio.sleep(0.2)
                await pw_input.press("Enter")
        except Exception as e:
            log(f"   ⚠️ Playwright fill failed: {e}, trying JS fallback...")
            pw_filled = await page.evaluate("""(pw) => {
                const inputs = document.querySelectorAll('input[type="password"]');
                for (const inp of inputs) {
                    if (inp.offsetParent !== null
                        && inp.getBoundingClientRect().width > 0) {
                        inp.focus();
                        inp.value = pw;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                }
                return false;
            }""", identity["password"])
            if not pw_filled:
                log_err("Password fill completely failed")
                await page.screenshot(
                    path=str(config.SCREENSHOTS_DIR / "pw_fail.png")
                )
                return False

        await asyncio.sleep(1.5)
        await page.screenshot(
            path=str(config.SCREENSHOTS_DIR / "after_pw_submit.png")
        )

        # Debug: check form state
        form_state = await page.evaluate("""() => {
            const errors = document.querySelectorAll(
                '.ant-form-item-explain-error, .ant-form-item-explain, ' +
                '[class*="error"], [class*="Error"]'
            );
            const errTexts = [...errors]
                .map(e => e.textContent.trim()).filter(t => t);
            const pwInput = document.querySelector(
                'input[type="password"]');
            const pwVal = pwInput ? pwInput.value : '';
            const btn = document.querySelector(
                'button[type="submit"]');
            const btnDisabled = btn ? btn.disabled : null;
            return {
                errors: errTexts,
                pwLen: pwVal.length,
                pwValue: pwVal.substring(0, 3) + '...',
                btnDisabled: btnDisabled,
            };
        }""")
        log(
            f"   🔎 Form state: pw_len={form_state.get('pwLen', 0)}, "
            f"btn_disabled={form_state.get('btnDisabled')}, "
            f"errors={form_state.get('errors', [])}"
        )

        # ═══ STEP 3: Captcha ═══
        log_step(5, 7, "Verify page — Solving captcha...")
        page_text = (
            await page.evaluate(
                "() => document.body?.innerText?.substring(0, 500) || ''"
            )
        ).lower()

        needs_verify = any(
            kw in page_text
            for kw in [
                "click to verify", "verify", "human", "captcha",
                "sure you are", "验证", "点击验证",
            ]
        )

        if needs_verify:
            # Click the verify button
            clicked = False
            for sel in [
                "text=Click to verify", "text=点击验证",
                "text=verify", "text=Verify",
                '[class*="verify"]', '[class*="captcha-btn"]',
            ]:
                try:
                    await page.locator(sel).first.click(timeout=3000)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                await page.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const txt = el.textContent.trim().toLowerCase();
                        if (el.childNodes.length <= 3 &&
                            (txt.includes('click to verify')
                             || txt === 'verify'
                             || txt.includes('点击验证')
                             || txt.includes('sure you are human'))) {
                            el.click(); return true;
                        }
                    }
                }""")
            await asyncio.sleep(1)

            # Solve captcha
            captcha_ok = await captcha_solver.solve(page)
            if not captcha_ok:
                await page.screenshot(
                    path=str(config.SCREENSHOTS_DIR / "captcha_fail.png")
                )
                return False
            await asyncio.sleep(1)

        # ═══ Wait for OTP page ═══
        log("   ⏳ Waiting for OTP page...")
        await asyncio.sleep(1)
        await page.screenshot(
            path=str(config.SCREENSHOTS_DIR / "after_captcha.png")
        )

        otp_count = await page.locator(".ant-otp-input").count()
        page_text2 = (
            await page.evaluate(
                "() => document.body?.innerText?.substring(0, 500) || ''"
            )
        ).lower()
        log(f"   Page state: otp_inputs={otp_count}, text='{page_text2[:150]}'")

        if (
            otp_count == 0
            and "enter the code" not in page_text2
            and "otp" not in page_text2
        ):
            log_err("OTP page didn't appear after captcha solve")
            await page.screenshot(
                path=str(config.SCREENSHOTS_DIR / "no_otp_page.png")
            )
            return False

        # ═══ STEP 4: Wait for OTP email ═══
        log_step(6, 7, "Waiting for OTP email...")
        tm = TempMail()
        otp = None
        start = time.time()
        while time.time() - start < config.OTP_TIMEOUT:
            try:
                msgs = tm.inbox(email)
                if msgs:
                    msg = tm.message(msgs[0]["id"])
                    if msg:
                        html = msg.get("html", "") or msg.get("text", "")
                        otp = extract_otp(html)
                        if otp:
                            log_ok(f"OTP received: {otp}")
                            break
            except Exception as e:
                log(f"   ⚠️ Inbox fetch error (will retry): {e}")
            await asyncio.sleep(2)

        if not otp:
            log_err(f"OTP not received within {config.OTP_TIMEOUT}s")
            return False

        # ═══ STEP 5: Input OTP ═══
        log_step(7, 7, "Entering OTP...")
        otp_inputs = page.locator(".ant-otp-input")
        count = await otp_inputs.count()
        if count >= len(otp):
            for i, digit in enumerate(otp):
                await otp_inputs.nth(i).click()
                await page.keyboard.type(digit, delay=random.randint(10, 30))
                await asyncio.sleep(random.uniform(0.05, 0.1))
            log_ok("OTP entered!")
        else:
            log_err(f"Expected {len(otp)} OTP inputs, found {count}")
            return False

        await asyncio.sleep(1.5)

        # Check if captcha reappeared after OTP — if so, bail out
        captcha_back = await page.evaluate("""() => {
            const sels = ['#aliyunCaptcha-sliding', '.aliyunCaptcha', '#nc_1_wrapper',
                          '.nc-container', '.slide-verify'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent !== null) return true;
            }
            return false;
        }""")
        if captcha_back:
            log_err("Captcha reappeared after OTP — marking as failed")
            return False

        # Check if verified (redirect or success message)
        try:
            await page.wait_for_url(
                lambda url: any(
                    x in url
                    for x in ["/account/", "/device/selectAccounts", "/dashboard"]
                ),
                timeout=15000,
            )
            log_ok("Account verified and redirected!")
            return True
        except Exception:
            pass

        # Check page text for success indicators
        final_text = (
            await page.evaluate(
                "() => document.body?.innerText?.substring(0, 500) || ''"
            )
        ).lower()
        if any(kw in final_text for kw in ["verified", "success", "welcome"]):
            log_ok("Account verified!")
            return True

        await page.screenshot(
            path=str(config.SCREENSHOTS_DIR / "otp_result.png")
        )
        log(f"   Page after OTP: {final_text[:200]}")
        return True

    except Exception as e:
        log_err(f"Register error: {e}")
        await page.screenshot(
            path=str(config.SCREENSHOTS_DIR / "error.png")
        )
        return False
