# Mac Validation Checklist

Use this for the first real Mac install/run validation pass.

## 1. Environment sanity check

```bash
python3 --version
python3 -m pip --version
claude --help
```

If the system `python3` is older than 3.11, install and use Homebrew Python 3.12 instead:

```bash
brew install python@3.12
/opt/homebrew/bin/python3.12 --version
```

## 2. Repo sanity check

From the repo root:

```bash
pwd
ls
```

Optional:

```bash
python3 -m pytest
```

If pytest is unavailable or the interpreter is too old, skip ahead to the venv setup below.

## 3. Install validation

Preferred Mac path:

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -e . pytest
.venv/bin/python -m app.assistant_cli --help
```

If `assistant` is on PATH and usable after install, you can also check:

```bash
assistant --help
```

If `assistant` is not on PATH yet:

```bash
./assistant.sh --help
```

## 4. Configure validation

```bash
.venv/bin/python -m app.assistant_cli configure
```

Fallback:

```bash
./assistant.sh configure
```

Then inspect the generated config:

```bash
cat ~/Library/Application\ Support/assistant/config/config.json
```

Check for:
- real Telegram token saved
- real allowed chat ID saved
- no placeholder junk
- seeded `project_root`, `agents_dir`, and `shared_dir`

## 5. Doctor validation

```bash
.venv/bin/python -m app.assistant_cli doctor
```

Fallback:

```bash
./assistant.sh doctor
```

Verify doctor reports:
- config exists
- canonical config path
- project root
- agents path
- shared path
- runtime PID / lock / log paths
- Claude CLI found
- default agent exists

## 6. Lifecycle validation

```bash
.venv/bin/python -m app.assistant_cli start
.venv/bin/python -m app.assistant_cli status
.venv/bin/python -m app.assistant_cli stop
.venv/bin/python -m app.assistant_cli status
```

Fallback:

```bash
./assistant.sh start
./assistant.sh status
./assistant.sh stop
./assistant.sh status
```

## 7. Log validation

Use the log path reported by `assistant doctor`.

Example:

```bash
tail -n 50 <log-path>
```

Look for:
- startup logging
- config/load failures
- lock issues
- Claude CLI issues
- Telegram API issues

## 8. Telegram smoke test

If start succeeds, send a real message to the bot and try:
- `/status`
- `/agent`
- `/agents`

## 9. Repo-launcher fallback check

```bash
./assistant.sh status
./assistant.sh doctor
```

## What to record

- whether system Python was sufficient or Homebrew Python 3.12 was needed
- whether a `.venv` was needed
- install success / PATH issue
- configure behavior
- doctor warnings/failures
- start/status/stop behavior
- runtime log errors
- Telegram round-trip result
- whether another machine had to be stopped because it was polling the same Telegram bot token
