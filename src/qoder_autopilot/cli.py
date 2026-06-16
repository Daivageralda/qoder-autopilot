"""
Qoder Autopilot — CLI Entry Point
===================================
Command-line interface for automated Qoder account registration
with optional 9Router integration.

Usage:
    qoder-autopilot -n 5 --manual-captcha --parallel
    python -m qoder_autopilot -n 3 --headless
"""

import argparse
import asyncio
import os
import platform
import random
import signal
import sys

from .auth.credentials import save_creds
from .auth.identity import gen_identity
from .auth.oauth import initiate_device_flow, poll_device_token
from .browser.camoufox import launch_browser, setup_page
from .browser.window_tiler import get_screen_size
from .errors import NineRouterDBNotFound, NineRouterError
from .infra import config
from .infra.ninerouter import add_to_9router_device
from .infra.temp_mail import TempMail
from .register import register_and_verify
from .utils.logger import log, log_debug, log_err, log_ok, log_warn, set_account_tag


async def run_one(
    headless: bool = True,
    use_oauth: bool = True,
    manual_captcha: bool = False,
    acct_num: int = 0,
    proxy: str | None = None,
) -> dict | None:
    """Register a single Qoder account and optionally connect to 9Router.

    Args:
        headless: Run browser in headless mode.
        use_oauth: Use OAuth device flow for 9Router connection.
        manual_captcha: Pause for manual captcha solving.
        acct_num: Account number for parallel mode logging.

    Returns:
        Dict with email and token on success, None on failure.
    """
    tag = f"#{acct_num}" if acct_num else ""
    if tag:
        set_account_tag(tag)

    # Force non-headless when manual captcha is enabled
    if manual_captcha:
        headless = False

    log("=" * 60)
    log(f"🚀 QODER AUTOPILOT — Register + 9Router Connect {tag}")
    if manual_captcha:
        log("🧑 Manual captcha mode — browser will stay visible")
    log("=" * 60)

    # 1. Generate temp email
    log("📋 Step 1/4: Generating temp email...")
    tm = TempMail()
    edata = tm.generate()
    email = edata["address"]
    log_ok(f"Email: {email}")

    # 2. Generate identity
    log("📋 Step 2/4: Generating identity...")
    ident = gen_identity()
    log_ok(f"{ident['display_name']} | pw: {'•' * 8}")

    # 3. Register + verify
    log("📋 Step 3/4: OAuth register + device token flow...")
    flow = initiate_device_flow() if use_oauth else None
    auth_url = flow["auth_url"] if flow else None

    if auth_url:
        log(f"   🔗 OAuth URL: {auth_url[:80]}...")

    # Calculate grid slot window size
    if platform.system() == "Darwin":
        sw, sh = get_screen_size()
        win_w = sw // 2
        win_h = sh // 2
    else:
        win_w, win_h = 900, 600

    async with launch_browser(
        headless=headless,
        window_width=win_w,
        window_height=win_h,
        proxy=proxy,
    ) as browser:
        page = await browser.new_page()
        await setup_page(page)
        verified = await register_and_verify(
            page,
            email,
            ident,
            auth_url=auth_url,
            manual_captcha=manual_captcha,
            acct_num=acct_num,
        )

        # Keep browser open briefly for redirect
        await asyncio.sleep(2)
        await page.screenshot(path=str(config.SCREENSHOTS_DIR / "final_state.png"))
        final_url = page.url
        log(f"   📍 Final URL: {final_url}")

    if not verified:
        log_err("Registration/verification failed!")
        save_creds(
            {
                "email": email,
                "password": ident["password"],
                "display_name": ident["display_name"],
                "status": "failed",
            }
        )
        return None

    log_ok("Account registered & verified! ✅")

    # 4. Poll for device token + connect to 9Router
    if flow:
        log("📋 Step 4/4: Polling device token...")
        device_token = await asyncio.to_thread(
            poll_device_token,
            flow["nonce"],
            flow["verifier"],
            60,
            3,
        )

        if device_token:
            log_ok(f"🎉 Device token obtained! token={device_token['token'][:20]}...")

            # Add to 9Router
            router_ok = False
            try:
                add_to_9router_device(
                    email,
                    ident["display_name"],
                    device_token,
                    flow["machine_id"],
                )
                router_ok = True
            except NineRouterDBNotFound as e:
                log_err(f"9Router DB missing: {e}")
            except NineRouterError as e:
                log_err(f"9Router insert failed: {e}")

            save_creds(
                {
                    "email": email,
                    "password": ident["password"],
                    "display_name": ident["display_name"],
                    "access_token": device_token["token"],
                    "refresh_token": device_token.get("refresh_token", ""),
                    "user_id": device_token.get("user_id", ""),
                    "machine_id": flow["machine_id"],
                    "9router": router_ok,
                    "status": "success",
                }
            )
            if router_ok:
                log_ok(f"🎉 {email} → 9Router connected")
            else:
                log_warn(f"{email} registered but 9Router failed")
            return {"email": email, "token": device_token["token"]}
        else:
            log_err("Device token poll failed — account verified but no token")
            save_creds(
                {
                    "email": email,
                    "password": ident["password"],
                    "display_name": ident["display_name"],
                    "status": "verified_no_token",
                }
            )
            return None
    else:
        log("⚠️ No OAuth flow — just registration done")
        save_creds(
            {
                "email": email,
                "password": ident["password"],
                "display_name": ident["display_name"],
                "status": "verified_no_oauth",
            }
        )
        return {"email": email}


async def main_async(args: argparse.Namespace) -> None:
    """Async main entry point."""
    # U6: Graceful shutdown on Ctrl+C
    _shutdown_event = asyncio.Event()

    def _handle_signal():
        log_warn("Shutdown requested (Ctrl+C) — cleaning up...")
        _shutdown_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _handle_signal)
    except NotImplementedError:
        pass  # Windows doesn't support add_signal_handler

    headless = args.headless
    use_oauth = not args.no_oauth
    manual_captcha = args.manual_captcha
    parallel = args.parallel

    # U3: Warn about parallel + manual captcha conflict
    if parallel and manual_captcha and args.count > 1:
        log_warn(
            "--parallel + --manual-captcha: multiple browser windows will open "
            "simultaneously. Manual captcha solving may be confusing."
        )

    # U4: Apply verbosity
    from .utils.logger import set_verbosity

    if args.verbose:
        set_verbosity(2)
    elif args.quiet:
        set_verbosity(0)

    # F6: Log file
    log_file_handle = None
    if args.log_file:
        from .utils.logger import set_log_file

        log_file_handle = set_log_file(args.log_file)
        log(f"📝 Logging to: {args.log_file}")

    proxy = args.proxy
    output_format = args.output_format

    # U5: Dry-run mode
    if args.dry_run:
        log_ok("Dry-run mode: configuration is valid ✅")
        log(f"  Accounts: {args.count}")
        log(f"  Headless: {headless}")
        log(f"  OAuth: {use_oauth}")
        log(f"  Manual captcha: {manual_captcha}")
        log(f"  Parallel: {parallel}")
        log(f"  Worker URL: {config.settings.worker_url}")
        log(f"  9Router DB: {config.settings.ninerouter_db_path}")
        return

    log(
        f"🎯 Creating {args.count} account(s) | "
        f"headless={headless} | oauth={use_oauth} | "
        f"manual_captcha={manual_captcha} | parallel={parallel}"
    )

    if parallel and args.count > 1:
        # ═══ PARALLEL MODE ═══
        log(f"⚡ Parallel mode: launching {args.count} browser windows")

        async def staggered_run(i: int) -> dict | None:
            if i > 0:
                await asyncio.sleep(i * 2)
            return await run_one(
                headless=headless,
                use_oauth=use_oauth,
                manual_captcha=manual_captcha,
                acct_num=i + 1,
                proxy=proxy,
            )

        tasks = [staggered_run(i) for i in range(args.count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log_err(f"Account #{i + 1} crashed: {r}")
                results[i] = None
    else:
        # ═══ SEQUENTIAL MODE ═══
        results = []
        for i in range(args.count):
            log(f"\n{'─' * 60}\n📦 Account {i + 1}/{args.count}\n{'─' * 60}")
            r = await run_one(
                headless=headless,
                use_oauth=use_oauth,
                manual_captcha=manual_captcha,
                acct_num=i + 1 if args.count > 1 else 0,
                proxy=proxy,
            )
            results.append(r)
            if i < args.count - 1:
                d = config.PARALLEL_DELAY + random.randint(0, 15)
                log(f"⏳ Waiting {d}s...")
                await asyncio.sleep(d)

    s = sum(1 for r in results if r)
    log(f"\n{'═' * 60}\n📊 DONE: {s}/{len(results)} succeeded\n{'═' * 60}")

    # F5: Output results in requested format
    valid_results = [r for r in results if r]
    if output_format == "json":
        import json

        print(json.dumps(valid_results, indent=2))
    elif output_format == "csv":
        if valid_results:
            keys = list(valid_results[0].keys())
            print(",".join(keys))
            for r in valid_results:
                print(",".join(str(r.get(k, "")) for k in keys))

    # H7: Screenshot cleanup — delete screenshots from successful runs
    try:
        import shutil

        if config.SCREENSHOTS_DIR.exists() and not any(config.SCREENSHOTS_DIR.glob("*fail*")):
            # Only clean up if no failure screenshots exist
            shutil.rmtree(config.SCREENSHOTS_DIR, ignore_errors=True)
            log_debug("Cleaned up debug screenshots (all runs succeeded)")
    except Exception:
        pass

    # F6: Close log file
    if log_file_handle:
        from .utils.logger import close_log_file

        close_log_file()
        log(f"📝 Log saved to: {args.log_file}")


def main() -> None:
    """CLI entry point with config management subcommand."""

    # ── Quick check for subcommands before full argparse ──
    if len(sys.argv) > 1:
        sub = sys.argv[1]

        if sub == "config":
            _handle_config_command(sys.argv[2:])
            return

        if sub == "deploy":
            from .setup.deploy import deploy_worker

            deploy_worker()
            return

        if sub == "relay":
            _handle_relay_command(sys.argv[2:])
            return

        if sub == "doctor":
            from .setup.doctor import run_doctor

            run_doctor()
            return

    # ── First-run wizard ──
    from .setup.first_run import is_first_run, run_first_run_wizard

    if is_first_run():
        if not run_first_run_wizard():
            return
        # After wizard, continue to main flow (user can run with args)
        # If no args besides the program name, exit gracefully
        if len(sys.argv) <= 1:
            print("  Run with --help to see available options:")
            print("  qoder-autopilot -n 3 --manual-captcha")
            return

    # ── Main registration arguments ──
    p = argparse.ArgumentParser(
        prog="qoder-autopilot",
        description="Automated Qoder account registration with 9Router integration",
        epilog=(
            "subcommands:\n"
            "  doctor           🩺 Health check — verify dependencies & configs\n"
            "  deploy           Deploy your own temp mail Cloudflare Worker\n"
            "  relay            Start relay server for remote 9Router\n"
            "  config           Manage configuration (show/set/get/reset)\n"
            "\n"
            "examples:\n"
            "  qoder-autopilot -n 3 --manual-captcha\n"
            "  qoder-autopilot doctor\n"
            "  qoder-autopilot relay --port 9999\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    def _valid_count(val: str) -> int:
        """Validate count is between 1 and 100."""
        n = int(val)
        if n < 1 or n > 100:
            raise argparse.ArgumentTypeError(f"Count must be between 1 and 100, got {n}")
        return n

    p.add_argument(
        "-n",
        "--count",
        type=_valid_count,
        default=1,
        help="Number of accounts to create (1-100)",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (hidden)",
    )
    p.add_argument(
        "--no-oauth",
        action="store_true",
        help="Skip OAuth flow, just register",
    )
    p.add_argument(
        "--manual-captcha",
        action="store_true",
        help="Pause for manual captcha solving (forces non-headless)",
    )
    p.add_argument(
        "--parallel",
        action="store_true",
        help="Run all accounts concurrently",
    )
    p.add_argument(
        "--delay",
        type=int,
        default=config.PARALLEL_DELAY,
        help=f"Delay between sequential accounts (default: {config.PARALLEL_DELAY}s)",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show debug-level logs",
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show errors and warnings",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and exit without registering",
    )
    p.add_argument(
        "--proxy",
        type=str,
        default=None,
        metavar="URL",
        help="Proxy URL for browser (e.g. socks5://host:port, http://host:port)",
    )
    p.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        dest="output_format",
        help="Output format for results (default: text)",
    )
    p.add_argument(
        "--log-file",
        type=str,
        default=None,
        metavar="PATH",
        help="Write all logs to a file (in addition to terminal)",
    )
    args = p.parse_args()

    asyncio.run(main_async(args))


def _handle_config_command(argv: list[str]) -> None:
    """Handle 'qoder-autopilot config' subcommands."""
    from .infra.user_config import (
        CONFIG_FILE,
        USER_CONFIGURABLE,
        delete_user_config,
        load_user_config,
        set_user_config_value,
    )

    if not argv or argv[0] in ("-h", "--help"):
        print("Usage: qoder-autopilot config <command> [args]")
        print()
        print("Commands:")
        print("  show                    Show all current settings")
        print("  set <key> <value>       Set a config value")
        print("  get <key>               Get a config value")
        print("  reset                   Reset all settings to defaults")
        print()
        print("Configurable keys:")
        for _key, info in USER_CONFIGURABLE.items():
            cli = info["cli_flag"]
            print(f"  {cli:20s} {info['description']}")
        print()
        print(f"Config file: {CONFIG_FILE}")
        print()
        print("─── Self-Host Your Own Temp Mail Worker ───")
        print("  Deploy your own Cloudflare Worker in 5 minutes:")
        print("  https://github.com/Daivageralda/cf-mail-worker")
        print()
        print("  Then point qoder-autopilot to it:")
        print("  qoder-autopilot config set worker-url https://your-worker.workers.dev")
        return

    cmd = argv[0]

    if cmd == "show":
        cfg = load_user_config()
        # Also show defaults and env overrides
        from .infra.config import settings

        print(f"{'Setting':<25} {'Value':<50} {'Source':<10}")
        print("─" * 85)
        for key, info in USER_CONFIGURABLE.items():
            env_val = os.environ.get(f"QODER_{key.upper()}", "")
            current = getattr(settings, key, None)
            if env_val:
                source = "env"
            elif key in cfg:
                source = "config"
            else:
                source = "default"
            val_str = str(current) if current else "(empty)"
            # Mask sensitive fields (API keys, tokens, passwords)
            sensitive_suffixes = ("api_key", "token", "password", "secret")
            if any(key.endswith(s) for s in sensitive_suffixes) and val_str not in ("(empty)", ""):
                val_str = val_str[:4] + "••••" + val_str[-4:] if len(val_str) > 8 else "***"
            print(f"  {info['cli_flag']:<23} {val_str:<50} {source}")
        print()
        print(f"Config file: {CONFIG_FILE}")
        print()
        print("💡 Want to self-host your own temp mail worker?")
        print("   → https://github.com/Daivageralda/cf-mail-worker")

    elif cmd == "set":
        if len(argv) < 3:
            print("Usage: qoder-autopilot config set <key> <value>")
            print("Example: qoder-autopilot config set worker-url https://my-worker.workers.dev")
            sys.exit(1)
        cli_flag = argv[1]
        value = argv[2]
        # Map CLI flag to config key
        key_map = {info["cli_flag"]: key for key, info in USER_CONFIGURABLE.items()}
        key = key_map.get(cli_flag)
        if not key:
            print(f"❌ Unknown key: {cli_flag}")
            print(f"Available: {', '.join(key_map.keys())}")
            sys.exit(1)
        if set_user_config_value(key, value):
            print(f"✅ {cli_flag} = {value}")
            print(f"   Saved to {CONFIG_FILE}")
        else:
            print(f"❌ Failed to set {cli_flag} (invalid value?)")
            sys.exit(1)

    elif cmd == "get":
        if len(argv) < 2:
            print("Usage: qoder-autopilot config get <key>")
            sys.exit(1)
        cli_flag = argv[1]
        key_map = {info["cli_flag"]: key for key, info in USER_CONFIGURABLE.items()}
        key = key_map.get(cli_flag)
        if not key:
            print(f"❌ Unknown key: {cli_flag}")
            sys.exit(1)
        cfg = load_user_config()
        val = cfg.get(key, "(not set)")
        print(f"{cli_flag} = {val}")

    elif cmd == "reset":
        if delete_user_config():
            print(f"✅ Config reset — deleted {CONFIG_FILE}")
        else:
            print("ℹ️  No config file to delete")

    else:
        print(f"❌ Unknown command: {cmd}")
        print("Run 'qoder-autopilot config --help' for usage")
        sys.exit(1)


def _handle_relay_command(argv: list[str]) -> None:
    """Handle 'qoder-autopilot relay' subcommand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="qoder-autopilot relay",
        description="Start relay server for remote 9Router integration",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1 — use 0.0.0.0 for external access)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Bind port (default: 8765)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Custom auth token (default: auto-generate)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Custom 9Router DB path (default: auto-detect)",
    )

    if argv and argv[0] in ("-h", "--help"):
        parser.print_help()
        return

    args = parser.parse_args(argv)

    from .infra.relay import start_relay

    start_relay(
        host=args.host,
        port=args.port,
        custom_token=args.token,
        custom_db_path=args.db,
    )
