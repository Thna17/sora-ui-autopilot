Sora & VEO UI Autopilot
========================

Automates the Sora and Google Labs Flow (VEO) web UIs with Selenium and exposes a FastAPI server
for queueing prompt runs, managing Chrome profiles, and checking job status. The worker launches a local
Chrome profile, submits a prompt, waits for the render/export, and downloads
the output into `downloads/`.

Features
--------
- **Dual Platform Support**: Automate both Sora and Google Labs Flow (VEO) video generation
- **Smart Routing**: Automatically selects the correct script based on Chrome profile name
- **Chrome Profile Management**: Create, launch, and manage multiple Chrome profiles via API
- **FastAPI Server**: Async job queueing with `/run_async` and `/process` endpoints
- **Selenium Automation**: Robust UI automation with retries and debug artifacts
- **Webhook Callbacks**: Optional webhook notifications for job completion
- **Organized Output**: Videos saved to organized folders + copied to n8n integration folder

Requirements
------------
- Python 3.10+ recommended
- Google Chrome installed
- Sora access in the browser profile

Quick start
-----------
1) Create a virtual environment and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Start the API server:

```bash
uvicorn runner_server:app --reload --port 8000
```

3) Submit a job:

**For Sora** (use Chrome profile without "veo" prefix):
```bash
curl -X POST http://127.0.0.1:8000/run_async \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A slow cinematic pan across a neon city at night",
    "storyId": "story-001",
    "scene": 1,
    "rowId": "row-42",
    "chromeProfile": "sora_profile_1",
    "webhookUrl": ""
  }'
```

**For VEO/Flow** (use Chrome profile starting with "veo"):
```bash
curl -X POST http://127.0.0.1:8000/run_async \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A serene sunset over the ocean",
    "storyId": "STORY002",
    "scene": 1,
    "rowId": "STORY002_scene_001",
    "chromeProfile": "veo_profile_1",
    "webhookUrl": "http://localhost:5678/webhook/video_done"
  }'
```

4) Check status:

```bash
curl http://127.0.0.1:8000/status/<job_id>
```

Chrome Profile Management
--------------------------
Manage multiple Chrome profiles for Sora and VEO via API:

**List profiles:**
```bash
curl http://127.0.0.1:8000/list_profiles
```

**Create a new profile:**
```bash
curl -X POST http://127.0.0.1:8000/create_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo_profile_1"}'
```

**Launch profile for login:**
```bash
curl -X POST http://127.0.0.1:8000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo_profile_1"}'
```

**Delete a profile:**
```bash
curl -X POST http://127.0.0.1:8000/delete_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "veo_profile_1"}'
```

Configuration
-------------
### Sora Environment Variables
Runtime behavior can be tuned via environment variables:
- `SORA_PYTHON`: override python executable for the worker script.
- `SORA_SCRIPT`: override the worker script path.
- `SORA_WAIT_SECONDS`: post-submit wait time before polling library.
- `SORA_LIBRARY_POLL_SECONDS`: poll interval for new outputs.
- `SORA_LIBRARY_MAX_WAIT`: max time to wait for a new output.
- `SORA_EXPORT_SOFT_TIMEOUT`: initial export wait time.
- `SORA_EXPORT_GRACE_TIMEOUT`: additional export wait time.
- `SORA_DOWNLOAD_START_TIMEOUT`: timeout for detecting download start.
- `SORA_DOWNLOAD_WAIT_MIN`: minimum download wait time.
- `SORA_DOWNLOAD_WAIT_MAX`: maximum download wait time.

### VEO Environment Variables
- `VEO_SCRIPT`: override the VEO worker script path.
- `VEO_PROJECT_URL`: Flow project URL (default: preset project)
- `VEO_WAIT_SECONDS`: initial wait after submission (default: 90)
- `VEO_POST_SUBMIT_WAIT`: wait before checking completion (default: 10)
- `VEO_POLL_SECONDS`: polling interval (default: 15)
- `VEO_MAX_WAIT_SECONDS`: maximum generation wait time (default: 300)
- `VEO_EXPORT_TIMEOUT`: download export timeout (default: 45)
- `VEO_HEADLESS`: run Chrome in headless mode (default: false)

### Output Directories
- Videos are saved to `downloads/{STORY}/{scene}/`
- Videos are also copied to `/Users/macbookpro/.n8n-files/videos/` for n8n integration

Notes
-----
- The Selenium runner stores logs in `logs/` and debug artifacts in `debug/`.
- Downloads are saved to `downloads/`.
- Chrome profiles are stored in `chrome_profiles/` to keep sessions.
- Profile names starting with "veo" automatically route to VEO script.
- See [VEO_AUTOPILOT.md](VEO_AUTOPILOT.md) for detailed VEO documentation.
