# Morning Drive iOS App

React Native app for Morning Drive with CarPlay support.

> For full documentation, see [morning.g0rdon.com](https://morning.g0rdon.com) or the [Development guide](https://morning.g0rdon.com/docs/development).

## Quick Start

```bash
# Install dependencies
npm install

# Install iOS pods
cd ios && pod install && cd ..

# Run on simulator
npm run ios
```

## Project Structure

```
MorningDriveApp/
├── src/
│   ├── App.tsx           # Root component with navigation
│   ├── screens/          # Home, Settings, Player screens
│   ├── services/         # API client, audio player, CarPlay
│   ├── store/            # Zustand state management
│   ├── components/       # Reusable UI components
│   └── types/            # TypeScript type definitions
├── ios/                  # Native iOS project
├── scripts/              # Build and release scripts
└── docs/                 # iOS distribution guides
```

## Available Scripts

| Command | Description |
|---------|-------------|
| `npm start` | Start Metro bundler |
| `npm run ios` | Run on iOS simulator |
| `npm test` | Run tests |
| `npm run lint` | Run ESLint |
| `npm run ios:release` | Build release archive for TestFlight |

## iOS Distribution

For release builds and TestFlight distribution:

- [Quick Start](./docs/ios-distribution/README.md) - Build commands and scripts
- [Initial Setup](./docs/ios-distribution/SETUP.md) - Apple Developer configuration
- [TestFlight Guide](./docs/ios-distribution/TESTFLIGHT.md) - Beta distribution

## Configuration

The app connects to a Morning Drive backend server. Configure the server URL in the app's Settings screen.

For development, the backend typically runs at `http://localhost:8000` or your machine's IP address for device testing.
