Sora UI Autopilot
=================

Automates the Sora web UI with Selenium and exposes a small FastAPI server
for queueing prompt runs and checking status. The worker launches a local
Chrome profile, submits a prompt, waits for the render/export, and downloads
the output into `downloads/`.

Features
--------
- FastAPI server with async job queueing.
- Selenium-based Sora UI automation with retries and debug artifacts.
- Webhook callback support (optional) for job completion.

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

```bash
curl -X POST http://127.0.0.1:8000/run_async \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A slow cinematic pan across a neon city at night",
    "storyId": "story-001",
    "scene": 1,
    "rowId": "row-42",
    "webhookUrl": ""
  }'
```

4) Check status:

```bash
curl http://127.0.0.1:8000/status/<job_id>
```

Configuration
-------------
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

Notes
-----
- The Selenium runner stores logs in `logs/` and debug artifacts in `debug/`.
- Downloads are saved to `downloads/`.
- The Chrome profile is stored in `chrome_profile/` to keep sessions.
