# VEO Download Fix - January 31, 2026

## Problem Summary
The VEO autopilot was failing to download videos with the following error sequence:
1. Video generation completed successfully ✅
2. Download button was found ✅  
3. Click on download button succeeded (via `js_click`) ✅
4. **Download never started** ❌
5. Timeout after 16 seconds waiting for download

The logs showed:
```
[20:14:44] 🖱️ Attempting hard_click on button
[20:14:45] ⚠️ normal_click failed: ... element click intercepted
[20:14:46] ✅ Click succeeded via js_click
[20:14:47] ⏳ Waiting for download to start...
[20:15:03] ❌ Download didn't start within timeout
```

## Root Cause Analysis

### Issue #1: Menu Button Not Recognized
The download button had `aria-haspopup="menu"`, meaning it opens a **dropdown menu** rather than directly downloading. The original code:
1. Clicked the button (opening the menu)
2. Waited **15 seconds** for a download to start
3. Only **then** tried to find and click the actual download menu item
4. But by that time, the menu had closed or timed out

### Issue #2: Quality Selection Menu Not Expected
After fixing Issue #1, we discovered the menu doesn't contain a "Download" item at all! Instead, it shows **quality/format options**:
```
📋 Found 4 menu items
  - Menu item: 'gif_box animated gif (270p)' 
  - Menu item: 'capture original size (720p)' ← The download trigger!
  - Menu item: 'high_res upscaled (1080p)'
  - Menu item: '4k upscaled (4k) upgrade'
```

Clicking any of these quality options triggers the download in that format.

## Solution Applied

### Fix #1: **Detect Menu Buttons Upfront** (`download_video` function)
Added logic to detect if the download button opens a menu by checking `aria-haspopup` attribute:
```python
# Check if button opens a menu (aria-haspopup="menu")
is_menu_button = False
try:
    aria_haspopup = (download_btn.get_attribute("aria-haspopup") or "").lower()
    is_menu_button = (aria_haspopup == "menu")
    if is_menu_button:
        logger.log("🔽 Download button opens a menu")
except Exception:
    pass
```

### Fix #2: **Handle Menu Buttons Immediately**
Instead of waiting 15 seconds, if we detect a menu button, we immediately try to click the menu item:
```python
if is_menu_button:
    logger.log("🔍 Looking for download menu item...")
    if _open_menu_and_click_download(driver, logger, download_btn):
        time.sleep(1.5)
        started = wait_for_download_start(logger, before_files, timeout=16)
    else:
        logger.log("⚠️ Could not find download menu item")
```

### Fix #3: **Recognize Quality Selection Menus** (`_click_download_menu_item`)
Enhanced the function to:
1. First try to find explicit "Download", "Export", or "Save" items
2. **If none found**, recognize quality/format options as download triggers
3. Click the most appropriate quality option with this preference order:
   - `original` (720p) - Best native quality
   - `720p` - Native resolution
   - `1080p` - Upscaled quality
   - `4k` - Maximum upscaled quality
   - `gif` - Animated GIF format

```python
# Second pass: if no explicit download found, look for quality options
logger.log("🎬 No explicit download found, looking for quality/format options...")
preferred_order = ["original", "720p", "1080p", "4k", "gif"]

for preference in preferred_order:
    for item in items:
        if preference in combined:
            logger.log(f"✅ Found quality option: '{text}' (preference: {preference})")
            if hard_click(driver, item, logger):
                logger.log(f"✅ Clicked quality option: {preference}")
                return True
```

### Fix #4: **Enhanced Menu Interaction Logging** (`_open_menu_and_click_download`)
Added comprehensive logging to track each step:
- Opening the menu
- Waiting for menu to appear
- Finding menu items
- Clicking the download option

## Expected Behavior After Fix
```
[20:21:26] ⬇️ Starting download...
[20:21:26] ✅ Found download button in video tile
[20:21:26] 🔽 Download button opens a menu
[20:21:26] 🖱️ Attempting hard_click on button
[20:21:28] ✅ Click succeeded via js_click
[20:21:29] 🔍 Looking for download menu item...
[20:21:29] 📂 Opening download menu...
[20:21:35] ✅ Menu clicked via ActionChains
[20:21:35] ⏳ Waiting for menu to appear...
[20:21:35] ✅ Menu appeared
[20:21:35] 🔍 Searching for download menu item...
[20:21:35] 📋 Found 4 menu items
[20:21:35]   - Menu item: 'capture original size (720p)' (aria: '')
[20:21:35] 🎬 No explicit download found, looking for quality/format options...
[20:21:35] ✅ Found quality option: 'capture original size (720p)' (preference: original)
[20:21:35] ✅ Clicked quality option: original
[20:21:36] ⏳ Waiting for download to start...
[20:21:37] ✅ Download started
[20:21:58] ✅ Download complete
```

## Files Modified
- `/Users/macbookpro/Desktop/Project - Coding/sora-autopilot/sora-ui-autopilot/scripts/veo_autopilot.py`
  - `download_video()` - Added menu button detection
  - `_open_menu_and_click_download()` - Enhanced logging
  - `_click_download_menu_item()` - Added quality/format selection recognition

## Testing Recommendation
Run the VEO autopilot again with the same story/scene to verify the download now completes successfully. The enhanced logging will provide clear visibility into each step of the download process.

