#!/bin/bash
#
# Bump version numbers for the Morning Drive iOS app
#
# Usage:
#   ./scripts/ios/bump-version.sh build    # Increment build number only
#   ./scripts/ios/bump-version.sh patch    # 1.0.0 -> 1.0.1
#   ./scripts/ios/bump-version.sh minor    # 1.0.0 -> 1.1.0
#   ./scripts/ios/bump-version.sh major    # 1.0.0 -> 2.0.0
#
# The script modifies MARKETING_VERSION and CURRENT_PROJECT_VERSION in:
#   ios/MorningDriveApp.xcodeproj/project.pbxproj

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

PBXPROJ="ios/MorningDriveApp.xcodeproj/project.pbxproj"
BUMP_TYPE="${1:-build}"

# Get current version from project file
CURRENT_VERSION=$(grep -m1 "MARKETING_VERSION = " "$PBXPROJ" | sed 's/.*MARKETING_VERSION = \([^;]*\);.*/\1/')
CURRENT_BUILD=$(grep -m1 "CURRENT_PROJECT_VERSION = " "$PBXPROJ" | sed 's/.*CURRENT_PROJECT_VERSION = \([^;]*\);.*/\1/')

echo -e "${YELLOW}Current version: ${CURRENT_VERSION} (${CURRENT_BUILD})${NC}"

# Parse version components
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Calculate new version
case "$BUMP_TYPE" in
    major)
        NEW_MAJOR=$((MAJOR + 1))
        NEW_VERSION="${NEW_MAJOR}.0.0"
        NEW_BUILD=1
        ;;
    minor)
        NEW_MINOR=$((MINOR + 1))
        NEW_VERSION="${MAJOR}.${NEW_MINOR}.0"
        NEW_BUILD=1
        ;;
    patch)
        NEW_PATCH=$((PATCH + 1))
        NEW_VERSION="${MAJOR}.${MINOR}.${NEW_PATCH}"
        NEW_BUILD=1
        ;;
    build)
        NEW_VERSION="$CURRENT_VERSION"
        NEW_BUILD=$((CURRENT_BUILD + 1))
        ;;
    *)
        echo -e "${RED}Unknown bump type: $BUMP_TYPE${NC}"
        echo "Usage: $0 [major|minor|patch|build]"
        exit 1
        ;;
esac

echo -e "${GREEN}New version: ${NEW_VERSION} (${NEW_BUILD})${NC}"

# Update MARKETING_VERSION (appears in both Debug and Release configurations)
sed -i '' "s/MARKETING_VERSION = ${CURRENT_VERSION}/MARKETING_VERSION = ${NEW_VERSION}/g" "$PBXPROJ"

# Update CURRENT_PROJECT_VERSION
sed -i '' "s/CURRENT_PROJECT_VERSION = ${CURRENT_BUILD}/CURRENT_PROJECT_VERSION = ${NEW_BUILD}/g" "$PBXPROJ"

echo ""
echo -e "${GREEN}Version bumped successfully!${NC}"
echo -e "  Marketing Version: ${CURRENT_VERSION} -> ${NEW_VERSION}"
echo -e "  Build Number: ${CURRENT_BUILD} -> ${NEW_BUILD}"
