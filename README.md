# 🤖 Qoder Autopilot

Automated [Qoder](https://qoder.com) account registration with anti-detect browser, multi-strategy captcha solving, and [9Router](https://github.com/nicepkg/9router) OAuth device token integration.

> Register Qoder accounts → solve captchas → verify OTP → auto-connect to 9Router. All in one command.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/pypi/v/qoder-autopilot.svg)](https://pypi.org/project/qoder-autopilot/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Camoufox](https://img.shields.io/badge/browser-Camoufox-orange.svg)](https://camoufox.com/)
[![Tests](https://github.com/Daivageralda/qoder-autopilot/actions/workflows/test.yml/badge.svg)](https://github.com/Daivageralda/qoder-autopilot/actions/workflows/test.yml)

---

> **📦 Published on PyPI** — [pypi.org/project/qoder-autopilot](https://pypi.org/project/qoder-autopilot/)
>
> Install with `pip install qoder-autopilot` — no clone needed.

## ✨ Features

- **🦊 Anti-detect Browser** — Uses [Camoufox](https://camoufox.com/) (stealth Firefox fork) with C++-level fingerprinting to bypass bot detection
- **🧩 Multi-strategy Captcha Solving**
  - AI Vision (Gemini/GPT via OpenAI-compatible API)
  - Manual mode (pause and solve it yourself)
- **📧 Multi-Provider Temp Mail** — Cloudflare Workers (default) or Moca Supabase
- **🔐 OAuth Device Flow** — PKCE-based device token flow (reverse-engineered from 9Router)
- **🔌 9Router Auto-Connect** — Inserts device tokens directly into 9Router's SQLite database
- **🚀 First-Run Wizard** — Interactive setup on first launch
- **🏠 Built-in Worker Deploy** — Deploy your own temp mail worker from CLI
- **⚡ Parallel Mode** — Register multiple accounts concurrently
- **⚙️ Persistent Config** — `qoder-autopilot config` for easy customization

## 📦 Installation

### Via pip (recommended)

```bash
# Basic install (manual captcha only)
pip install qoder-autopilot

# With AI captcha solver support
pip install qoder-autopilot[captcha]

# Full install with all extras
pip install qoder-autopilot[full]
```

### From source (development)

```bash
git clone https://github.com/Daivageralda/qoder-autopilot.git
cd qoder-autopilot

# Basic install
pip install -e .

# With AI captcha solver
pip install -e ".[captcha]"

# Full install + dev tools
pip install -e ".[dev]"
```

### Post-install

```bash
# Download Camoufox browser binary
python -m camoufox fetch

# Download Playwright browsers (if needed)
playwright install firefox
```

## 🚀 Quick Start

First time? Just run:

```bash
qoder-autopilot
```

You'll see the setup wizard:

```
  ╔══════════════════════════════════════════════════╗
  ║       👋 Welcome to qoder-autopilot!             ║
  ║       Let's get you set up in 30 seconds.        ║
  ╚══════════════════════════════════════════════════╝

  [1] 🚀 Quick Start — use the default public worker
  [2] 🏠 Self-Host — deploy your own Cloudflare Worker
```

Pick **1** for instant setup, or **2** to deploy your own temp mail service.

### Registration commands

```bash
# Single account, manual captcha (most reliable)
qoder-autopilot --manual-captcha

# 5 accounts sequentially
qoder-autopilot -n 5 --manual-captcha

# 5 accounts in parallel
qoder-autopilot -n 5 --manual-captcha --parallel

# Skip OAuth/9Router, just register
qoder-autopilot --manual-captcha --no-oauth

# Show browser windows
qoder-autopilot --manual-captcha --no-headless

# Custom delay between accounts (seconds)
qoder-autopilot -n 3 --manual-captcha --delay 60
```

## 📋 All Commands

| Command | Description |
|---|---|
| `qoder-autopilot` | First-run wizard (no config) or start registration |
| `qoder-autopilot [options]` | Register accounts (see flags below) |
| `qoder-autopilot doctor` | 🩺 Health check — verify all dependencies & configs |
| `qoder-autopilot deploy` | Deploy your own temp mail worker |
| `qoder-autopilot relay` | Start relay server for remote 9Router |
| `qoder-autopilot config` | Show config help + available keys |
| `qoder-autopilot config show` | Show all current settings with source |
| `qoder-autopilot config get <key>` | Get a specific config value |
| `qoder-autopilot config set <key> <value>` | Set a config value |
| `qoder-autopilot config reset` | Reset all settings to defaults |

### Registration flags

| Flag | Description | Default |
|---|---|---|
| `-n`, `--count N` | Number of accounts to create (1-100) | `1` |
| `--manual-captcha` | Pause for manual captcha solving (forces non-headless) | `false` |
| `--no-headless` | Show browser windows | `false` |
| `--parallel` | Run all accounts concurrently | `false` |
| `--delay N` | Delay between sequential accounts | `30` |
| `--verbose`, `-v` | Show debug-level logs | `false` |
| `--quiet`, `-q` | Only show errors and warnings | `false` |
| `--dry-run` | Validate configuration and exit | `false` |
| `--proxy URL` | Proxy for browser (socks5://host:port, http://host:port) | `none` |
| `--format {text,json,csv}` | Output format for results | `text` |
| `--log-file PATH` | Write all logs to a file | `none` |
| `--no-oauth` | Skip 9Router OAuth, just register | `false` |
| `--parallel` | Run all accounts concurrently | `false` |
| `--delay N` | Delay between sequential accounts (seconds) | `30` |

## ⚙️ Configuration

Three-tier priority: **Environment variables** → **User config** (`~/.qoder-autopilot/config.json`) → **Defaults**

### Via CLI (recommended)

```bash
# See all settings
qoder-autopilot config show

# Set values
qoder-autopilot config set worker-url https://my-worker.workers.dev
qoder-autopilot config set ai-api-key sk-abc123...
qoder-autopilot config set otp-timeout 30
qoder-autopilot config set mail-provider moca

# Get a value
qoder-autopilot config get worker-url

# Reset everything
qoder-autopilot config reset
```

### Configurable keys

| Key | Description | Default |
|---|---|---|
| `mail-provider` | Temp mail provider: `cloudflare` or `moca` | `cloudflare` |
| `worker-url` | Cloudflare Worker URL | Built-in default |
| `moca-api-key` | Moca Supabase API key (`tmk_xxx`) | *(empty)* |
| `moca-base-url` | Moca Supabase base URL | *(built-in)* |
| `ai-api-key` | API key for AI captcha solver | *(empty)* |
| `ai-base-url` | OpenAI-compatible API base URL | `https://ai.sumopod.com/v1` |
| `ai-model` | AI model name | `gemini/gemini-2.5-flash` |
| `otp-timeout` | Max seconds to wait for OTP | `20` |
| `captcha-timeout` | Max seconds for manual captcha | `120` |
| `parallel-delay` | Delay between parallel accounts (sec) | `30` |
| `ninerouter-db` | Path to 9Router SQLite DB | OS-aware: `~/.9router/db/data.sqlite` (macOS/Linux), `%APPDATA%/9router/db/data.sqlite` (Windows) |

### Via environment variables

All keys can be set with `QODER_` prefix:

```bash
export QODER_WORKER_URL=https://my-worker.workers.dev
export QODER_AI_API_KEY=sk-abc123...
export QODER_OTP_TIMEOUT=30
```

### Via `.env` file

```bash
cp .env.example .env
# Edit .env with your settings
```

## 🏠 Self-Host Temp Mail Worker

Want your own independent temp mail service? Deploy in 5 minutes:

```bash
# From qoder-autopilot (bundled worker template)
qoder-autopilot deploy

# Or clone the standalone repo
git clone https://github.com/Daivageralda/cf-mail-worker.git
cd cf-mail-worker
npm install
npm run setup
```

See [cf-mail-worker](https://github.com/Daivageralda/cf-mail-worker) for full documentation.

## 🏗️ Architecture

```
qoder-autopilot/
├── src/qoder_autopilot/
│   ├── cli.py              # CLI entry point
│   ├── config.py           # Pydantic Settings (env + user config + defaults)
│   ├── user_config.py      # Persistent config manager (~/.qoder-autopilot/)
│   ├── first_run.py        # First-run setup wizard
│   ├── deploy.py           # Worker deploy (extract + setup)
│   ├── register.py         # Main registration flow
│   ├── temp_mail.py        # Multi-provider temp email client
│   ├── oauth.py            # PKCE device auth flow
│   ├── otp.py              # Email OTP extraction
│   ├── identity.py         # Random identity generation (faker id_ID)
│   ├── credentials.py      # Account credential storage
│   ├── ninerouter.py       # 9Router SQLite integration
│   ├── errors.py           # Custom exceptions
│   ├── logger.py           # ANSI colored structured logging
│   ├── browser/
│   │   ├── camoufox.py     # Anti-detect browser launcher
│   │   └── window_tiler.py # macOS window grid positioning
│   ├── captcha/
│   │   ├── solver.py       # Orchestrator (AI → manual)
│   │   ├── ai_vision.py    # AI vision gap detection
│   │   └── manual.py       # Manual solve pause/poll
│   └── worker_template/    # Bundled Cloudflare Worker (for deploy)
│       ├── src/             # Worker JS source
│       ├── schema.sql       # D1 database schema
│       ├── package.json
│       └── scripts/setup.sh
├── tests/
├── pyproject.toml
└── README.md
```

## 🔒 Security

qoder-autopilot takes security seriously:

- **Credential files** — `qoder_accounts.json` saved with `chmod 600` (owner-only)
- **Config files** — `~/.qoder-autopilot/config.json` and `relay.json` restricted to `600`
- **Password masking** — passwords never logged to stdout (masked as `••••••••`)
- **API key masking** — AI API keys never shown in logs (shown as `***configured***`)
- **Sensitive field masking** — `config show` masks API keys, tokens, and passwords
- **File locking** — concurrent credential writes are atomic (safe in `--parallel` mode)
- **Timing-safe auth** — relay token comparison uses `hmac.compare_digest()`
- **Rate limiting** — relay server limits to 30 requests/60s per IP
- **Input validation** — relay validates email format and field lengths via Pydantic
- **SQLite WAL mode** — safe concurrent access with `busy_timeout` (no connection leaks)
- **Secure default binding** — relay defaults to `127.0.0.1` (localhost only)
- **HTTPS warning** — startup warns when relay runs without TLS
- **Trust transparency** — first-run wizard warns about shared public worker

> **Recommendation:** For production use, always self-host your temp mail worker and use HTTPS (nginx/caddy) or SSH tunnel for relay.

## 🔗 Related

- [**cf-mail-worker**](https://github.com/Daivageralda/cf-mail-worker) — Self-hosted temp mail API (Cloudflare Workers + D1)
- [**bulk-temp-mail**](https://github.com/Daivageralda/temp-mail-generator) — Full temp mail service with React frontend

## 📄 License

MIT — see [LICENSE](LICENSE)

## ⚠️ Disclaimer

This tool is for educational and research purposes only. Use responsibly and in accordance with applicable terms of service.
