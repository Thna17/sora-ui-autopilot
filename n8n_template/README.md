# n8n YouTube Upload Workflow

## Overview

This n8n workflow automates the complete pipeline:
1. **Video Generation** (Sora/Veo)
2. **YouTube Upload**
3. **Notifications** (Slack/Email)

## Workflow Diagram

```
[Trigger] → [Generate Video] → [Video Done Webhook]
                                        ↓
                                [Upload to YouTube]
                                        ↓
                                [YouTube Done Webhook]
                                        ↓
                                [Notifications]
```

## Installation

### 1. Import Workflow

1. Open n8n
2. Click **Workflows** → **Import from File**
3. Select `youtube_upload_workflow.json`
4. Click **Import**

### 2. Configure Webhooks

The workflow uses 3 webhooks:

| Webhook | Path | Purpose |
|---------|------|---------|
| Trigger | `/webhook/generate_video` | Start video generation |
| Video Done | `/webhook/video_done` | Video generation complete |
| YouTube Done | `/webhook/youtube_done` | YouTube upload complete |

URLs will be:
- `http://localhost:5678/webhook/generate_video`
- `http://localhost:5678/webhook/video_done`
- `http://localhost:5678/webhook/youtube_done`

### 3. Setup Notifications (Optional)

If using Slack notifications:
1. Click on **Notify** nodes
2. Add your Slack credentials
3. Configure channel name

Or remove these nodes if not needed.

## Usage

### Trigger Video Generation + Upload

Send POST request to trigger webhook:

```bash
curl -X POST http://localhost:5678/webhook/generate_video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A beautiful sunset over the ocean",
    "storyId": "STORY005",
    "scene": 1,
    "rowId": "STORY005-scene-1",
    "chromeProfile": "veo_profile",
    "youtubeProfile": "youtube_main",
    "title": "Beautiful Sunset - AI Generated",
    "description": "An amazing AI-generated video of a sunset over the ocean.\n\nCreated with Veo AI."
  }'
```

### Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `prompt` | Yes | Video generation prompt | "A sunset over ocean" |
| `storyId` | Yes | Story identifier | "STORY005" |
| `scene` | Yes | Scene number | 1 |
| `rowId` | No | Row identifier for tracking | "STORY005-scene-1" |
| `chromeProfile` | No | Chrome profile for video gen | "veo_profile" |
| `youtubeProfile` | No | Chrome profile for YouTube | "youtube_main" |
| `title` | No | YouTube video title | "My Video Title" |
| `description` | No | YouTube video description | "My description..." |

## Workflow Steps

### Step 1: Generate Video
```
POST http://localhost:4000/run_async
{
  "prompt": "...",
  "storyId": "STORY005",
  "scene": 1,
  "chromeProfile": "veo_profile",
  "webhookUrl": "http://localhost:5678/webhook/video_done"
}
```

**Response:**
```json
{
  "ok": true,
  "jobId": "abc123",
  "message": "Video generation started"
}
```

### Step 2: Video Generation Complete

When video is done, webhook receives:
```json
{
  "ok": true,
  "storyId": "STORY005",
  "scene": 1,
  "result": {
    "outputPath": "/path/to/STORY005_scene_001.mp4",
    "finished": true
  }
}
```

### Step 3: Upload to YouTube

Automatically triggered:
```
POST http://localhost:4000/upload_youtube
{
  "videoPath": "/path/to/STORY005_scene_001.mp4",
  "title": "Beautiful Sunset - AI Generated",
  "description": "An amazing AI-generated video...",
  "storyId": "STORY005",
  "chromeProfile": "youtube_main",
  "webhookUrl": "http://localhost:5678/webhook/youtube_done"
}
```

### Step 4: Upload Complete

When upload is done, webhook receives:
```json
{
  "ok": true,
  "storyId": "STORY005",
  "result": {
    "finished": true,
    "title": "Beautiful Sunset - AI Generated"
  }
}
```

## Customization

### Adding Error Handling

Add an **IF** node after each HTTP request:

```
[HTTP Request] → [IF: Check ok=true]
                    ├─ True → Continue
                    └─ False → Send Error Notification
```

### Adding Retries

Add **Error Trigger** nodes with retry logic:

```
[HTTP Request] → [Error Trigger]
                     ↓
                [Wait 30s]
                     ↓
                [Retry HTTP Request]
```

### Multiple YouTube Channels

Clone the **Upload to YouTube** node for each channel:

```
[Video Done] → [IF: Check channel]
                  ├─ Channel 1 → Upload with profile1
                  ├─ Channel 2 → Upload with profile2
                  └─ Channel 3 → Upload with profile3
```

### Batch Processing

Add a **Split in Batches** node:

```
[Trigger: Multiple Videos] → [Split in Batches]
                                    ↓
                              [Generate Video]
                                    ↓
                              [Upload to YouTube]
```

## Monitoring

### Check Job Status

While workflow is running, check status:

```bash
# Check video generation
curl http://localhost:4000/status/{job_id}

# Check YouTube upload
curl http://localhost:4000/upload_youtube_status/{job_id}
```

### View Logs

Server logs show real-time progress:
```bash
# Watch server logs
tail -f logs/veo_*.txt
tail -f logs/youtube_*.txt
```

### n8n Execution Log

In n8n UI:
1. Click **Executions** in left menu
2. View execution history
3. Click on execution to see details

## Troubleshooting

### Webhook Not Triggering

1. Check webhook is active (green play button)
2. Verify URL in `webhookUrl` parameter
3. Check n8n is running on port 5678

### Video Generation Fails

1. Check Chrome profile exists and is logged in
2. Verify prompt is valid
3. Check server logs: `logs/veo_*.txt`

### YouTube Upload Fails

1. Verify video file exists at `outputPath`
2. Check YouTube profile is logged in
3. Check server logs: `logs/youtube_*.txt`
4. Ensure title and description are provided

### Timeout Issues

For large videos, increase timeout in HTTP Request nodes:
1. Click on HTTP Request node
2. Go to **Settings** → **Timeout**
3. Increase to 600000 (10 minutes)

## Advanced Features

### Schedule Regular Uploads

Add a **Cron** node:

```
[Cron: Daily at 10am] → [Generate Video] → [Upload]
```

### Conditional Publishing

Add logic to publish at specific times:

```
[Upload Complete] → [IF: Is Weekend?]
                        ├─ Yes → Publish immediately
                        └─ No → Schedule for weekend
```

### Multi-Language Titles

Add **Set** node to create multiple language versions:

```
[Video Done] → [Set: Create translations]
                    ├─ English → Upload to channel_en
                    ├─ Spanish → Upload to channel_es
                    └─ French → Upload to channel_fr
```

## Example: Complete Automation

```bash
# 1. Generate video
curl -X POST http://localhost:5678/webhook/generate_video \
  -d '{"prompt": "Beautiful sunset", "storyId": "STORY005", "scene": 1}'

# Result: Video generates automatically

# 2. Video completes → Webhook triggers upload automatically

# 3. Upload completes → Notification sent automatically

# 4. Check final status
curl http://localhost:4000/upload_youtube_status/{job_id}
```

## Production Tips

1. **Error Notifications**: Add email/Slack alerts on failures
2. **Status Dashboard**: Create a monitoring dashboard
3. **Retry Logic**: Add automatic retries for transient failures
4. **Rate Limiting**: Throttle uploads if hitting API limits
5. **Backup**: Save workflow JSON regularly

## Support Files

- **Workflow**: `youtube_upload_workflow.json`
- **Documentation**: `YOUTUBE_UPLOAD.md`
- **Quick Reference**: `YOUTUBE_QUICK_REFERENCE.md`
- **Test Script**: `test_youtube_upload.py`
