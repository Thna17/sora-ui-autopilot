# VEO Autopilot Quick Reference

## ⚡ Quick Start (Copy & Paste)

### 1. Create VEO Profile
```bash
curl -X POST http://localhost:8000/create_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo_profile_1"}'
```

### 2. Launch & Login
```bash
curl -X POST http://localhost:8000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo_profile_1"}'
```
→ Login to Google, accept Flow terms, close browser

### 3. Submit VEO Job
```bash
curl -X POST http://localhost:8000/run_async \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Your video prompt here",
    "storyId": "STORY002",
    "scene": 1,
    "rowId": "STORY002_scene_001",
    "chromeProfile": "veo_profile_1",
    "webhookUrl": "http://localhost:5678/webhook/video_done"
  }'
```

### 4. Check Status
```bash
curl http://localhost:8000/status/<job_id_from_step_3>
```

---

## 🎯 Key Points

- ✅ Profile name **must start with "veo"** to route to VEO script
- ✅ Videos saved to: `downloads/STORY002/scene_001/STORY002_scene_001.mp4`
- ✅ Auto-copied to: `/Users/macbookpro/.n8n-files/videos/STORY002_final.mp4`
- ✅ Logs saved to: `logs/veo_STORY002_scene_001_TIMESTAMP.txt`

---

## 🔧 Optional: Set Custom Project URL

```bash
export VEO_PROJECT_URL="https://labs.google/fx/tools/flow/project/YOUR_PROJECT_ID"
# Restart runner_server after setting this
```

Default: `https://labs.google/fx/tools/flow/project/a443eb39-ba91-46b8-9d06-253a09ccb603`

---

## 📋 Profile Management

```bash
# List all profiles
curl http://localhost:8000/list_profiles

# Create profile
curl -X POST http://localhost:8000/create_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "PROFILE_NAME"}'

# Launch profile for setup
curl -X POST http://localhost:8000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "PROFILE_NAME"}'

# Delete profile
curl -X POST http://localhost:8000/delete_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "PROFILE_NAME"}'
```

---

## 🏷️ Naming Convention

| Profile Name | Routes To |
|-------------|-----------|
| `veo_*` | VEO Script (Google Labs Flow) |
| `sora_*` or other | Sora Script |

Examples:
- ✅ `veo_profile_1` → VEO
- ✅ `veo_production` → VEO  
- ✅ `sora_main` → Sora
- ✅ `my_profile` → Sora

---

## 🔍 Debugging

```bash
# View logs
tail -f logs/veo_STORY002_scene_001_TIMESTAMP.txt

# View debug screenshots
open debug/

# Check if server is running
curl http://localhost:8000/routes
```

---

## ⚙️ Environment Variables (Optional)

```bash
# Set before starting runner_server
export VEO_PROJECT_URL="https://labs.google/fx/tools/flow/project/YOUR_ID"
export VEO_WAIT_SECONDS=90
export VEO_MAX_WAIT_SECONDS=300
export VEO_POLL_SECONDS=15
export VEO_HEADLESS=false
```

---

## 📖 Full Documentation

- **VEO_IMPLEMENTATION_SUMMARY.md** - Complete implementation details
- **VEO_AUTOPILOT.md** - Detailed VEO documentation
- **README.md** - Main project documentation

---

## 🎬 Example: Complete Workflow

```bash
# 1. Create profile (once)
curl -X POST http://localhost:8000/create_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo_profile_1"}'

# 2. Launch and login (once)
curl -X POST http://localhost:8000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo_profile_1"}'
# → Complete login in browser window that opens
# → Close browser when done

# 3. Run automation (as many times as needed)
curl -X POST http://localhost:8000/run_async \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A peaceful mountain landscape at dawn",
    "storyId": "STORY002", 
    "scene": 1,
    "rowId": "STORY002_scene_001",
    "chromeProfile": "veo_profile_1",
    "webhookUrl": "http://localhost:5678/webhook/video_done"
  }'

# Save the jobId from response
# {"ok": true, "jobId": "abc123...", ...}

# 4. Check status
curl http://localhost:8000/status/abc123

# 5. When finished, video will be at:
# - downloads/STORY002/scene_001/STORY002_scene_001.mp4
# - /Users/macbookpro/.n8n-files/videos/STORY002_final.mp4
```

---

**Ready to automate! 🚀**
