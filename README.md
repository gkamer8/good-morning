# Morning Drive

AI-powered personalized morning briefing app with CarPlay integration.

## Documentation

**Full documentation is available at [morning.g0rdon.com](https://morning.g0rdon.com)**

- [Getting Started](https://morning.g0rdon.com/docs/getting-started) - Setup and first briefing
- [Deployment](https://morning.g0rdon.com/docs/deployment) - Production deployment guide
- [Development](https://morning.g0rdon.com/docs/development) - Local development setup
- [API Reference](https://morning.g0rdon.com/docs/api-reference) - REST API documentation

## Features

- **Professional Radio-Style Briefings**: AI-generated morning briefings with natural voice and professional production
- **Personalized Content**: News, sports scores, weather forecasts, and fun segments tailored to your interests
- **Voice-Matched Quotes**: Quotes read in voices matched to the speaker's demographics
- **CarPlay Support**: Listen to briefings hands-free while driving
- **Classical Music Corner**: Each briefing includes a curated classical music piece
- **Scheduled Generation**: Automatically generate briefings at your preferred time

## Quick Start

```bash
cd backend
cp .env.example .env   # Add your API keys
docker-compose up -d
```

The server runs at http://localhost:8000. See the [Getting Started guide](https://morning.g0rdon.com/docs/getting-started) for detailed instructions.

## Project Structure

```
good-morning/
├── backend/              # Python FastAPI + Claude Agents SDK
│   ├── src/
│   │   ├── agents/       # Claude-powered content orchestration
│   │   ├── tools/        # Data fetching (news, sports, weather)
│   │   ├── audio/        # ElevenLabs TTS + audio assembly
│   │   ├── api/          # REST API endpoints
│   │   └── templates/    # Documentation website
│   └── Dockerfile
└── MorningDriveApp/      # React Native iOS app
    ├── src/              # App screens, services, store
    ├── ios/              # Native iOS project
    └── docs/             # iOS distribution guides
```

## Running Documentation Locally

If the production documentation site is unavailable, you can run it locally:

```bash
cd backend
cp .env.example .env   # Add your API keys
docker-compose up -d

# Documentation available at http://localhost:8000
```

## iOS App

See `MorningDriveApp/README.md` for iOS-specific setup, or the [Development guide](https://morning.g0rdon.com/docs/development) for full instructions.

## License

MIT
