"""
Qoder Autopilot — First Run Wizard
=====================================
Detects first run (no config file) and shows interactive setup wizard.

Usage:
    Called automatically by cli.main() when no config exists.
"""

import sys
from pathlib import Path

from .user_config import CONFIG_FILE

BOLD = "\033[1m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
NC = "\033[0m"


def is_first_run() -> bool:
    """Check if this is the first time running qoder-autopilot."""
    return not CONFIG_FILE.exists()


def run_first_run_wizard() -> bool:
    """
    Show first-run setup wizard.

    Returns:
        True if user wants to continue (quick start or after deploy).
        False if user wants to exit.
    """
    print()
    print(f"{BOLD}  ╔══════════════════════════════════════════════════╗{NC}")
    print(f"{BOLD}  ║       👋 Welcome to qoder-autopilot!             ║{NC}")
    print(f"{BOLD}  ║       Let's get you set up in 30 seconds.        ║{NC}")
    print(f"{BOLD}  ╚══════════════════════════════════════════════════╝{NC}")
    print()
    print(f"  {DIM}This tool automates Qoder account registration.{NC}")
    print(f"  {DIM}It needs a temp mail service to receive OTP codes.{NC}")
    print()
    print(f"  {BOLD}How do you want to set up temp mail?{NC}")
    print()
    print(f"  {GREEN}[1]{NC} 🚀 {BOLD}Quick Start{NC}")
    print(f"      Use the default public worker — instant, no setup.")
    print(f"      {DIM}Great for trying out or casual use.{NC}")
    print()
    print(f"  {GREEN}[2]{NC} 🏠 {BOLD}Self-Host{NC}")
    print(f"      Deploy your own Cloudflare Worker — independent, your domain.")
    print(f"      {DIM}Takes ~5 minutes. Needs Cloudflare account + domain.{NC}")
    print()

    while True:
        choice = input(f"  {BOLD}Pick [1/2]:{NC} ").strip()

        if choice == "1":
            print()
            print(f"  {GREEN}✅ Quick Start selected! Using default worker.{NC}")
            print()
            _mark_configured()
            return True

        elif choice == "2":
            print()
            print(f"  {BOLD}Do you already have a deployed worker?{NC}")
            print()
            print(f"  {GREEN}[a]{NC} 🆕 Deploy a new worker (~5 min)")
            print(f"  {GREEN}[b]{NC} 🔗 I already have a worker URL")
            print()

            while True:
                sub = input(f"  {BOLD}Pick [a/b]:{NC} ").strip().lower()

                if sub == "a":
                    from .deploy import deploy_worker
                    deploy_worker()
                    _mark_configured()
                    return True

                elif sub == "b":
                    url = input(f"  {BOLD}[?] Worker URL:{NC} ").strip()
                    if url and url.startswith("http"):
                        from .deploy import save_worker_url
                        save_worker_url(url.rstrip("/"))
                        _mark_configured()
                        return True
                    else:
                        print(f"  {YELLOW}Please enter a valid URL (https://...).{NC}")

                else:
                    print(f"  {YELLOW}Please enter a or b.{NC}")

        else:
            print(f"  {YELLOW}Please enter 1 or 2.{NC}")


def _mark_configured() -> None:
    """
    Ensure config file exists so first-run wizard doesn't show again.
    Even if user chose Quick Start (no custom config), we create an empty
    config to mark "user has seen the wizard".
    """
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text("{}")
