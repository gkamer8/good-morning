# iOS Distribution Setup

One-time setup required before distributing the app.

## 1. Apple Developer Program Enrollment

1. Go to https://developer.apple.com/programs/
2. Click "Enroll" and sign in with your Apple ID
3. Pay the $99/year fee
4. Wait for approval (typically 24-48 hours)

## 2. App ID Registration

After enrollment is approved:

1. Go to https://developer.apple.com/account/resources/identifiers/list
2. Click the "+" button to register a new identifier
3. Select "App IDs" and click Continue
4. Select "App" and click Continue
5. Configure the App ID:
   - Description: "Morning Drive"
   - Bundle ID: Select "Explicit" and enter `com.g0rdon.morning`
   - Capabilities: Enable "CarPlay Audio" under "Additional Capabilities"
6. Click Continue and Register

Repeat for the dev bundle ID (`com.g0rdon.morning.dev`) if you want to distribute dev builds.

## 3. App Store Connect Setup

1. Go to https://appstoreconnect.apple.com/
2. Click "My Apps" > "+" > "New App"
3. Fill in the details:
   - Platforms: iOS
   - Name: Morning Drive
   - Primary Language: English (U.S.)
   - Bundle ID: Select `com.g0rdon.morning`
   - SKU: morning-drive (unique identifier, not visible to users)
   - User Access: Full Access
4. Click Create

## 4. Xcode Signing Configuration

The project is already configured for automatic signing:

- **Development Team**: 94ERB3H892
- **Signing Style**: Automatic
- **Bundle IDs**: Configured per-configuration (Debug/Release)

To verify:

1. Open `ios/MorningDriveApp.xcworkspace` in Xcode
2. Select the MorningDriveApp target
3. Go to "Signing & Capabilities" tab
4. Ensure "Automatically manage signing" is checked
5. Select your team from the dropdown

## 5. CarPlay Entitlement

The app uses CarPlay Audio, which requires a special entitlement:

1. In Apple Developer Portal, go to your App ID
2. Under Capabilities, ensure "CarPlay Audio" is enabled
3. Xcode should automatically include the entitlement when signing

If you see signing errors related to CarPlay:
1. Go to Certificates, Identifiers & Profiles > Profiles
2. Delete any stale provisioning profiles for this app
3. Let Xcode regenerate them automatically

## Troubleshooting

### "No signing certificate" error

1. Xcode > Settings > Accounts
2. Select your Apple ID
3. Click "Manage Certificates"
4. Click "+" and create a new "Apple Development" certificate

### "Bundle ID not registered" error

Ensure you've registered the exact bundle ID in the Developer Portal:
- Production: `com.g0rdon.morning`
- Development: `com.g0rdon.morning.dev`

### CarPlay entitlement issues

CarPlay requires explicit Apple approval for new developers. If builds fail with entitlement errors:
1. Request CarPlay entitlement at https://developer.apple.com/contact/carplay/
2. Wait for approval before distributing
