# Morning Drive

AI-powered personalized morning briefing app with CarPlay integration.

## Features

- **Professional Radio-Style Briefings**: AI-generated morning briefings with natural voice and professional production
- **Personalized Content**:
  - News from multiple sources (BBC, Reuters, NPR, NYT, AP)
  - Sports scores and narratives for your favorite teams
  - Weather forecasts for your locations
  - Fun segments (This Day in History, Quote of the Day, Market Minute, Dad Jokes)
- **Voice-Matched Quotes**: When the briefing includes quotes, they're read in voices matched to the speaker's demographics
- **CarPlay Support**: Listen to your briefings hands-free while driving
- **Scheduled Generation**: Automatically generate briefings at your preferred time

## Architecture

```
morning-drive/
├── backend/          # Python FastAPI + Claude Agents SDK
│   ├── src/
│   │   ├── agents/   # Claude-powered content orchestration
│   │   ├── tools/    # Data fetching (news, sports, weather)
│   │   ├── audio/    # ElevenLabs TTS + audio assembly
│   │   └── api/      # REST API endpoints
│   └── Dockerfile
└── ios/              # React Native app
    └── src/
        ├── screens/  # Home, Settings, Player
        ├── services/ # API client, audio player, CarPlay
        └── store/    # Zustand state management
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (for backend deployment)
- Xcode (for iOS development)
- FFmpeg (installed via Docker or locally)

### API Keys Required

- **Anthropic API Key**: For Claude-powered content generation
- **ElevenLabs API Key**: For text-to-speech

### Optional API Keys

- NewsAPI Key (free tier available)
- Weather API Key (Open-Meteo doesn't require one)

## Backend Setup

1. **Navigate to backend directory**:
   ```bash
   cd morning-drive/backend
   ```

2. **Create environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Run with Docker** (recommended):
   ```bash
   docker-compose up -d
   ```

   Or **run locally**:
   ```bash
   pip install -e .
   python -m src.main
   ```

4. **Verify the server is running**:
   ```bash
   curl http://localhost:8000/health
   ```

## iOS App Setup

1. **Navigate to iOS directory**:
   ```bash
   cd morning-drive/ios
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Install iOS pods**:
   ```bash
   cd ios && pod install && cd ..
   ```

4. **Run on simulator**:
   ```bash
   npm run ios
   ```

5. **Configure server URL**:
   - Open the app
   - Go to Settings
   - Enter your backend server URL (e.g., `http://192.168.1.100:8000`)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/briefings/generate` | POST | Generate a new briefing |
| `/api/briefings` | GET | List all briefings |
| `/api/briefings/{id}` | GET | Get briefing details |
| `/api/briefings/{id}/status` | GET | Get generation status |
| `/api/settings` | GET/PUT | User preferences |
| `/api/schedule` | GET/PUT | Generation schedule |

## Configuration Options

### User Settings

- **News Topics**: technology, business, world, science, health, entertainment
- **News Sources**: BBC, Reuters, NPR, NYT, AP, TechCrunch
- **Sports Leagues**: NFL, MLB, NHL, NBA, MLS, ATP, PGA
- **Weather Locations**: Add multiple locations with lat/lon
- **Fun Segments**: This Day in History, Quote of the Day, Market Minute, Word of the Day, Dad Joke, Sports History
- **Duration**: 5, 10, 15, or 20 minutes

### Schedule Settings

- Enable/disable automatic generation
- Select days of week
- Set generation time
- Configure timezone

## Customization

### Adding Custom Audio Assets

Replace the placeholder audio files in `backend/assets/`:
- `intro.mp3` - Intro music/jingle
- `transition.mp3` - Transition sound between segments
- `outro.mp3` - Outro music

### Adding Voice Profiles

Edit `backend/src/audio/tts.py` to add more ElevenLabs voice mappings for different demographics.

## Cost Estimates

| Service | Estimated Monthly Cost |
|---------|----------------------|
| Data APIs | $0 (using free tiers) |
| ElevenLabs | ~$22 (Creator plan) |
| Claude API | ~$10-30 (usage-based) |
| **Total** | **$32-52/month** |

## Development

### Running Tests

```bash
# Backend
cd backend && pytest

# iOS
cd ios && npm test
```

### Code Quality

```bash
# Backend
cd backend && ruff check src/

# iOS
cd ios && npm run lint
```

## Troubleshooting

### Backend won't start
- Check that all required environment variables are set
- Ensure Docker is running if using docker-compose
- Verify port 8000 is not in use

### iOS app can't connect to backend
- Ensure backend is running and accessible
- Check the server URL in app settings
- For simulators, use your machine's IP address, not localhost

### CarPlay not showing
- Ensure the app is built with CarPlay entitlements
- Test on a real device or CarPlay simulator

### Audio generation fails
- Verify ElevenLabs API key is valid
- Check API rate limits
- Ensure FFmpeg is installed (in Docker image by default)

## License

MIT
