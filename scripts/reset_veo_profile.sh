#!/usr/bin/env bash
# VEO Profile Reset Script
# Run this to completely reset the veo-bot profile

set -e

echo "🔧 VEO Profile Reset Script"
echo "================================"
echo ""

# Step 1: Kill all Chrome processes
echo "1. Killing all Chrome processes..."
pkill -f "Google Chrome" || true
sleep 2
echo "✅ Chrome processes killed"
echo ""

# Step 2: Backup old profile
echo "2. Backing up old veo-bot profile..."
cd "$(dirname "$0")/.."
if [ -d "chrome_profiles/veo-bot" ]; then
    timestamp=$(date +%Y%m%d_%H%M%S)
    mv "chrome_profiles/veo-bot" "chrome_profiles/veo-bot.backup_${timestamp}"
    echo "✅ Backed up to chrome_profiles/veo-bot.backup_${timestamp}"
else
    echo "⚠️ No existing profile found"
fi
echo ""

# Step 3: Create fresh profile directory
echo "3. Creating fresh profile directory..."
mkdir -p "chrome_profiles/veo-bot"
echo "✅ Fresh directory created"
echo ""

# Step 4: Clear undetected_chromedriver cache 
echo "4. Clearing ChromeDriver cache..."
rm -rf ~/.undetected_chromedriver || true
echo "✅ ChromeDriver cache cleared"
echo ""

echo "================================"
echo "✅ Profile reset complete!"
echo ""
echo "Next steps:"
echo "1. Run: curl -X POST http://localhost:8000/launch_profile -H 'Content-Type: application/json' -d '{\"name\": \"veo-bot\"}'"
echo "2. Login to Google in the browser that opens"
echo "3. Go to https://labs.google/fx/tools/flow/"
echo "4. Close the browser"
echo "5. Run your n8n workflow"
echo ""
