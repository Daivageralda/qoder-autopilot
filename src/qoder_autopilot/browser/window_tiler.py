"""
Qoder Autopilot — Window Grid Tiling
======================================
Tile Camoufox browser windows into a 2×2 grid layout.
Supports macOS (AppleScript) and Windows (Win32 API via ctypes).

Grid layout:
    ┌──────────┬──────────┐
    │  Slot 1  │  Slot 2  │  (top row)
    ├──────────┼──────────┤
    │  Slot 3  │  Slot 4  │  (bottom row)
    └──────────┴──────────┘

Windows cycle through slots: 5th window → slot 1, 6th → slot 2, etc.
"""

import platform
import subprocess

from ..logger import log

_screen_size_cache: tuple[int, int] | None = None


def get_screen_size() -> tuple[int, int]:
    """Get main screen dimensions (cached).

    macOS: Uses AppleScript (osascript).
    Windows: Uses ctypes Win32 API (GetSystemMetrics).
    Linux: Falls back to 1920×1080.

    Returns:
        Tuple of (width, height) in pixels.
    """
    global _screen_size_cache
    if _screen_size_cache:
        return _screen_size_cache

    system = platform.system()

    if system == "Darwin":
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "Finder" to get bounds of window of desktop',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            parts = [int(x.strip()) for x in result.stdout.strip().split(",")]
            _screen_size_cache = (parts[2], parts[3])
        except Exception:
            _screen_size_cache = (1920, 1080)

    elif system == "Windows":
        try:
            import ctypes

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            SM_CXSCREEN = 0  # noqa: N806
            SM_CYSCREEN = 1  # noqa: N806
            w = user32.GetSystemMetrics(SM_CXSCREEN)
            h = user32.GetSystemMetrics(SM_CYSCREEN)
            _screen_size_cache = (w, h)
        except Exception:
            _screen_size_cache = (1920, 1080)

    else:
        # Linux / other — fallback
        _screen_size_cache = (1920, 1080)

    return _screen_size_cache


def _tile_macos(sw: int, sh: int) -> None:
    """Tile Camoufox windows on macOS using AppleScript."""
    half_w = sw // 2
    half_h = sh // 2
    menubar = 25

    # Grid positions: (left, top, right, bottom)
    g = [
        (0, menubar, half_w, half_h + menubar),
        (half_w, menubar, sw, half_h + menubar),
        (0, half_h + menubar, half_w, sh),
        (half_w, half_h + menubar, sw, sh),
    ]

    grid_str = (
        "{"
        + "{"
        + f"{g[0][0]}, {g[0][1]}, {g[0][2]}, {g[0][3]}"
        + "}, "
        + "{"
        + f"{g[1][0]}, {g[1][1]}, {g[1][2]}, {g[1][3]}"
        + "}, "
        + "{"
        + f"{g[2][0]}, {g[2][1]}, {g[2][2]}, {g[2][3]}"
        + "}, "
        + "{"
        + f"{g[3][0]}, {g[3][1]}, {g[3][2]}, {g[3][3]}"
        + "}"
        + "}"
    )

    script = f"""
    tell application "camoufox"
        set winCount to count of windows
        set grid to {grid_str}
        repeat with i from 1 to winCount
            set posIdx to ((i - 1) mod 4) + 1
            set bounds of window i to item posIdx of grid
        end repeat
        return winCount
    end tell
    """

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        count = result.stdout.strip()
        log(f"   🪟 Tiled {count} Camoufox windows into 2×2 grid")
    except Exception as e:
        log(f"   ⚠️ Grid tiling failed: {e}", "WARN")


def _tile_windows(sw: int, sh: int) -> None:
    """Tile Camoufox windows on Windows using Win32 API via ctypes.

    Enumerates all top-level windows, filters by title containing 'camoufox'
    or 'firefox' (Camoufox is Firefox-based), then positions them in a 2×2 grid.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]

    # Win32 constants
    SWP_NOZORDER = 0x0004  # noqa: N806
    SWP_NOACTIVATE = 0x0010  # noqa: N806
    GW_OWNER = 4  # noqa: N806
    WS_VISIBLE = 0x10000000  # noqa: N806

    # Grid positions
    half_w = sw // 2
    half_h = sh // 2
    taskbar_h = 48  # approximate Windows taskbar height

    grid = [
        (0, 0, half_w, half_h),  # top-left
        (half_w, 0, half_w, half_h),  # top-right
        (0, half_h, half_w, half_h - taskbar_h),  # bottom-left
        (half_w, half_h, half_w, half_h - taskbar_h),  # bottom-right
    ]

    # Callback type for EnumWindows
    WNDENUMPROC = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]  # noqa: N806
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    found_windows: list[int] = []

    def enum_callback(hwnd: int, _lparam: int) -> bool:
        """Collect visible top-level windows with Camoufox/Firefox in title."""
        # Skip invisible windows
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
        if not (style & WS_VISIBLE):
            return True

        # Skip child/owned windows (only want top-level)
        owner = user32.GetWindow(hwnd, GW_OWNER)
        if owner:
            return True

        # Get window title
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()

        # Match Camoufox windows (title contains 'camoufox' or 'firefox')
        if "camoufox" in title or "firefox" in title:
            found_windows.append(hwnd)

        return True

    try:
        # Enumerate all windows
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

        if not found_windows:
            log("   ⚠️ No Camoufox windows found for tiling", "WARN")
            return

        # Position each window in the grid
        count = 0
        for i, hwnd in enumerate(found_windows):
            slot = i % 4
            x, y, w, h = grid[slot]

            # SetWindowPos: move and resize
            user32.SetWindowPos(
                hwnd,
                None,
                x,
                y,
                w,
                h,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )
            count += 1

        log(f"   🪟 Tiled {count} Camoufox windows into 2×2 grid (Windows)")

    except Exception as e:
        log(f"   ⚠️ Windows grid tiling failed: {e}", "WARN")


def tile_all_camoufox_windows() -> None:
    """Tile ALL open Camoufox windows into a 2×2 grid.

    Call this after all browsers have been launched.
    Supports macOS (AppleScript) and Windows (Win32 API).
    Linux is not supported (falls back to no-op).
    """
    system = platform.system()
    if system not in ("Darwin", "Windows"):
        return

    sw, sh = get_screen_size()

    if system == "Darwin":
        _tile_macos(sw, sh)
    elif system == "Windows":
        _tile_windows(sw, sh)
