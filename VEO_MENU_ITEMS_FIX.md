# VEO Menu Items Loading Fix - January 31, 2026

## Problem: Menu Items Not Found

### What Was Happening
The download menu would open successfully, but no menu items were being found inside it:

```
[20:41:29] ✅ Menu appeared
[20:41:29] 🔍 Searching for download menu item...
[20:41:29] ⚠️ Specific selectors failed, scanning all menu items...
[20:41:29] 📋 Found 0 menu items  ← PROBLEM!
```

## Root Cause

**Timing Issue**: The menu container appears quickly, but the items inside take a moment to render. The code was:
1. Opening the menu ✅
2. Seeing the menu container appear ✅
3. **Immediately** trying to find items ❌
4. Finding 0 items because they hadn't rendered yet ❌

## Solution Applied

### Fix #1: Wait for Menu Items After Menu Appears
Added a pause and verification step after the menu appears:

```python
if menu_found:
    # Wait a bit longer for menu items to render inside the menu
    logger.log("⏳ Waiting for menu items to load...")
    time.sleep(0.5)
    
    # Verify items are actually present
    max_retries = 3
    for retry in range(max_retries):
        try:
            items = driver.find_elements(By.CSS_SELECTOR, "[role='menuitem']")
            visible_items = [item for item in items if item.is_displayed()]
            if visible_items:
                logger.log(f"✅ Found {len(visible_items)} menu items ready")
                break
            else:
                logger.log(f"⏳ No items yet (attempt {retry + 1}/{max_retries}), waiting...")
                time.sleep(0.3)
        except Exception:
            time.sleep(0.3)
```

### Fix #2: Retry Menu Item Scanning
Enhanced `_click_download_menu_item()` to retry scanning if items aren't found:

```python
# Try multiple times in case items are still loading
max_scan_attempts = 3
items = []

for attempt in range(max_scan_attempts):
    try:
        items = driver.find_elements(By.CSS_SELECTOR, "[role='menuitem']")
        visible_items = [item for item in items if item.is_displayed()]
        
        if visible_items:
            logger.log(f"📋 Found {len(visible_items)} menu items")
            items = visible_items
            break
        else:
            logger.log(f"⏳ No visible items yet (scan attempt {attempt + 1}/{max_scan_attempts})")
            if attempt < max_scan_attempts - 1:
                time.sleep(0.4)
    except Exception as e:
        logger.log(f"⚠️ Error scanning menu items: {e}")
        if attempt < max_scan_attempts - 1:
            time.sleep(0.4)

if not items:
    logger.log("❌ No menu items could be found")
    return False
```

## Expected Behavior After Fix

```
[20:41:29] ✅ Menu appeared
[20:41:29] ⏳ Waiting for menu items to load...
[20:41:29] ✅ Found 4 menu items ready
[20:41:29] 🔍 Searching for download menu item...
[20:41:29] ⚠️ Specific selectors failed, scanning all menu items...
[20:41:29] 📋 Found 4 menu items
[20:41:29]   - Menu item: 'gif_box animated gif (270p)' (aria: '')
[20:41:29]   - Menu item: 'capture original size (720p)' (aria: '')
[20:41:29]   - Menu item: 'high_res upscaled (1080p)' (aria: '')
[20:41:29]   - Menu item: '4k upscaled (4k) upgrade' (aria: '')
[20:41:29] 🎬 No explicit download found, looking for quality/format options...
[20:41:29] ✅ Found quality option: 'capture original size (720p)' (preference: original)
[20:41:30] ✅ Clicked quality option: original
[20:41:31] ✅ Download started
```

## Key Improvements

1. ✅ **Wait 0.5s after menu appears** before looking for items
2. ✅ **Verify items are loaded** with up to 3 retries (0.3s each)
3. ✅ **Retry scanning** up to 3 times if items not found
4. ✅ **Better error messages** showing scan attempts
5. ✅ **Early exit** if no items found after all attempts

## Files Modified
- `/scripts/veo_autopilot.py`
  - `_open_menu_and_click_download()` - Added menu item loading wait
  - `_click_download_menu_item()` - Added retry logic for scanning

## Total Wait Time
- Menu appears: ~0.5s
- Verify items ready: ~0.9s (3 attempts × 0.3s max)
- Scan for items: ~1.2s (3 attempts × 0.4s max)
- **Total max wait**: ~2.6 seconds (minimal impact on performance)
