# TestFlight Distribution Guide

TestFlight is Apple's official beta testing platform. It allows you to distribute pre-release builds to up to 10,000 testers.

## Uploading a Build

### Option 1: Xcode Organizer (Recommended)

1. Build the archive:
   ```bash
   npm run ios:release
   ```

2. Open Xcode Organizer:
   - Xcode > Window > Organizer
   - Or press Cmd+Shift+O

3. Select the archive and click "Distribute App"

4. Select "App Store Connect" and click Next

5. Select "Upload" and click Next

6. Keep defaults (automatic signing) and click Next

7. Review and click "Upload"

8. Wait for processing (usually 5-30 minutes)

### Option 2: Transporter App

1. Download Transporter from the Mac App Store

2. Build and export:
   ```bash
   npm run ios:release
   npm run ios:upload  # Creates IPA in build/export/
   ```

3. Open Transporter and sign in with your Apple ID

4. Drag the IPA file from `build/export/` into Transporter

5. Click "Deliver"

## Setting Up TestFlight

After the build is uploaded and processed:

1. Go to https://appstoreconnect.apple.com/
2. Select your app
3. Click "TestFlight" tab

### Internal Testing

For your development team (up to 25 testers):

1. Click "Internal Testing" in the sidebar
2. Click "+" to create a group
3. Add testers by email (must be Apple IDs)
4. Select the build to test
5. Click "Submit for Review" (auto-approved for internal)

Testers receive an email invitation to install TestFlight and the app.

### External Testing

For wider distribution (up to 10,000 testers):

1. Click "External Testing" in the sidebar
2. Click "+" to create a group
3. Fill in test information:
   - What to Test: Brief description
   - Contact Info: Email for feedback
4. Add testers or create a public link
5. Submit for Beta App Review (usually approved in 24-48 hours)

## Public Link Distribution

For easy sharing with friends:

1. Go to TestFlight > External Testing
2. Create or select a group
3. Enable "Public Link"
4. Copy the link and share it
5. Anyone with the link can install (up to 10,000 total testers)

Note: Public links still require Beta App Review approval.

## Managing Builds

### Version Numbers

Each TestFlight build must have a unique combination of:
- **Marketing Version** (MARKETING_VERSION): 1.0.0, shown to users
- **Build Number** (CURRENT_PROJECT_VERSION): 1, 2, 3, internal tracking

Use the bump scripts:
```bash
npm run ios:bump-build  # Increment build only (1.0.0 build 1 -> 1.0.0 build 2)
npm run ios:bump-patch  # 1.0.0 -> 1.0.1, resets build to 1
npm run ios:bump-minor  # 1.0.0 -> 1.1.0, resets build to 1
npm run ios:bump-major  # 1.0.0 -> 2.0.0, resets build to 1
```

### Build Expiration

TestFlight builds expire after 90 days. Upload new builds regularly to keep testers updated.

### Build Notes

When uploading, you can add "What's New" notes in App Store Connect that testers see when updating.

## Tester Experience

1. Tester receives email invitation
2. Downloads TestFlight app from App Store
3. Accepts invitation and installs the app
4. App appears with "Morning Drive" name and icon
5. Updates are automatic (or manual in TestFlight settings)

## Troubleshooting

### Build stuck in "Processing"

- Usually takes 5-30 minutes
- If stuck >1 hour, try re-uploading
- Check for email from Apple about issues

### "This build is not available"

- Build may have expired (90 day limit)
- Build may have compliance issues
- Upload a new build

### Testers can't install

- Ensure device is running iOS 15.1 or later
- Ensure device is registered with their Apple ID
- Check if build is approved for external testing
