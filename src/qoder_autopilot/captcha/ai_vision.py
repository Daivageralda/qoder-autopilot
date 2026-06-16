"""
Qoder Autopilot — AI Vision Captcha Gap Detection
===================================================
Uses AI vision models (Gemini, OpenAI, etc. via OpenAI-compatible API)
combined with OpenCV preprocessing to identify the gap position in
Aliyun slide CAPTCHAs.

Strategy:
    1. Extract puzzle piece and background images from the page
    2. Use OpenCV to create a silhouette of the puzzle piece
    3. Crop background to the puzzle strip region
    4. Apply CLAHE contrast enhancement + edge detection
    5. Send composite image to AI for gap identification
"""

import base64
import json
import re
import time

from .. import config
from ..logger import log


async def gemini_detect_gap(page) -> float | None:
    """Use AI Vision to find the gap position in an Aliyun slide captcha.

    Extracts puzzle piece silhouette, enhances background strip, and asks
    the AI model to identify the gap X coordinate.

    Args:
        page: Playwright/Camoufox page object with the captcha loaded.

    Returns:
        The X offset scaled to track width, or None on failure.
    """
    try:
        import cv2
        import numpy as np
        from openai import OpenAI

        api_key = config.AI_API_KEY
        if not api_key:
            log("   ⚠️ AI_API_KEY not set! Check .env file")
            return None

        model = config.AI_MODEL
        log(f"   🤖 Using model: {model}, API key: {api_key[:8]}...")
        client = OpenAI(api_key=api_key, base_url=config.AI_BASE_URL)

        # ─── Get image data + puzzle piece position from page ───
        img_data = await page.evaluate("""() => {
            const bg = document.querySelector('#aliyunCaptcha-img');
            const pz = document.querySelector('#aliyunCaptcha-puzzle');
            const track = document.querySelector('#aliyunCaptcha-sliding-body');
            if (!bg || !pz) return null;
            const bgRect = bg.getBoundingClientRect();

            // Get puzzle piece ACTUAL position using multiple methods
            let pzTop = 0, pzHeight = 50;

            // Method 1: CSS style.top (most reliable for absolutely positioned elements)
            const styleTop = pz.style.top;
            if (styleTop && styleTop.includes('px')) {
                pzTop = parseFloat(styleTop);
            }

            // Method 2: offsetTop relative to parent
            if (pzTop === 0 && pz.offsetParent) {
                pzTop = pz.offsetTop;
            }

            // Method 3: Get actual image dimensions (not container)
            if (pz.tagName === 'IMG') {
                pzHeight = pz.clientHeight || pz.offsetHeight || 50;
                if (pzHeight > bgRect.height * 0.8 && pz.naturalHeight > 0) {
                    const scale = bgRect.height / pz.naturalHeight;
                    pzHeight = pz.naturalHeight * scale;
                }
            } else {
                pzHeight = pz.clientHeight || 50;
            }

            // Fallback: if pzHeight is still wrong, estimate ~25% of bg height
            if (pzHeight > bgRect.height * 0.8) {
                pzHeight = Math.round(bgRect.height * 0.25);
            }

            return {
                bgSrc: bg?.src || '',
                pzSrc: pz?.src || '',
                bgW: bgRect?.width || 300,
                bgH: bgRect?.height || 200,
                bgX: bgRect?.x || 0,
                bgY: bgRect?.y || 0,
                pzW: pz?.clientWidth || pz?.offsetWidth || 50,
                pzH: pzHeight,
                pzTop: pzTop,
                trackW: track?.getBoundingClientRect()?.width || 300,
            };
        }""")

        if not img_data or not img_data.get("bgSrc"):
            log("   ⚠️ No background image src (captcha may be loading)")
            return None

        def get_b64(uri: str) -> str | None:
            if uri.startswith("data:"):
                _, b64data = uri.split(",", 1)
                return b64data
            return None

        bg_b64 = get_b64(img_data["bgSrc"])
        pz_b64 = get_b64(img_data.get("pzSrc", ""))

        # Cache puzzle piece from first attempt for reuse on retries
        if pz_b64:
            gemini_detect_gap._cached_pz_b64 = pz_b64
        elif hasattr(gemini_detect_gap, "_cached_pz_b64"):
            pz_b64 = gemini_detect_gap._cached_pz_b64
            log("   📌 Using cached puzzle piece from first attempt")

        track_w = int(img_data["trackW"])

        # ─── Decode background image ───
        bg_img = None
        if bg_b64:
            bg_bytes = base64.b64decode(bg_b64)
            bg_arr = np.frombuffer(bg_bytes, dtype=np.uint8)
            bg_img = cv2.imdecode(bg_arr, cv2.IMREAD_COLOR)
        elif img_data["bgSrc"].startswith("http"):
            try:
                import urllib.request

                log("   🔄 Fetching bg image from URL...")
                req = urllib.request.Request(img_data["bgSrc"])
                with urllib.request.urlopen(req, timeout=5) as resp:
                    bg_bytes_raw = resp.read()
                bg_arr = np.frombuffer(bg_bytes_raw, dtype=np.uint8)
                bg_img = cv2.imdecode(bg_arr, cv2.IMREAD_COLOR)
            except Exception as e:
                log(f"   ⚠️ Failed to fetch HTTP image: {e}")

        if bg_img is None:
            log(f"   ⚠️ Failed to decode bg image (src={img_data['bgSrc'][:60]})")
            return None
        actual_h, actual_w = bg_img.shape[:2]

        # ─── Crop background to puzzle strip ───
        pz_screen_y = img_data.get("pzTop", 0)
        pz_screen_h = img_data["pzH"]
        scale_y = actual_h / img_data["bgH"] if img_data["bgH"] > 0 else 1
        pz_img_y = int(pz_screen_y * scale_y)
        pz_img_h = int(pz_screen_h * scale_y)

        pad = max(15, pz_img_h // 3)
        crop_y1 = max(0, pz_img_y - pad)
        crop_y2 = min(actual_h, pz_img_y + pz_img_h + pad)
        crop_h = crop_y2 - crop_y1

        log(f"   📐 Strip: pz_y={pz_img_y}, pz_h={pz_img_h} → crop {crop_y1}-{crop_y2} ({crop_h}px)")

        bg_strip = bg_img[crop_y1:crop_y2, :]

        # ─── Process puzzle piece → shape silhouette ───
        pz_silhouette_b64 = None
        if pz_b64:
            pz_bytes = base64.b64decode(pz_b64)
            pz_arr = np.frombuffer(pz_bytes, dtype=np.uint8)
            pz_img = cv2.imdecode(pz_arr, cv2.IMREAD_UNCHANGED)

            if pz_img is not None:
                if len(pz_img.shape) == 3 and pz_img.shape[2] == 4:
                    alpha = pz_img[:, :, 3]
                    _, mask = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
                else:
                    gray = (
                        cv2.cvtColor(pz_img, cv2.COLOR_BGR2GRAY)
                        if len(pz_img.shape) == 3
                        else pz_img
                    )
                    _, mask = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)

                pz_h, pz_w = mask.shape[:2]
                silhouette = np.ones((pz_h, pz_w), dtype=np.uint8) * 255
                silhouette[mask > 0] = 0

                kernel = np.ones((3, 3), np.uint8)
                dilated = cv2.dilate(255 - silhouette, kernel, iterations=2)
                border = cv2.subtract(dilated, 255 - silhouette)
                silhouette_color = cv2.cvtColor(silhouette, cv2.COLOR_GRAY2BGR)
                silhouette_color[border > 0] = [0, 0, 255]

                scale = crop_h / pz_h
                new_pz_w = int(pz_w * scale)
                silhouette_resized = cv2.resize(silhouette_color, (new_pz_w, crop_h))

                _, pz_buf = cv2.imencode(".png", silhouette_resized)
                pz_silhouette_b64 = base64.b64encode(pz_buf).decode("ascii")

        # ─── Process cropped strip → enhance gap ───
        strip_h = bg_strip.shape[0]
        strip_w = bg_strip.shape[1]

        # CLAHE on strip
        lab = cv2.cvtColor(bg_strip, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(8, 8))
        l_enh = clahe.apply(l_ch)
        enhanced = cv2.cvtColor(cv2.merge([l_enh, a_ch, b_ch]), cv2.COLOR_LAB2BGR)

        # Edge detection on strip
        gray = cv2.cvtColor(bg_strip, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 40, 120)
        edges_color = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

        # Composite: original | enhanced | edges
        composite = np.hstack([bg_strip, enhanced, edges_color])

        # Pad if too thin (AI models struggle with very thin images)
        min_height = 100
        if composite.shape[0] < min_height:
            pad_top = (min_height - composite.shape[0]) // 2
            pad_bottom = min_height - composite.shape[0] - pad_top
            composite = cv2.copyMakeBorder(
                composite, pad_top, pad_bottom, 0, 0,
                cv2.BORDER_CONSTANT, value=[200, 200, 200],
            )

        _, comp_buf = cv2.imencode(".png", composite)
        comp_b64 = base64.b64encode(comp_buf).decode("ascii")
        comp_w = composite.shape[1]

        log(f"   🔬 CV2: strip={strip_w}x{strip_h}, composite={comp_w}x{strip_h}, "
            f"puzzle={'yes' if pz_silhouette_b64 else 'no'}")

        # Save debug screenshot
        try:
            dbg_dir = config.SCREENSHOTS_DIR
            dbg_dir.mkdir(exist_ok=True)
            with open(dbg_dir / f"captcha_strip_{int(time.time())}.png", "wb") as f:
                f.write(comp_buf.tobytes())
        except Exception:
            pass

        # ─── AI Vision: Find gap in cropped strip ───
        prompt = f"""You are solving a jigsaw slide puzzle CAPTCHA.

IMAGE: A horizontal strip cropped from the background at the exact height where the puzzle piece goes. Shows 3 views side by side:
- LEFT: Original photo
- MIDDLE: Contrast-enhanced (gap/shadow is darker and more visible)
- RIGHT: Edge detection (outlines highlighted)

The strip is {strip_w}px wide and {strip_h}px tall. All three views show the SAME area.

YOUR TASK: Find the GAP/CUTOUT in the background where the puzzle piece should go.
Look for a dark shadow, cutout, or missing piece in the image. It appears as a darker area with distinct edges.

Return the X coordinate (in pixels from LEFT edge) of the CENTER of the gap.
Answer MUST be between 10 and {strip_w - 10}.

Respond ONLY with JSON: {{"x": 150, "confidence": 0.95}}"""

        content = [{"type": "text", "text": prompt}]
        content.append({
            "type": "text",
            "text": "BACKGROUND STRIP (original | enhanced | edges):",
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{comp_b64}"},
        })

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=1000,
            temperature=0,
        )

        if not response.choices or not response.choices[0].message:
            log(f"   ⚠️ AI returned empty response object: {response}")
            return None

        text = (response.choices[0].message.content or "").strip()
        finish = response.choices[0].finish_reason
        usage = getattr(response, "usage", None)
        log(f"   🤖 AI raw response: {repr(text[:200])} | finish={finish} | usage={usage}")
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        match = re.search(r'\{[^}]*"x"\s*:\s*(\d+)[^}]*\}', text)
        if match:
            data = json.loads(match.group())
            gap_x = int(data.get("x", 0))
            conf = float(data.get("confidence", 0.8))

            if 0 < gap_x < actual_w:
                scaled_x = (gap_x / actual_w) * track_w
                log(
                    f"   🤖 AI match: x={gap_x}px (img {actual_w}px) "
                    f"→ track {scaled_x:.0f}/{track_w}px, conf={conf:.2f}"
                )
                return scaled_x
            else:
                log(f"   ⚠️ Out-of-range x={gap_x} (max {actual_w})")
        else:
            log(f"   ⚠️ Parse fail: {text[:120]}")

        return None

    except Exception as e:
        log(f"   ⚠️ AI+CV2 error: {e}")
        return None
