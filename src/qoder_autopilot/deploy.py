"""
Qoder Autopilot — Worker Deploy
==================================
Extract bundled worker template and run interactive setup wizard.
No need to clone a separate repo — everything is self-contained.

Usage:
    qoder-autopilot deploy
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

TEMPLATE_DIR = Path(__file__).parent / "worker_template"

BOLD = "\033[1m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
NC = "\033[0m"


def log(msg: str) -> None:
    print(f"  {CYAN}{msg}{NC}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✅ {msg}{NC}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠️  {msg}{NC}")


def err(msg: str) -> None:
    print(f"  {RED}❌ {msg}{NC}")


# ═══════════════════════════════════════════════════════════════════════════════
# PREREQUISITE CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

def check_node() -> bool:
    """Check if Node.js is installed."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            ok(f"Node.js {result.stdout.strip()}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    err("Node.js not found. Install: https://nodejs.org")
    return False


def check_npx() -> bool:
    """Check if npx is available."""
    try:
        result = subprocess.run(
            ["npx", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            ok(f"npx {result.stdout.strip()}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    err("npx not found (should come with Node.js)")
    return False


def check_wrangler_auth() -> bool:
    """Check if user is authenticated with Cloudflare."""
    try:
        result = subprocess.run(
            ["npx", "wrangler", "whoami"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            # Extract email from output
            for line in result.stdout.splitlines():
                if "@" in line:
                    ok(f"Logged in as {line.strip()}")
                    return True
            ok("Logged in to Cloudflare")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def wrangler_login() -> bool:
    """Open browser for Cloudflare login."""
    log("Opening browser for Cloudflare login...")
    try:
        result = subprocess.run(
            ["npx", "wrangler", "login"],
            timeout=120,
        )
        if result.returncode == 0:
            ok("Logged in to Cloudflare")
            return True
    except subprocess.TimeoutExpired:
        err("Login timed out (2 minutes)")
    except FileNotFoundError:
        err("npx not found")
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACT + DEPLOY
# ═══════════════════════════════════════════════════════════════════════════════

def extract_template(dest: Path) -> bool:
    """Extract bundled worker template to destination directory."""
    if not TEMPLATE_DIR.exists():
        err(f"Worker template not found at {TEMPLATE_DIR}")
        return False

    try:
        # Copy all template files
        for item in TEMPLATE_DIR.rglob("*"):
            if item.is_file():
                rel = item.relative_to(TEMPLATE_DIR)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

        # Make setup.sh executable
        setup_sh = dest / "scripts" / "setup.sh"
        if setup_sh.exists():
            setup_sh.chmod(0o755)

        ok(f"Worker files extracted to {dest}")
        return True
    except Exception as e:
        err(f"Failed to extract template: {e}")
        return False


def run_setup_wizard(work_dir: Path) -> str | None:
    """Run the interactive setup wizard (setup.sh) and return the worker URL."""
    setup_sh = work_dir / "scripts" / "setup.sh"
    if not setup_sh.exists():
        err("setup.sh not found in extracted template")
        return None

    print()
    log("Starting setup wizard...")
    print()

    try:
        result = subprocess.run(
            ["bash", str(setup_sh)],
            cwd=str(work_dir),
        )

        if result.returncode != 0:
            err(f"Setup wizard exited with code {result.returncode}")
            return None

    except KeyboardInterrupt:
        print()
        warn("Setup cancelled by user")
        return None

    # Try to find the worker URL from wrangler.toml or deploy output
    worker_url = _detect_worker_url(work_dir)
    return worker_url


def _detect_worker_url(work_dir: Path) -> str | None:
    """Try to detect the deployed worker URL automatically."""
    import re

    # Read wrangler.toml to get worker name
    toml_path = work_dir / "wrangler.toml"
    if not toml_path.exists():
        return None

    worker_name = None
    for line in toml_path.read_text().splitlines():
        if line.startswith("name"):
            match = re.search(r'name\s*=\s*"([^"]+)"', line)
            if match:
                worker_name = match.group(1)
                break

    if not worker_name:
        return None

    # Get account subdomain from wrangler whoami
    try:
        result = subprocess.run(
            ["npx", "wrangler", "whoami"],
            capture_output=True, text=True, timeout=15,
            cwd=str(work_dir),
        )
        # Parse subdomain from output like:
        # "│ xxxxxx  │ daivageralda831.workers.dev │"
        for line in result.stdout.splitlines():
            match = re.search(r'(\S+)\.workers\.dev', line)
            if match:
                subdomain = match.group(1)
                url = f"https://{worker_name}.{subdomain}.workers.dev"
                # Verify it's reachable
                try:
                    import urllib.request
                    req = urllib.request.Request(f"{url}/api/health", method="GET")
                    resp = urllib.request.urlopen(req, timeout=5)
                    if resp.status == 200:
                        ok(f"Auto-detected worker URL: {url}")
                        return url
                except Exception:
                    # URL might be valid but health check failed, still return it
                    ok(f"Detected worker URL: {url}")
                    return url
    except Exception:
        pass

    # Fallback: ask user
    print()
    url = input(f"  {BOLD}[?] Worker URL{NC} (e.g. https://{worker_name}.yoursubdomain.workers.dev): ").strip()
    if url and url.startswith("http"):
        return url.rstrip("/")

    return None


def save_worker_url(url: str) -> None:
    """Save the worker URL to user config."""
    from .user_config import set_user_config_value

    if set_user_config_value("worker_url", url):
        ok(f"Config saved: worker-url = {url}")
    else:
        warn("Could not save config (try: qoder-autopilot config set worker-url ...)")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN DEPLOY FLOW
# ═══════════════════════════════════════════════════════════════════════════════

def deploy_worker() -> None:
    """Main deploy flow — extract, setup, configure."""
    print()
    print(f"{BOLD}  ╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}  ║  🏠 Self-Host: Deploy Your Own Temp Mail Worker  ║{NC}")
    print(f"{BOLD}  ╚══════════════════════════════════════════════════╝{NC}")
    print()

    # Step 1: Check prerequisites
    log("Checking prerequisites...")
    if not check_node():
        sys.exit(1)
    if not check_npx():
        sys.exit(1)

    # Step 2: Check Cloudflare auth
    if not check_wrangler_auth() and not wrangler_login():
        err("Cloudflare authentication failed")
        sys.exit(1)

    # Step 3: Extract template
    print()
    work_dir = Path(tempfile.mkdtemp(prefix="qoder-mail-worker-"))
    log("Extracting worker template...")
    if not extract_template(work_dir):
        sys.exit(1)

    # Step 4: Install npm dependencies
    log("Installing worker dependencies...")
    try:
        subprocess.run(
            ["npm", "install", "--silent"],
            cwd=str(work_dir),
            capture_output=True,
            timeout=60,
        )
        ok("Dependencies installed")
    except Exception as e:
        warn(f"npm install issue: {e}")

    # Step 5: Run setup wizard
    worker_url = run_setup_wizard(work_dir)

    # Step 6: Save config
    if worker_url:
        print()
        save_worker_url(worker_url)
        print()
        print(f"  {GREEN}{BOLD}🎉 Deploy complete!{NC}")
        print()
        print(f"  {CYAN}Don't forget to enable Email Routing in Cloudflare Dashboard:{NC}")
        print("  Email → Routing Rules → Catch-all → Send to Worker")
        print()
        print(f"  {CYAN}Run qoder-autopilot to start:{NC}")
        print("  qoder-autopilot --manual-captcha")
        print()
    else:
        print()
        warn("Worker URL not detected. You can set it manually:")
        print("  qoder-autopilot config set worker-url https://your-worker.workers.dev")
        print()

    # Cleanup: ask if user wants to keep the extracted files
    print(f"  Worker files at: {work_dir}")
    keep = input(f"  {BOLD}[?]{NC} Keep extracted files? [y/N]: ").strip().lower()
    if keep != "y":
        shutil.rmtree(work_dir, ignore_errors=True)
        ok("Cleaned up temporary files")
    else:
        ok(f"Files kept at: {work_dir}")
