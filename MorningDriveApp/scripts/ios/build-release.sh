#!/bin/bash
#
# Build a release archive of the Morning Drive iOS app
#
# Usage:
#   ./scripts/ios/build-release.sh
#
# This script:
#   1. Installs npm dependencies
#   2. Installs CocoaPods dependencies
#   3. Builds the app in Release configuration
#   4. Creates an Xcode archive
#
# The archive can then be exported/uploaded via Xcode Organizer or Transporter

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

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Morning Drive - iOS Release Build    ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuration
SCHEME="MorningDriveApp"
WORKSPACE="ios/MorningDriveApp.xcworkspace"
CONFIGURATION="Release"
ARCHIVE_PATH="build/MorningDriveApp.xcarchive"

# Create build directory
mkdir -p build

# Step 1: Install npm dependencies
echo -e "${YELLOW}Installing npm dependencies...${NC}"
npm ci

# Step 2: Install CocoaPods
echo -e "${YELLOW}Installing CocoaPods dependencies...${NC}"
cd ios
pod install --repo-update
cd ..

# Step 3: Clean previous builds
echo -e "${YELLOW}Cleaning previous builds...${NC}"
xcodebuild clean \
    -workspace "$WORKSPACE" \
    -scheme "$SCHEME" \
    -configuration "$CONFIGURATION" \
    | grep -E "(Clean|error:|warning:)" || true

# Step 4: Build archive
echo -e "${YELLOW}Building archive...${NC}"
xcodebuild archive \
    -workspace "$WORKSPACE" \
    -scheme "$SCHEME" \
    -configuration "$CONFIGURATION" \
    -archivePath "$ARCHIVE_PATH" \
    -destination "generic/platform=iOS" \
    CODE_SIGN_STYLE=Automatic \
    | grep -E "(Archive|error:|warning:|BUILD)" || true

# Check if archive was created
if [ -d "$ARCHIVE_PATH" ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Build Complete!                       ${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "Archive created at: ${ARCHIVE_PATH}"
    echo ""
    echo -e "Next steps:"
    echo -e "  1. Open Xcode > Window > Organizer"
    echo -e "  2. Select the archive and click 'Distribute App'"
    echo -e "  3. Choose 'App Store Connect' for TestFlight distribution"
    echo ""
    echo -e "Or use: ./scripts/ios/upload-testflight.sh"
else
    echo ""
    echo -e "${RED}Build failed - archive not created${NC}"
    exit 1
fi
