# YouTube Upload - Quick Reference

## 🚀 Quick Start

### 1. Create YouTube Profile
```bash
curl -X POST http://localhost:4000/create_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "youtube_channel1"}'
```

### 2. Login to YouTube
```bash
# Launch browser with profile
curl -X POST http://localhost:4000/launch_profile \
  -H "Content-Type: application/json" \
  -d '{"name": "youtube_channel1"}'

# Login to YouTube Studio in the opened browser, then close it
```

### 3. Upload Video
```bash
curl -X POST http://localhost:4000/upload_youtube \
  -H "Content-Type: application/json" \
  -d '{
    "videoPath": "/Users/macbookpro/Desktop/Project - Coding/sora-autopilot/sora-ui-autopilot/outputs/STORY004/STORY004_final.mp4",
    "title": "My Amazing Video",
    "description": "This is my video description",
    "storyId": "STORY004",
    "chromeProfile": "youtube_channel1"
  }'
```

### 4. Check Status
```bash
# Replace JOB_ID with the jobId from step 3
curl http://localhost:4000/upload_youtube_status/JOB_ID
```

## 📋 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload_youtube` | POST | Upload video to YouTube |
| `/upload_youtube_status/{job_id}` | GET | Check upload status |
| `/list_profiles` | GET | List Chrome profiles |
| `/create_profile` | POST | Create new Chrome profile |
| `/launch_profile` | POST | Open Chrome with profile |

## 🔧 Request Format

### Minimal Request
```json
{
  "videoPath": "/path/to/video.mp4",
  "title": "Video Title",
  "description": "Video Description",
  "storyId": "STORY001"
}
```

### Full Request
```json
{
  "videoPath": "/path/to/video.mp4",
  "title": "Video Title",
  "description": "Video Description",
  "storyId": "STORY001",
  "chromeProfile": "youtube_channel1",
  "webhookUrl": "http://localhost:5678/webhook/youtube_done"
}
```

## 📝 Response Format

### Success Response
```json
{
  "ok": true,
  "jobId": "abc123",
  "status": "queued",
  "storyId": "STORY001",
  "videoPath": "/path/to/video.mp4",
  "message": "YouTube upload job accepted..."
}
```

### Status Response (Running)
```json
{
  "ok": true,
  "jobId": "abc123",
  "status": "running",
  "created_at": 1234567890,
  "started_at": 1234567891
}
```

### Status Response (Complete)
```json
{
  "ok": true,
  "jobId": "abc123",
  "status": "done",
  "finished_at": 1234567999,
  "result": {
    "ok": true,
    "finished": true,
    "storyId": "STORY001"
  }
}
```

## 🎯 Common Use Cases

### Upload Final Story Video
```bash
curl -X POST http://localhost:4000/upload_youtube \
  -H "Content-Type: application/json" \
  -d '{
    "videoPath": "/Users/macbookpro/Desktop/Project - Coding/sora-autopilot/sora-ui-autopilot/outputs/STORY004/STORY004_final.mp4",
    "title": "AI Generated Story - Part 4",
    "description": "This video was generated using AI. An amazing journey!",
    "storyId": "STORY004",
    "chromeProfile": "youtube_main"
  }'
```

### Check All Profiles
```bash
curl http://localhost:4000/list_profiles
```

## 🔍 Key Features

- ✅ **Mobile Resolution**: 390x844 window size for better UI
- ✅ **Auto-login**: Use saved Chrome profiles
- ✅ **Async Processing**: Upload in background
- ✅ **Webhook Callbacks**: Get notified on completion
- ✅ **Error Recovery**: Comprehensive logging

## 📊 Workflow Order

```
1. Generate Video (Sora/Veo)
   ↓
2. Process Video (Optional - merge/captions/music)
   ↓
3. Upload to YouTube
   ↓
4. Get webhook notification when done
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Profile locked | Close Chrome instances using that profile |
| File not found | Check video path is absolute and exists |
| Upload timeout | Increase `YT_UPLOAD_WAIT` env variable |
| Login required | Launch profile and login to YouTube Studio |

## 📁 File Locations

- **Logs**: `logs/youtube_<storyId>_<timestamp>.txt`
- **Debug**: `debug/<storyId>_error.png`
- **Profiles**: `chrome_profiles/<profile_name>/`
- **Videos**: `outputs/<storyId>/<storyId>_final.mp4`

## 💡 Pro Tips

1. **Multiple Channels**: Create separate profiles for each YouTube channel
2. **Batch Upload**: Run multiple upload jobs in parallel (different profiles)
3. **Title Templates**: Use consistent title format with story ID
4. **Description**: Include keywords and timestamps for better SEO

## 🔗 Related Endpoints

- **Sora Generation**: `POST /run_async`
- **Veo Generation**: `POST /run_async` (with veo profile)
- **Media Processing**: `POST /process`
- **Status Check**: `GET /status/{job_id}`

## Environment Variables

```bash
export YT_CHROME_PROFILE="/path/to/profile"
export YT_UPLOAD_WAIT=300
export YT_PROCESSING_WAIT=300
export YT_POLL_SECONDS=5
```
