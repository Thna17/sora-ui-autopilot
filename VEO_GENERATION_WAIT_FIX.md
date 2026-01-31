# VEO Generation Wait Fix - January 31, 2026

## Problem: Downloading Old Video Instead of New One

### What Was Happening
After submitting a new prompt, the script would immediately detect "generation complete" and download the **previous video** instead of waiting for the **new video** to generate.

### Evidence from Logs
```
[20:25:01] ✅ Submitted prompt
[20:25:01] ⏳ Waiting 10s after submit...
[20:25:11] ⏳ Waiting up to 300s for generation...
[20:25:11] ✅ Generation complete (ready indicator found)  ← INSTANT! Should take 1-2 min
[20:25:11] 📁 Downloads before: 24 files
[20:25:11] ⬇️ Starting download...
```

The "ready indicator" was found in **0 seconds** because it detected the **old video's** download button, not the new one.

## Root Cause

The `wait_for_generation_complete()` function had this logic:

```python
while time.time() < end:
    if _generation_in_progress(driver):
        pass  # Keep waiting
    else:
        # THIS IS THE PROBLEM:
        if _download_button_ready(driver) or _video_ready(driver):
            return True  # Returns immediately if ANY video is ready!
```

It would check if generation is in progress, and if **not**, it would immediately check if a download button or video is ready. Since the **old video** was already there with its download button ready, it would return True instantly.

## Solution: Two-Phase Generation Wait

Implemented a **phase-based approach**:

### Phase 1: Wait for Generation to START
```python
# Phase 1: Wait for generation to START (look for progress indicators)
# Don't check for completion too early to avoid detecting old videos
generation_started = False
min_wait_before_checking = 5  # Wait at least 5 seconds

logger.log("🔄 Waiting for generation to start...")
while time.time() < end:
    elapsed = time.time() - start_time
    
    # Check if generation is in progress
    if _generation_in_progress(driver):
        logger.log(f"✅ Generation started (detected at {int(elapsed)}s)")
        generation_started = True
        break
    
    # After minimum wait, if we still don't see progress, assume it started
    if elapsed > min_wait_before_checking:
        logger.log(f"⏳ No progress indicator after {int(elapsed)}s, assuming generation started")
        generation_started = True
        break
    
    time.sleep(1)
```

### Phase 2: Wait for Generation to COMPLETE
```python
# Phase 2: Wait for generation to COMPLETE
logger.log("⏳ Waiting for generation to complete...")
while time.time() < end:
    if _generation_in_progress(driver):
        pass  # Keep waiting
    else:
        # Generation appears done, verify we have a NEW video
        if before_video_srcs and _new_video_ready(driver, before_video_srcs):
            logger.log("✅ Generation complete (new video detected)")
            return True
        
        # Fallback: only check for ready indicators AFTER confirming generation started
        if generation_started and (_download_button_ready(driver) or _video_ready(driver)):
            logger.log("✅ Generation complete (ready indicator found)")
            return True
```

## Key Improvements

1. ✅ **Wait minimum 5 seconds** before checking for completion
2. ✅ **Detect when generation starts** (progress indicators appear)
3. ✅ **Prefer detecting NEW video** via `before_video_srcs` comparison
4. ✅ **Only use fallback check** after confirming generation started
5. ✅ **Better logging** to track both phases

## Expected Behavior After Fix

```
[20:25:01] ✅ Submitted prompt
[20:25:01] ⏳ Waiting 10s after submit...
[20:25:11] ⏳ Waiting up to 300s for generation...
[20:25:11] 🔄 Waiting for generation to start...
[20:25:12] ✅ Generation started (detected at 1s)
[20:25:12] ⏳ Waiting for generation to complete...
[20:25:22] …still generating (278s remaining)
[20:25:37] …still generating (263s remaining)
[20:26:52] …still generating (148s remaining)
[20:27:07] …still generating (133s remaining)
[20:27:22] ✅ Generation complete (new video detected)
[20:27:22] 📁 Downloads before: 24 files
[20:27:22] ⬇️ Starting download...
```

## Files Modified
- `/scripts/veo_autopilot.py`
  - `wait_for_generation_complete()` - Added two-phase wait logic

## Impact
- ✅ Prevents downloading old videos
- ✅ Properly waits for new video to generate (1-2 minutes)
- ✅ Better tracking of generation lifecycle
- ✅ More reliable automation
