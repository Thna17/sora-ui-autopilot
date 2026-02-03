# YouTube Upload Autopilot

## Overview

The YouTube Upload Autopilot automates the process of uploading videos to YouTube using Chrome automation. It supports:

- **Mobile Resolution**: Runs in mobile-sized window (390x844) for better UI handling
- **Chrome Profile Support**: Use specific Chrome profiles with pre-authenticated YouTube accounts
- **Automatic Form Filling**: Automatically fills video title and description
- **Step-by-Step Upload**: Handles all upload steps including publish
- **Background Processing**: Runs as async job with webhook callbacks

## Features

✅ **Mobile Window Size**: 390x844 resolution optimized for YouTube's mobile-friendly UI  
✅ **Chrome Profile Management**: Use separate profiles for different YouTube accounts  
✅ **Automatic Upload**: From file selection to publishing  
✅ **Title & Description**: Auto-fill video metadata  
✅ **Webhook Callbacks**: Get notified when upload completes  
✅ **Error Handling**: Comprehensive logging and debug screenshots  

## API Endpoint

### POST `/upload_youtube`

Upload a video to YouTube.

**Request Body:**
```json
{
  "videoPath": "/path/to/video.mp4",
  "title": "My Video Title",
  "description": "My video description with details...",
  "storyId": "STORY004",
  "chromeProfile": "youtube_channel1",
  "webhookUrl": "http://localhost:5678/webhook/youtube_done"
}
```

**Response:**
```json
{
  "ok": true,
  "jobId": "abc123def456",
  "status": "queued",
  "storyId": "STORY004",
  "videoPath": "/path/to/video.mp4",
  "message": "YouTube upload job accepted. Will callback webhookUrl when finished=true."
}
```

### GET `/upload_youtube_status/{job_id}`

Check the status of an upload job.

**Response:**
```json
{
  "ok": true,
  "jobId": "abc123def456",
  "status": "done",
  "created_at": 1234567890.123,
  "started_at": 1234567891.456,
  "finished_at": 1234567999.789,
  "result": {
    "ok": true,
    "finished": true,
    "storyId": "STORY004",
    "videoPath": "/path/to/video.mp4",
    "title": "My Video Title"
  }
}
```

## Usage Examples

### Using cURL

```bash
curl -X POST http://localhost:4000/upload_youtube \
  -H "Content-Type: application/json" \
  -d '{
    "videoPath": "/Users/macbookpro/Desktop/Project - Coding/sora-autopilot/sora-ui-autopilot/outputs/STORY004/STORY004_final.mp4",
    "title": "Amazing AI Generated Video",
    "description": "Created with Sora AI - An incredible journey through imagination",
    "storyId": "STORY004",
    "chromeProfile": "youtube_main"
  }'
```

### Using Python

```python
import requests

response = requests.post("http://localhost:4000/upload_youtube", json={
    "videoPath": "/Users/macbookpro/Desktop/Project - Coding/sora-autopilot/sora-ui-autopilot/outputs/STORY004/STORY004_final.mp4",
    "title": "Amazing AI Generated Video",
    "description": "Created with Sora AI",
    "storyId": "STORY004",
    "chromeProfile": "youtube_main",
    "webhookUrl": "http://localhost:5678/webhook/youtube_done"
})

job = response.json()
print(f"Job ID: {job['jobId']}")

# Check status later
status = requests.get(f"http://localhost:4000/upload_youtube_status/{job['jobId']}")
print(status.json())
```

### Using n8n Workflow

**1. HTTP Request Node - Upload Video**
- Method: POST
- URL: `http://localhost:4000/upload_youtube`
- Body:
```json
{
  "videoPath": "{{ $json.videoPath }}",
  "title": "{{ $json.title }}",
  "description": "{{ $json.description }}",
  "storyId": "{{ $json.storyId }}",
  "chromeProfile": "youtube_channel1",
  "webhookUrl": "http://localhost:5678/webhook/youtube_done"
}
```

**2. Webhook Node - Receive Completion**
- Webhook URL: `/webhook/youtube_done`
- Method: POST
- This will receive the upload result when complete

## Chrome Profile Setup

1. **Create a Chrome profile for YouTube:**
```bash
curl -X POST http://localhost:4000/create_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "youtube_main"}'
```

2. **Launch the profile to login to YouTube:**
```bash
curl -X POST http://localhost:4000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "youtube_main"}'
```

3. **Login to YouTube Studio** in the opened browser window

4. **Close the browser** when done logging in

5. **Use the profile** in your upload jobs with `"chromeProfile": "youtube_main"`

## Environment Variables

You can customize the upload behavior with these environment variables:

- `YT_CHROME_PROFILE`: Default Chrome profile path
- `YT_UPLOAD_WAIT`: Max seconds to wait for upload (default: 180)
- `YT_PROCESSING_WAIT`: Max seconds to wait for processing (default: 300)
- `YT_POLL_SECONDS`: Seconds between status checks (default: 5)
- `YT_HEADLESS`: Run in headless mode (`1`, `true`, or `yes`)

Example:
```bash
export YT_CHROME_PROFILE="/path/to/chrome_profiles/youtube_main"
export YT_UPLOAD_WAIT=300
```

## Workflow Integration

### Complete Video Generation → Upload Flow

1. **Generate Video** (Sora/Veo)
```json
POST /run_async
{
  "prompt": "A beautiful sunset",
  "storyId": "STORY004",
  "scene": 1,
  "chromeProfile": "veo_profile"
}
```

2. **Process Video** (Optional - Add captions, music)
```json
POST /process
{
  "storyId": "STORY004",
  "clips": ["/path/to/scene1.mp4", "/path/to/scene2.mp4"],
  "musicPath": "/path/to/music.mp3"
}
```

3. **Upload to YouTube**
```json
POST /upload_youtube
{
  "videoPath": "/path/to/outputs/STORY004/STORY004_final.mp4",
  "title": "My AI Video - STORY004",
  "description": "Generated with AI",
  "storyId": "STORY004",
  "chromeProfile": "youtube_main"
}
```

## Mobile Resolution

The YouTube upload runs in a **mobile-sized window (390x844)** to:
- Better handle YouTube Studio's responsive UI
- Avoid desktop-specific UI issues
- Match the mobile-friendly upload flow
- Ensure reliable element detection

This matches the approach used in your existing Sora/Veo autopilots.

## Logging & Debugging

- **Logs**: Saved to `logs/youtube_<storyId>_<timestamp>.txt`
- **Screenshots**: Debug screenshots saved to `debug/` on errors
- **Console Output**: Real-time progress in server logs

## Troubleshooting

### Upload doesn't start
- Ensure Chrome profile is logged into YouTube
- Check that video file exists and is valid
- Review logs in `logs/youtube_*.txt`

### Chrome profile locked
- Close any running Chrome instances using that profile
- The script will auto-cleanup stale locks

### Upload timeout
- Increase `YT_UPLOAD_WAIT` environment variable
- Check internet connection
- Verify video file size (large files take longer)

### Title/Description not filled
- Check debug screenshots in `debug/` folder
- YouTube UI may have changed - review selectors in script
- Ensure you're using latest Chrome version (144)

## Next Steps

1. **Create dedicated YouTube profiles** for each channel
2. **Setup n8n workflow** to chain generation → upload
3. **Configure webhooks** for completion notifications
4. **Test with sample videos** before production use

## Support

For issues or questions:
1. Check logs in `logs/youtube_*.txt`
2. Review debug screenshots in `debug/`
3. Verify Chrome profile is authenticated
4. Check that video file exists and path is correct
