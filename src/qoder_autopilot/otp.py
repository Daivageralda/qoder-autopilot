"""
Qoder Autopilot — OTP Extraction
==================================
Extract 6-digit OTP codes from email HTML content.
Handles various email templates and filters out CSS color codes.
"""

import re

# Common CSS color codes that look like 6-digit numbers but aren't OTPs
_CSS_COLORS = {
    "000000", "111111", "222222", "333333", "444444", "555555", "666666",
    "777777", "888888", "999999", "aaaaaa", "bbbbbb", "cccccc", "dddddd",
    "eeeeee", "ffffff", "232323", "464646", "f9f8f9",
}


def extract_otp(html: str | None) -> str | None:
    """
    Extract a 6-digit OTP from email HTML.

    Strategy (in order of reliability):
    1. Look for OTP in letter-spacing styled elements (common OTP display pattern)
    2. Look for OTP in large font-size elements
    3. Fallback: any 6-digit number that isn't a CSS color code
    """
    # Guard against None or empty input
    if not html:
        return None

    # Method 1: letter-spacing context (OTP display style)
    spaced = re.findall(r"letter-spacing.*?>([\d\s]+)<", html, re.DOTALL)
    for s in spaced:
        code = re.sub(r"\s", "", s).strip()
        if len(code) == 6 and code.isdigit() and code.lower() not in _CSS_COLORS:
            return code

    # Method 2: big font-size elements
    big = re.findall(
        r"font-size:\s*(?:[2-9][0-9]|[1-9][0-9]{2})px[^>]*>([^<]+)<", html
    )
    for b in big:
        code = re.sub(r"\D", "", b)
        if len(code) == 6 and code.lower() not in _CSS_COLORS:
            return code

    # Method 3: any 6-digit number not matching common CSS colors
    all_codes = re.findall(r">(\d{6})<", html)
    for c in all_codes:
        if c.lower() not in _CSS_COLORS:
            return c

    return None
