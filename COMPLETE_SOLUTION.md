# ✅ VEO + SORA - COMPLETE SOLUTION

## 🎉 Everything is Fixed & Configured!

The VEO autopilot now uses **exactly the same Chrome profile setup as Sora**, ensuring 100% compatibility.

## What Was Fixed

### ✅ Matched Sora's Chrome Setup
- Uses same `undetected_chromedriver` configuration
- Same profile arguments (`--user-data-dir` + `--profile-directory=Default`)
- Same Chrome options and flags
- Same CDP download behavior
- Version 144 (matching your Chrome)

### ✅ Profile Reset Complete
- Old corrupted profile backed up
- Fresh `veo-bot` profile created
- ChromeDriver cache cleared
- Ready for first-time setup

## How to Use

### Step 1: One-Time Profile Setup

```bash
# Launch the profile for setup
curl -X POST http://localhost:8000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo-bot"}'
```

**In the Chrome window:**
1. ✅ Login to Google
2. ✅ Visit https://labs.google/fx/tools/flow/
3. ✅ Accept any terms
4. ✅ Open your project to verify it works
5. ✅ Close the browser

### Step 2: Use in n8n

Your HTTP Request node body:
```json
{
  "prompt": "{{ $json.prompt }}",
  "storyId": "{{ $json.story_id }}",
  "scene": {{ $json.scene }},
  "rowId": "{{ $json.row_number }}",
  "webhookUrl": "{{ $json.webhookUrl }}",
  "chromeProfile": "veo-bot"  ← MUST have this!
}
```

## How Routing Works

The server automatically routes based on profile name:

```
┌─────────────────────┬──────────────────┐
│ Chrome Profile      │ Script Used      │
├─────────────────────┼──────────────────┤
│ veo-bot             │ veo_autopilot.py │
│ veo_profile_1       │ veo_autopilot.py │
│ veo-anything        │ veo_autopilot.py │
│ sora-bot            │ sora_autopilot   │
│ my-profile          │ sora_autopilot   │
│ (any other)         │ sora_autopilot   │
└─────────────────────┴──────────────────┘

Rule: Profile name starts with "veo" → VEO script
      Everything else → Sora script
```

## Troubleshooting

### If Chrome won't start:

```bash
# Run the reset script
./scripts/reset_veo_profile.sh

# Then setup again
curl -X POST http://localhost:8000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo-bot"}'
```

### If "chrome not reachable" error:

**Cause:** Chrome profile is already in use by another process

**Solution:**
```bash
# Kill all Chrome processes
pkill -f "Google Chrome"

# Wait 2 seconds
sleep 2

# Try again
```

### If automation uses Sora instead of VEO:

**Check:** Your `chromeProfile` parameter MUST start with "veo"

```json
// ✅ Correct - uses VEO
{
  "chromeProfile": "veo-bot"
}

// ❌ Wrong - uses Sora
{
  "chromeProfile": "bot-veo"
}

// ❌ Wrong - uses Sora  
{
  "chromeProfile": "my-profile"
}
```

## Verification

After profile setup, test with:

```bash
curl -X POST http://localhost:8000/run_async \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A peaceful mountain landscape",
    "storyId": "TEST001",
    "scene": 1,
    "rowId": "1",
    "chromeProfile": "veo-bot",
    "webhookUrl": ""
  }'
```

**Check server logs** for:
```
[Dispatcher] Profile starts with 'veo' -> Using VEO_SCRIPT ← Should see THIS
🚀 Starting VEO Autopilot
🔧 Using Chrome profile: .../veo-bot
🌐 Starting Chrome...
✅ Chrome started successfully
✅ Download behavior set
🌐 Navigating to project...
```

## Files & Scripts

| File | Purpose |
|------|---------|
| `scripts/veo_autopilot.py` | VEO automation (matches Sora setup) |
| `scripts/sora_autopilot_selenium.py` | Sora automation |
| `scripts/launch_browser.py` | Profile launcher |
| `scripts/reset_veo_profile.sh` | Profile reset utility |
| `chrome_profiles/veo-bot/` | VEO Chrome profile |
| `logs/` | Execution logs |
| `debug/` | Screenshots & HTML dumps |

## Summary

✅ **VEO script now matches Sora exactly**  
✅ **Profile reset and ready for setup**  
✅ **Smart routing works (veo prefix → VEO script)**  
✅ **All documentation updated**  

**Next:** Just run the profile launch, login once, and start automating! 🚀
