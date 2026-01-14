# Playwright Session Persistence

Session persistence allows you to avoid re-logging into GitHub on every validation run.

## Quick Start

### 1. Initialize session (one-time setup)

```bash
python3 init_playwright_session.py
```

This will:

- Open a browser window at github.com
- Wait for you to log in (including 2FA)
- Save the session to `outputs/playwright_state.json`

### 2. Use the saved session

```bash
python3 validate_playwright.py '<stories>' --storage-state outputs/playwright_state.json
```

The script will:

- Load your saved session
- Skip the login prompt
- Run validation immediately
- Refresh the session state after each run

## How It Works

### Storage State

Playwright saves browser cookies, localStorage, and sessionStorage to a JSON file. When you load this file in a new browser session, you're already authenticated.

### Session Refresh

After each successful validation run, the script automatically updates the storage state file. This keeps your session fresh and prevents expiration.

### Backward Compatibility

The `--storage-state` flag is **optional**. If you don't use it, the script works exactly as before:

- Opens browser
- Prompts for login if needed
- Runs validation

## Advanced Usage

### Custom storage location

```bash
# Initialize to custom location
python3 init_playwright_session.py --output-path ~/my_github_session.json

# Use custom location
python3 validate_playwright.py '<stories>' --storage-state ~/my_github_session.json
```

### Check if session is still valid

Just run the init script again:

```bash
python3 init_playwright_session.py
```

If you're still logged in, it will immediately save the state and exit. If not, it will prompt you to log in.

## Troubleshooting

### "Session expired" errors

Run the init script to refresh:

```bash
python3 init_playwright_session.py
```

### Different GitHub account needed

Delete the state file and re-run init:

```bash
rm outputs/playwright_state.json
python3 init_playwright_session.py
```

### Multiple GitHub accounts

Use different state files:

```bash
# Work account
python3 init_playwright_session.py --output-path outputs/github_work.json

# Personal account
python3 init_playwright_session.py --output-path outputs/github_personal.json

# Use the right one
python3 validate_playwright.py '<stories>' --storage-state outputs/github_work.json
```

## Security Notes

- The storage state file contains authentication tokens
- Keep it secure (don't commit to git)
- The `outputs/` directory is already in `.gitignore`
- Sessions do expire after some time (GitHub security policy)

## File Locations

| File                            | Purpose                                        |
| ------------------------------- | ---------------------------------------------- |
| `init_playwright_session.py`    | One-time session initialization                |
| `validate_playwright.py`        | Validation script (supports `--storage-state`) |
| `outputs/playwright_state.json` | Default saved session location                 |
