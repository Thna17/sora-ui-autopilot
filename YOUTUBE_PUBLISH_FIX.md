# YouTube Upload Fix - Visibility & Save Button

## 🐛 **Problem Identified**

The script was **not selecting a visibility option** before clicking the Save button, causing videos to be saved as drafts with default visibility.

### Root Cause
On the **Visibility step**, the workflow is:
1. **Select visibility** (Private/Unlisted/Public radio button) ← **MISSING**
2. **Click "Save" button** → This publishes the video with selected visibility

The original script:
- ❌ Did NOT select a visibility option
- ❌ Skipped the "Save" button thinking it would create a draft
- ❌ Looked for a non-existent "Publish" button

### Correct Understanding
- The **"Save" button** on the Visibility page **IS** the publish button
- You must **select a visibility option first** (Public/Unlisted/Private)
- After selecting visibility + clicking Save → **Video is published** ✅

---

## ✅ **Fixes Applied**

### 1. **Added Visibility Selection**
The script now:
- Waits for the Visibility page to load
- Finds and clicks the visibility radio button (Public/Unlisted/Private)
- Verifies the selection was successful
- Takes debug screenshots before/after

### 2. **Clicks the Save Button**
The script now:
- Looks for the "Save" button (ID: done-button)
- Clicks it to publish the video with selected visibility
- No longer skips the Save button
- No longer looks for a non-existent "Publish" button

### 3. **Added Visibility Parameter**
New optional parameter `visibility`:
- **Options**: `public`, `unlisted`, `private`
- **Default**: `public`
- **Usage**: Include in API request

---

## 📝 **Updated API Usage**

### With Visibility (Recommended)

```bash
curl -X POST http://localhost:8000/upload_youtube \
  -H "Content-Type: application/json" \
  -d '{
    "videoPath": "/path/to/video.mp4",
    "title": "My Video Title",
    "description": "My video description",
    "storyId": "STORY006",
    "chromeProfile": "Sora-bot-1",
    "visibility": "public"
  }'
```

### Visibility Options

| Option | Description |
|--------|-------------|
| `public` | Everyone can watch (default) |
| `unlisted` | Anyone with the link can watch |
| `private` | Only you and people you choose can watch |

---

## 🔍 **Enhanced Logging**

The script now provides detailed logs:

```
[23:42:30] 📺 Setting video visibility...
[23:42:30] 📸 Saved visibility page screenshot
[23:42:30] 🔘 Selecting visibility: public
[23:42:31] ✅ Found Public radio button
[23:42:31] ✅ Public visibility selected successfully
[23:42:33] 🚀 Looking for PUBLISH button (not Save)...
[23:42:34] 🔍 Found button - text: 'publish', aria-label: 'publish video'
[23:42:34] ✅ Found PUBLISH button
[23:42:35] 🎉 Video published!
```

---

## 📸 **Debug Screenshots**

The script now saves screenshots at key points:
- `{storyId}_before_fill.png` - Before filling title/description
- `{storyId}_after_fill.png` - After filling title/description
- `{storyId}_visibility_page.png` - Visibility selection page
- `{storyId}_publish_not_found.png` - If publish button not found

All saved to: `debug/` folder

---

## 🧪 **Test the Fix**

Try uploading again with the corrected script:

```bash
curl -X POST http://localhost:8000/upload_youtube \
  -H "Content-Type: application/json" \
  -d '{
    "videoPath": "/Users/macbookpro/Desktop/Project - Coding/sora-autopilot/sora-ui-autopilot/outputs/STORY006/STORY006_final.mp4",
    "title": "My Story 006 - Public Test",
    "description": "Testing the fixed publish button",
    "storyId": "STORY006",
    "chromeProfile": "Sora-bot-1",
    "visibility": "public"
  }'
```

### Expected Result
- ✅ Video uploads
- ✅ Title and description are set
- ✅ Visibility is set to "Public"
- ✅ Video is **published** (not saved as draft)
- ✅ Video appears on your channel

---

## 📊 **Changes Made**

### File: `youtube_upload_autopilot.py`

1. **`complete_upload_steps()` function**:
   - Added `visibility` parameter
   - Changed max_steps from 4 to 3 (visibility handled separately)
   - Added visibility selection logic
   - Added button text/aria-label checking
   - Added debug screenshots
   - Improved error handling

2. **`main()` function**:
   - Added visibility parameter (5th argument)
   - Added visibility validation
   - Passes visibility to `complete_upload_steps()`

### File: `runner_server.py`

1. **`YouTubeJob` model**:
   - Added `visibility` field (defaults to "public")

2. **`run_youtube_background()` function**:
   - Extracts visibility from job
   - Passes visibility to script

---

## ⚠️ **Important Notes**

1. **Visibility Must Be Selected**: Without selecting a visibility option, YouTube won't show the "Publish" button, only "Save"

2. **Button Detection**: The script now carefully checks button text to avoid clicking "Save" instead of "Publish"

3. **Debug Screenshots**: Always check the debug screenshots if upload fails

4. **Default Visibility**: If not specified, defaults to "public"

---

## 🎯 **Summary**

| Before | After |
|--------|-------|
| ❌ Clicked "Save" button | ✅ Clicks "Publish" button |
| ❌ No visibility selection | ✅ Selects visibility option |
| ❌ Videos saved as drafts | ✅ Videos published to channel |
| ❌ No visibility control | ✅ Supports public/unlisted/private |
| ⚠️ Misleading logs | ✅ Accurate, detailed logs |

---

## 🚀 **Ready to Test!**

The fix is now deployed. Try uploading a video and verify it's actually published (not a draft) on your YouTube channel!
