import sys
import os
import time
import undetected_chromedriver as uc

def main():
    if len(sys.argv) < 2:
        print("Usage: python launch_browser.py <profile_path>")
        sys.exit(1)
    
    profile_path = sys.argv[1]
    
    print(f"Launching Chrome with profile: {profile_path}")
    
    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--disable-popup-blocking")
    
    # Standard prefs
    prefs = {
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)
    
    try:
        # Force ChromeDriver version 144 to match your Chrome 144
        # Change this number if you update Chrome later
        driver = uc.Chrome(
            options=options,
            user_data_dir=profile_path,
            version_main=144,  # Match your Chrome version (144.0.7559.110)
            use_subprocess=False,
            driver_executable_path=None
        )
        print("✅ Browser launched successfully!")
        print(f"Chrome version: 144.x (matched ChromeDriver 144)")
        print("Keep this script running to keep browser open.")
        
        driver.get("https://sora.chatgpt.com/")
        
        # Keep alive
        while True:
            try:
                # check if browser is still open
                _ = driver.window_handles
                time.sleep(1)
            except Exception:
                print("Browser closed.")
                break
                
    except Exception as e:
        print(f"Error launching browser: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
