#!/usr/bin/env python3
"""
Example: YouTube Upload Test
Demonstrates how to upload a video to YouTube using the upload_youtube endpoint
"""

import requests
import json
import time
import sys
import os

# Configuration
API_BASE = "http://localhost:4000"
VIDEO_PATH = "/Users/macbookpro/Desktop/Project - Coding/sora-autopilot/sora-ui-autopilot/outputs/STORY004/STORY004_final.mp4"
TITLE = "AI Generated Video - STORY004"
DESCRIPTION = """
This video was generated using AI technology.

🎬 Created with Sora/Veo AI
🎨 Automated video generation
✨ Amazing AI capabilities

Subscribe for more AI-generated content!
"""
STORY_ID = "STORY004"
CHROME_PROFILE = "youtube_main"

def main():
    print("=" * 60)
    print("YouTube Upload Test")
    print("=" * 60)
    
    # 1. Check if video file exists
    print(f"\n1. Checking video file...")
    if not os.path.exists(VIDEO_PATH):
        print(f"   ❌ Error: Video file not found: {VIDEO_PATH}")
        return
    print(f"   ✅ Video file found: {VIDEO_PATH}")
    file_size = os.path.getsize(VIDEO_PATH) / (1024 * 1024)  # MB
    print(f"   📊 File size: {file_size:.2f} MB")
    
    # 2. Check if chrome profile exists
    print(f"\n2. Checking Chrome profile...")
    try:
        response = requests.get(f"{API_BASE}/list_profiles")
        profiles = response.json()
        if CHROME_PROFILE in profiles.get("profiles", []):
            print(f"   ✅ Chrome profile '{CHROME_PROFILE}' found")
        else:
            print(f"   ⚠️  Chrome profile '{CHROME_PROFILE}' not found")
            print(f"   Available profiles: {profiles.get('profiles', [])}")
            print(f"\n   Create it with:")
            print(f"   curl -X POST {API_BASE}/create_profile -H 'Content-Type: application/json' -d '{{'name': '{CHROME_PROFILE}'}}'")
            print(f"\n   Then login with:")
            print(f"   curl -X POST {API_BASE}/launch_profile -H 'Content-Type: application/json' -d '{{'name': '{CHROME_PROFILE}'}}'")
            
            # Ask if user wants to continue anyway
            response = input("\n   Continue without profile? (y/n): ")
            if response.lower() != 'y':
                return
    except Exception as e:
        print(f"   ⚠️  Could not check profiles: {e}")
    
    # 3. Submit upload job
    print(f"\n3. Submitting upload job...")
    upload_data = {
        "videoPath": VIDEO_PATH,
        "title": TITLE,
        "description": DESCRIPTION,
        "storyId": STORY_ID,
        "chromeProfile": CHROME_PROFILE,
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/upload_youtube",
            json=upload_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            print(f"   ❌ Error: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return
        
        result = response.json()
        
        if not result.get("ok"):
            print(f"   ❌ Error: {result.get('error')}")
            return
        
        job_id = result.get("jobId")
        print(f"   ✅ Job submitted successfully!")
        print(f"   📝 Job ID: {job_id}")
        print(f"   📊 Status: {result.get('status')}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # 4. Monitor upload progress
    print(f"\n4. Monitoring upload progress...")
    print(f"   (This may take several minutes depending on file size)")
    
    last_status = ""
    start_time = time.time()
    
    while True:
        try:
            response = requests.get(f"{API_BASE}/upload_youtube_status/{job_id}")
            status_data = response.json()
            
            current_status = status_data.get("status", "unknown")
            
            if current_status != last_status:
                elapsed = int(time.time() - start_time)
                print(f"   [{elapsed}s] Status: {current_status}")
                last_status = current_status
            
            # Check if done
            if current_status in ["done", "error"]:
                print(f"\n5. Upload completed!")
                
                if current_status == "done":
                    result = status_data.get("result", {})
                    if result.get("ok") and result.get("finished"):
                        print(f"   ✅ Successfully uploaded to YouTube!")
                        print(f"   📝 Video: {result.get('title')}")
                        print(f"   📊 Story ID: {result.get('storyId')}")
                    else:
                        print(f"   ⚠️  Upload may have issues:")
                        print(f"   {json.dumps(result, indent=2)}")
                else:
                    print(f"   ❌ Upload failed")
                    result = status_data.get("result", {})
                    print(f"   Error: {result.get('error', 'Unknown error')}")
                
                # Show full result
                print(f"\n6. Full result:")
                print(json.dumps(status_data, indent=2))
                break
            
            # Wait before next check
            time.sleep(5)
            
        except KeyboardInterrupt:
            print(f"\n\n   ⏸️  Monitoring stopped (job still running)")
            print(f"   Check status later with:")
            print(f"   curl {API_BASE}/upload_youtube_status/{job_id}")
            break
        except Exception as e:
            print(f"   ⚠️  Error checking status: {e}")
            time.sleep(5)
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
