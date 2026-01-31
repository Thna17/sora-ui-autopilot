# Runner Server Error Handling Fix - January 31, 2026

## Problem: Jobs Running But Failing Silently

### What Was Happening
When the `/run_async` endpoint was called, it would return 200 OK but:
- No Chrome browser would open
- No log files would be created
- No errors were visible

```
[Dispatcher] Profile starts with 'veo' -> Using VEO_SCRIPT: ...
INFO:     127.0.0.1:65463 - "POST /run_async HTTP/1.1" 200 OK
```

But nothing happened after that.

## Root Causes

### Issue #1: NoneType Error on chrome_profile
At line 125 in `runner_server.py`:
```python
if chrome_profile.lower().startswith("veo"):
```

If `chromeProfile` wasn't provided in the request, `chrome_profile` would be an empty string or None, causing an `AttributeError` when calling `.lower()`. Since the job runs in a **daemon thread**, this error was silently swallowed.

### Issue #2: No Error Logging in Background Thread
The `run_job_background()` function had no try-except wrapper, so any errors would crash the thread silently without logging.

## Solutions Applied

### Fix #1: Safe Chrome Profile Checking
Added proper None/empty string checking:

```python
# OLD CODE (crashes if chrome_profile is empty)
if chrome_profile.lower().startswith("veo"):
    target_script = VEO_SCRIPT

# NEW CODE (safe checking)
if chrome_profile and chrome_profile.lower().startswith("veo"):
    target_script = VEO_SCRIPT
```

### Fix #2: Exception Handling Wrapper
Wrapped entire `run_job_background()` function in try-except:

```python
def run_job_background(job_id: str, job: Job):
    try:
        # ... all the job logic ...
        
    except Exception as e:
        import traceback
        error_msg = f"Job {job_id} crashed: {e}\n{traceback.format_exc()}"
        print(f"[ERROR] {error_msg}", flush=True)
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["finished_at"] = time.time()
        JOBS[job_id]["result"] = {
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
```

### Fix #3: Better Logging
Added command logging to see what's actually executing:

```python
cmd = [PYTHON, target_script, prompt, row_id, story_id, str(scene)]
print(f"[Job {job_id}] Running: {' '.join(cmd[:2])} ...", flush=True)
proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
```

Also added `flush=True` to all print statements to ensure immediate console output.

## Expected Behavior After Fix

### Successful Job
```
[Dispatcher] Profile starts with 'veo' -> Using VEO_SCRIPT: /path/to/veo_autopilot.py
[Job abc123] Running: /path/to/python /path/to/veo_autopilot.py ...
INFO:     127.0.0.1:65463 - "POST /run_async HTTP/1.1" 200 OK
```

Then Chrome opens and the VEO script runs normally.

### Job with Error
```
[Dispatcher] Using SORA_SCRIPT: /path/to/sora_autopilot.py
[Job abc123] Running: /path/to/python /path/to/sora_autopilot.py ...
[ERROR] Job abc123 crashed: AttributeError: 'NoneType' object has no attribute 'lower'
Traceback (most recent call last):
  File "/path/to/runner_server.py", line 125, in run_job_background
    ...
INFO:     127.0.0.1:65463 - "POST /run_async HTTP/1.1" 200 OK
```

Now you can see exactly what went wrong!

## Files Modified
- `/runner_server.py`
  - `run_job_background()` - Added try-except wrapper and better logging
  - Chrome profile checking - Added None safety check

## How to Check Job Status

You can now check job status via the API:
```bash
curl http://localhost:8000/status/{job_id}
```

This will return:
- `status`: "queued", "running", "done", or "error"
- `result`: The job result (including error/traceback if failed)
- Timestamps for created/started/finished

## Testing

1. Start the server: `uvicorn runner_server:app --reload --port 8000`
2. Send a test request with VEO profile:
```bash
curl -X POST http://localhost:8000/run_async \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Test prompt",
    "storyId": "TEST001",
    "scene": 1,
    "rowId": "test",
    "chromeProfile": "veo-bot"
  }'
```
3. Watch the server logs - you should see:
   - `[Dispatcher] Profile starts with 'veo' -> Using VEO_SCRIPT: ...`
   - `[Job ...] Running: ...`
   - Chrome opening and script executing
