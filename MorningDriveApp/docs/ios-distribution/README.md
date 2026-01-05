# iOS Distribution Guide

This guide covers building and distributing Morning Drive for iOS.

## Quick Start

```bash
# Build and create archive (bumps build number automatically)
npm run ios:release

# Or manually:
npm run ios:bump-build      # Increment build number
npm run ios:build-release   # Create archive
npm run ios:upload          # Upload to TestFlight (or use Xcode)
```

## Build Types

| Aspect | Development (Debug) | Production (Release) |
|--------|---------------------|----------------------|
| Bundle ID | `com.g0rdon.morning.dev` | `com.g0rdon.morning` |
| App Name | Morning Drive Dev | Morning Drive |
| App Icon | Red DEV banner | Clean sunrise icon |
| Metro Server | Connected | Bundled JavaScript |
| Install | Can install both on same device | Separate from dev |

## Available Scripts

| Command | Description |
|---------|-------------|
| `npm run ios:release` | Bump build & create archive |
| `npm run ios:build-release` | Create archive only |
| `npm run ios:bump-build` | Increment build number (1 -> 2) |
| `npm run ios:bump-patch` | Increment patch (1.0.0 -> 1.0.1) |
| `npm run ios:bump-minor` | Increment minor (1.0.0 -> 1.1.0) |
| `npm run ios:bump-major` | Increment major (1.0.0 -> 2.0.0) |
| `npm run ios:upload` | Upload to TestFlight |
| `npm run icons:generate` | Regenerate app icons |

## Files

```
scripts/ios/
  build-release.sh      # Main build script
  bump-version.sh       # Version management
  upload-testflight.sh  # TestFlight upload helper
  ExportOptions-AppStore.plist  # Export configuration

ios/MorningDriveApp/Images.xcassets/
  AppIcon.appiconset/     # Production icons
  AppIcon-Dev.appiconset/ # Development icons (with DEV banner)
```

## Next Steps

1. [Initial Setup](./SETUP.md) - Apple Developer enrollment and configuration
2. [TestFlight Guide](./TESTFLIGHT.md) - How to distribute to testers
