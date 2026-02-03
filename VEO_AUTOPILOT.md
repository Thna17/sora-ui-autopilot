# VEO Autopilot - Google Labs Flow Integration

## Overview

The `veo_autopilot.py` script automates video generation using Google Labs Flow (Veo). It follows a similar workflow to Sora but adapted for Flow's UI structure.

## Key Differences: Sora vs Flow

### Sora
- Multiple routes (explore, drafts, library)
- Navigate between pages to check generation status
- Download from detail page via overflow menu

### Flow
- Single project URL contains everything
- All functionality in one page
- Video generation and download in same view

## Workflow

1. **Navigate to Project** - Opens the specified Flow project URL
2. **Submit Prompt** - Finds input field, pastes prompt, and submits
3. **Wait for Generation** - Polls for completion indicators (download button, video element)
4. **Download Video** - Clicks download button or uses overflow menu
5. **Save & Copy** - Saves to organized folder + copies to n8n folder

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VEO_PROJECT_URL` | `https://labs.google/fx/tools/flow/project/a443eb39-ba91-46b8-9d06-253a09ccb603` | Flow project URL |
| `SORA_CHROME_PROFILE` | - | Chrome profile path (set by runner_server) |
| `VEO_WAIT_SECONDS` | 90 | Initial wait after submission |
| `VEO_POST_SUBMIT_WAIT` | 10 | Wait before checking for completion |
| `VEO_POLL_SECONDS` | 15 | Polling interval for generation status |
| `VEO_MAX_WAIT_SECONDS` | 300 | Maximum wait for generation (5 min) |
| `VEO_EXPORT_TIMEOUT` | 45 | Download export timeout |
| `VEO_HEADLESS` | false | Run Chrome in headless mode |

## Usage

### Via Runner Server (Recommended)

The `runner_server.py` automatically routes to VEO script when using a Chrome profile that starts with "veo".

```bash
# Example POST request to /run_async
curl -X POST http://localhost:8000/run_async \
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

### Direct Execution

```bash
# Basic usage
python scripts/veo_autopilot.py "prompt text" "STORY002_scene_001" "STORY002" 1

# Frames to Video (two images)
python scripts/veo_autopilot.py "prompt text" "STORY002_scene_001" "STORY002" 1 \
  "/path/to/frame_1.png" "/path/to/frame_2.png"

# With custom project URL
VEO_PROJECT_URL="https://labs.google/fx/tools/flow/project/YOUR_PROJECT_ID" \
python scripts/veo_autopilot.py "prompt text" "STORY002_scene_001" "STORY002" 1

# With Chrome profile
SORA_CHROME_PROFILE="/path/to/chrome/profile" \
python scripts/veo_autopilot.py "prompt text" "STORY002_scene_001" "STORY002" 1
```

## Output Structure

### Downloaded Videos

Videos are organized by story and scene:

```
downloads/
  └── STORY002/
      └── scene_001/
          └── STORY002_scene_001.mp4
```

### n8n Copy

Videos are also copied to the n8n folder for workflow integration:

```
/Users/macbookpro/.n8n-files/videos/
  └── STORY002_final.mp4
```

### Logs

Detailed logs are saved for debugging:

```
logs/
  └── veo_STORY002_scene_001_20260131_011532.txt
```

## Chrome Profile Setup

1. **Create a VEO Profile**
   ```bash
   curl -X POST http://localhost:8000/create_profile \
     -H "Content-Type: application/json" \
     -d '{"name": "veo_profile_1"}'
   ```

2. **Launch and Login**
   ```bash
   curl -X POST http://localhost:8000/launch_profile \
     -H "Content-Type: application/json" \
     -d '{"name": "veo_profile_1"}'
   ```
   
   - Login to your Google account
   - Navigate to Google Labs Flow and accept any terms
   - Close the browser

3. **Use in Automation**
   - The profile is now ready for `chromeProfile: "veo_profile_1"`

## Project URL Management

### Default Project

The default project URL is set in the script. To change it:

```python
DEFAULT_PROJECT_URL = "https://labs.google/fx/tools/flow/project/YOUR_PROJECT_ID"
```

### Per-Request Project URL

Set the environment variable before running:

```bash
export VEO_PROJECT_URL="https://labs.google/fx/tools/flow/project/YOUR_PROJECT_ID"
```

### Finding Your Project URL

1. Go to Google Labs Flow
2. Create or open a project
3. Copy the URL from your browser
4. Format: `https://labs.google/fx/tools/flow/project/{PROJECT_ID}`

## Return Format

The script outputs a JSON result to stdout with marker `__RESULT__=`:

```json
{
  "ok": true,
  "started": true,
  "finished": true,
  "downloaded_path": "/path/to/downloads/STORY002/scene_001/STORY002_scene_001.mp4",
  "downloaded_filename": "STORY002_scene_001.mp4",
  "n8n_path": "/Users/macbookpro/.n8n-files/videos/STORY002_final.mp4",
  "log_file": "/path/to/logs/veo_STORY002_scene_001_20260131_011532.txt",
  "download_dir": "/path/to/downloads",
  "elapsed": 125.43
}
```

### Error Format

```json
{
  "ok": false,
  "error": "Error message here",
  "finished": false,
  "log_file": "/path/to/logs/veo_STORY002_scene_001_20260131_011532.txt",
  "elapsed": 45.12
}
```

## Troubleshooting

### Download Button Not Found

The script tries multiple strategies:
1. Direct download button (aria-label, title)
2. Button with "Download" text
3. Overflow menu with download option

Check the debug files:
- `debug/{timestamp}_generation_timeout.png`
- `debug/{timestamp}_generation_timeout.html`

### Generation Timeout

Increase wait times:
```bash
export VEO_MAX_WAIT_SECONDS=600  # 10 minutes
export VEO_POLL_SECONDS=20       # Check every 20 seconds
```

### Chrome Profile Issues

Ensure profile path is correct:
```bash
# Check profile exists
ls -la chrome_profiles/veo_profile_1

# Verify in runner_server logs
# Should see: "Using Chrome profile: /path/to/chrome_profiles/veo_profile_1"
```

### Video Generation Not Starting

1. Check if prompt was submitted (see logs)
2. Verify project URL is accessible
3. Ensure Chrome profile is logged in
4. Check for Flow UI changes (selectors may need updates)

## Integration with n8n

The script automatically copies videos to `/Users/macbookpro/.n8n-files/videos/` for easy n8n workflow integration.

Example n8n workflow:
1. HTTP Request to `/run_async` with `chromeProfile: "veo_*"`
2. Wait for webhook callback
3. Use `n8n_path` from result to access video
4. Process video (upload, edit, etc.)

## Maintenance

### Updating Selectors

If Google Labs Flow updates their UI, you may need to update selectors in:

- `find_prompt_input()` - Prompt input field
- `submit_prompt()` - Submit button
- `wait_for_generation_complete()` - Completion indicators
- `download_video()` - Download button

Check recent logs and debug screenshots to identify new selectors.

## Best Practices

1. **Always use dedicated Chrome profiles** - Keeps sessions separate
2. **Set appropriate timeouts** - Flow generation can be slow
3. **Monitor logs** - Check for warnings/errors
4. **Keep profiles logged in** - Saves authentication time
5. **Use webhooks** - For async notification when complete
6. **Backup n8n folder** - Important generated videos

## Comparison with Sora Workflow

| Feature | Sora | Flow |
|---------|------|------|
| Starting URL | Explore page | Project URL |
| Navigation | Multiple pages | Single page |
| Status Check | Poll Drafts page | Check for indicators |
| Download | Detail page menu | Direct or menu |
| File Output | Same structure | Same structure |
| n8n Copy | Yes | Yes |
| Chrome Profile | Required | Required |

Both scripts share the same file organization and n8n integration for seamless workflow compatibility.
