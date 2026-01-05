#!/bin/bash
#
# Upload the latest archive to TestFlight
#
# Usage:
#   ./scripts/ios/upload-testflight.sh
#
# Prerequisites:
#   - An archive must exist at build/MorningDriveApp.xcarchive
#   - You must be signed into Xcode with your Apple Developer account
#   - The app must be registered in App Store Connect
#
# Alternative upload methods:
#   1. Xcode Organizer: Window > Organizer > Select Archive > Distribute App
#   2. Transporter app: Drag and drop the .ipa file
#   3. altool (deprecated): xcrun altool --upload-app -f <ipa> -t ios

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory and change to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

ARCHIVE_PATH="build/MorningDriveApp.xcarchive"
EXPORT_PATH="build/export"
EXPORT_OPTIONS="$SCRIPT_DIR/ExportOptions-AppStore.plist"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Morning Drive - TestFlight Upload    ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if archive exists
if [ ! -d "$ARCHIVE_PATH" ]; then
    echo -e "${RED}Error: Archive not found at $ARCHIVE_PATH${NC}"
    echo -e "Run ./scripts/ios/build-release.sh first"
    exit 1
fi

# Clean export directory
rm -rf "$EXPORT_PATH"
mkdir -p "$EXPORT_PATH"

echo -e "${YELLOW}Exporting archive for App Store Connect...${NC}"

# Export the archive
xcodebuild -exportArchive \
    -archivePath "$ARCHIVE_PATH" \
    -exportPath "$EXPORT_PATH" \
    -exportOptionsPlist "$EXPORT_OPTIONS" \
    | grep -E "(Export|error:|warning:)" || true

# Check if IPA was created
IPA_FILE=$(find "$EXPORT_PATH" -name "*.ipa" | head -1)

if [ -n "$IPA_FILE" ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Export Complete!                      ${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "IPA created at: ${IPA_FILE}"
    echo ""
    echo -e "${YELLOW}Uploading to App Store Connect...${NC}"
    echo ""

    # Upload using xcrun notarytool or altool
    # Note: This requires App Store Connect API key or Apple ID credentials
    xcrun altool --upload-app \
        -f "$IPA_FILE" \
        -t ios \
        --apiKey "${APP_STORE_CONNECT_API_KEY:-}" \
        --apiIssuer "${APP_STORE_CONNECT_ISSUER_ID:-}" \
        2>&1 || {
            echo ""
            echo -e "${YELLOW}Automatic upload requires API credentials.${NC}"
            echo ""
            echo -e "Upload manually using one of these methods:"
            echo ""
            echo -e "  ${GREEN}Option 1: Xcode Organizer (Recommended)${NC}"
            echo -e "    1. Open Xcode"
            echo -e "    2. Window > Organizer"
            echo -e "    3. Select the archive"
            echo -e "    4. Click 'Distribute App'"
            echo -e "    5. Choose 'App Store Connect'"
            echo ""
            echo -e "  ${GREEN}Option 2: Transporter App${NC}"
            echo -e "    1. Download Transporter from the Mac App Store"
            echo -e "    2. Drag and drop: ${IPA_FILE}"
            echo ""
        }
else
    echo ""
    echo -e "${RED}Export failed - IPA not created${NC}"
    exit 1
fi
