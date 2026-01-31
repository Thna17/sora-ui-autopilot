# ChromeDriver Version Troubleshooting Guide

## Problem: ChromeDriver Version Mismatch

If you see errors like:
```
This version of ChromeDriver only supports Chrome version 145
Current browser version is 144.0.7559.110
```

This means your ChromeDriver and Chrome browser versions don't match.

## Solutions (Recommended Order)

### Solution 1: Use webdriver-manager (Recommended ✅)

We've updated the VEO autopilot to automatically use `webdriver-manager` which handles version matching automatically.

**Install it:**
```bash
source .venv/bin/activate
pip install webdriver-manager
```

**Done!** The VEO script will now auto-download and use the correct ChromeDriver version.

### Solution 2: Update Chrome Browser

Update Chrome to match ChromeDriver version 145:

**On Mac:**
```bash
# Open Chrome
# Go to: Chrome > About Google Chrome
# It will auto-update to latest version
```

Or use Homebrew:
```bash
brew upgrade --cask google-chrome
```

### Solution 3: Downgrade ChromeDriver (Not Recommended)

Only if solutions 1 & 2 don't work:

```bash
# Find your Chrome version
google-chrome --version
# or: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version

# Download matching ChromeDriver from:
# https://googlechromelabs.github.io/chrome-for-testing/

# Replace the existing ChromeDriver in your PATH
```

## For launch_browser.py

The `launch_browser.py` uses `undetected_chromedriver` which should auto-detect versions.

If it still fails:

**Option 1: Reinstall undetected_chromedriver**
```bash
source .venv/bin/activate
pip uninstall undetected_chromedriver
pip install undetected_chromedriver
```

**Option 2: Clear ChromeDriver cache**
```bash
rm -rf ~/.undetected_chromedriver
```

## Verification

Test if the fix worked:

```bash
# Test VEO profile launch
curl -X POST http://localhost:8000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo-bot"}'

# Check the terminal output - should see "Browser launched" message
```

## Current Status

✅ **VEO Autopilot**: Now uses webdriver-manager (auto version matching)  
✅ **Launch Browser**: Uses undetected_chromedriver (auto version detection)  
✅ **Routes Endpoint**: Fixed to handle Mount objects

## Prevention

To avoid this in the future:

1. **Keep webdriver-manager installed** - It auto-manages versions
2. **Update Chrome regularly** - Most automation tools support latest Chrome
3. **Use virtual environments** - Isolates dependencies per project

## Alternative: Use Docker

For production/consistent environments, consider using Chrome in Docker:

```dockerfile
FROM selenium/standalone-chrome:latest
# Your automation code here
```

This ensures Chrome and ChromeDriver versions always match.
