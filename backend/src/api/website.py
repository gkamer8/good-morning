"""Public website routes for Morning Drive."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from src.api.templates import base_page, docs_page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home_page():
    """Home page with overview and quick links."""
    content = """
    <div class="hero">
        <h1>Morning Drive</h1>
        <p>AI-powered personalized morning briefings with professional radio-style production</p>
        <a href="/docs/getting-started" class="btn">Get Started</a>
        <a href="/api/docs" class="btn">API Docs</a>
    </div>
    <div class="container">
        <div class="features">
            <div class="feature">
                <h3>Personalized Content</h3>
                <p>Get briefings tailored to your interests: news topics, sports teams, weather locations, and fun segments like "This Day in History."</p>
            </div>
            <div class="feature">
                <h3>Professional Audio</h3>
                <p>ElevenLabs text-to-speech with voice-matched quotes. Sounds like a real radio show with intro music and smooth transitions.</p>
            </div>
            <div class="feature">
                <h3>CarPlay Support</h3>
                <p>Listen to your morning briefings hands-free while driving with full CarPlay integration.</p>
            </div>
            <div class="feature">
                <h3>Scheduled Generation</h3>
                <p>Set your preferred time and days, and your briefing will be ready when you wake up.</p>
            </div>
            <div class="feature">
                <h3>AI-Powered Scripts</h3>
                <p>Claude generates natural, engaging scripts from multiple news sources, sports APIs, and weather data.</p>
            </div>
            <div class="feature">
                <h3>Classical Music</h3>
                <p>Each briefing includes a classical music piece with an introduction from the host.</p>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Quick Start</div>
            <div class="card-body">
                <p>Get Morning Drive running in minutes:</p>
                <pre><code># Clone and navigate to backend
cd morning-drive/backend

# Copy environment template and add your API keys
cp .env.example .env

# Start with Docker
docker-compose up -d

# Verify it's running
curl http://localhost:8000/health</code></pre>
                <p>See the <a href="/docs/getting-started">Getting Started guide</a> for detailed setup instructions.</p>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Documentation</div>
            <div class="card-body">
                <ul>
                    <li><a href="/docs/getting-started"><strong>Getting Started</strong></a> - Prerequisites, installation, and first briefing</li>
                    <li><a href="/docs/deployment"><strong>Deployment</strong></a> - Docker, production setup, and configuration</li>
                    <li><a href="/docs/development"><strong>Development</strong></a> - Local setup, testing, and code quality</li>
                    <li><a href="/docs/api-reference"><strong>API Reference</strong></a> - REST endpoints and usage examples</li>
                </ul>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Administration</div>
            <div class="card-body">
                <p>The <a href="/admin">Admin Panel</a> provides a web interface for managing your Morning Drive instance:</p>
                <ul>
                    <li>Upload and manage classical music pieces</li>
                    <li>View music library with metadata</li>
                </ul>
                <p><em>Note: Admin access requires a password (set via <code>ADMIN_PASSWORD</code> environment variable).</em></p>
            </div>
        </div>
    </div>
    """
    return base_page("Home", content)


@router.get("/docs/getting-started", response_class=HTMLResponse)
async def docs_getting_started():
    """Getting started documentation page."""
    content = """
    <p>This guide will help you set up Morning Drive and generate your first briefing.</p>

    <h3>Prerequisites</h3>
    <p>Before you begin, ensure you have:</p>
    <ul>
        <li><strong>Python 3.11+</strong> (for local development)</li>
        <li><strong>Docker &amp; Docker Compose</strong> (recommended for deployment)</li>
        <li><strong>Node.js 18+</strong> (for iOS app development)</li>
        <li><strong>Xcode</strong> (for iOS app building)</li>
    </ul>

    <h3>Required API Keys</h3>
    <table>
        <thead>
            <tr><th>Service</th><th>Purpose</th><th>Get Key</th></tr>
        </thead>
        <tbody>
            <tr><td>Anthropic</td><td>Claude AI for content generation</td><td><a href="https://console.anthropic.com">console.anthropic.com</a></td></tr>
            <tr><td>ElevenLabs</td><td>Text-to-speech</td><td><a href="https://elevenlabs.io">elevenlabs.io</a></td></tr>
        </tbody>
    </table>

    <div class="note">
        <strong>Note:</strong> Weather and news APIs are optional. Morning Drive uses free services (Open-Meteo for weather, RSS feeds for news) by default.
    </div>

    <h3>Step 1: Clone the Repository</h3>
    <pre><code>git clone https://github.com/gkamer8/good-morning.git
cd good-morning</code></pre>

    <h3>Step 2: Configure Environment</h3>
    <pre><code># Navigate to backend directory
cd backend

# Copy the environment template
cp .env.example .env

# Edit .env and add your API keys
nano .env</code></pre>

    <p>Required environment variables:</p>
    <pre><code>ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...
ADMIN_PASSWORD=your-secure-password</code></pre>

    <h3>Step 3: Start the Server</h3>
    <p><strong>Option A: Using Docker (Recommended)</strong></p>
    <pre><code>docker-compose up -d</code></pre>

    <p><strong>Option B: Running Locally</strong></p>
    <pre><code># Install dependencies
pip install -e .

# Start the server
python -m src.main</code></pre>

    <h3>Step 4: Verify Installation</h3>
    <pre><code># Check health endpoint
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "service": "morning-drive"}</code></pre>

    <h3>Step 5: Generate Your First Briefing</h3>
    <pre><code># Generate a briefing with default settings
curl -X POST http://localhost:8000/api/briefings/generate

# Check generation status
curl http://localhost:8000/api/briefings</code></pre>

    <h3>Next Steps</h3>
    <ul>
        <li>Set up the <a href="/docs/development">iOS app</a> to listen to your briefings</li>
        <li>Configure <a href="/docs/deployment">production deployment</a></li>
        <li>Customize user settings via the <a href="/docs/api-reference">API</a></li>
    </ul>
    """
    return docs_page("Getting Started", content, active_doc="getting-started")


@router.get("/docs/deployment", response_class=HTMLResponse)
async def docs_deployment():
    """Deployment documentation page."""
    content = """
    <p>This guide covers deploying Morning Drive to production environments.</p>

    <div class="note">
        <strong>Development vs Production:</strong> For local development with auto-reload, see the <a href="/docs/development">Development guide</a> and use <code>./dev.sh</code>. This page covers production deployment.
    </div>

    <h3>Docker Deployment (Production)</h3>
    <p>For production deployment without auto-reload:</p>
    <pre><code>cd good-morning/backend

# Create and configure environment
cp .env.example .env
nano .env  # Add your API keys

# Build and start (production mode)
docker compose -f docker-compose.yml up -d --build

# View logs
docker compose logs -f morning-drive</code></pre>

    <div class="warning">
        <strong>Note:</strong> Running <code>docker compose up</code> in the backend directory will automatically use the development override (with auto-reload). For production, explicitly specify <code>-f docker-compose.yml</code> to skip the override.
    </div>

    <h3>Services Overview</h3>
    <table>
        <thead>
            <tr><th>Service</th><th>Port</th><th>Description</th></tr>
        </thead>
        <tbody>
            <tr><td>morning-drive</td><td>8000</td><td>Main FastAPI application</td></tr>
            <tr><td>minio</td><td>9000, 9001</td><td>S3-compatible storage for music</td></tr>
            <tr><td>scheduler</td><td>-</td><td>Optional background job scheduler</td></tr>
        </tbody>
    </table>

    <h3>Environment Variables</h3>
    <table>
        <thead>
            <tr><th>Variable</th><th>Required</th><th>Description</th></tr>
        </thead>
        <tbody>
            <tr><td><code>ANTHROPIC_API_KEY</code></td><td>Yes</td><td>Claude API key for content generation</td></tr>
            <tr><td><code>ELEVENLABS_API_KEY</code></td><td>Yes</td><td>ElevenLabs API key for TTS</td></tr>
            <tr><td><code>ADMIN_PASSWORD</code></td><td>Yes</td><td>Password for admin panel access</td></tr>
            <tr><td><code>DATABASE_URL</code></td><td>No</td><td>Database connection string (default: SQLite)</td></tr>
            <tr><td><code>MINIO_ENDPOINT</code></td><td>No</td><td>MinIO server address</td></tr>
            <tr><td><code>MINIO_ACCESS_KEY</code></td><td>No</td><td>MinIO access key</td></tr>
            <tr><td><code>MINIO_SECRET_KEY</code></td><td>No</td><td>MinIO secret key</td></tr>
            <tr><td><code>DEBUG</code></td><td>No</td><td>Enable debug mode (default: false)</td></tr>
        </tbody>
    </table>

    <h3>Running the Scheduler</h3>
    <p>The scheduler service handles automatic briefing generation at scheduled times:</p>
    <pre><code># Start with scheduler enabled
docker-compose --profile with-scheduler up -d</code></pre>

    <h3>Production Considerations</h3>

    <div class="warning">
        <strong>Security:</strong> Always change the default admin password and MinIO credentials in production.
    </div>

    <h4>Reverse Proxy Setup (nginx)</h4>
    <pre><code>server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}</code></pre>

    <h4>SSL/TLS</h4>
    <p>Use Let's Encrypt with Certbot for free SSL certificates:</p>
    <pre><code>sudo certbot --nginx -d your-domain.com</code></pre>

    <h3>Persistent Storage</h3>
    <p>The Docker setup mounts these volumes for data persistence:</p>
    <ul>
        <li><code>./data</code> - SQLite database and generated audio files</li>
        <li><code>./assets</code> - Custom audio assets (intro, outro, transitions)</li>
        <li><code>minio_data</code> - Uploaded music files (Docker volume)</li>
    </ul>

    <h3>Health Checks</h3>
    <p>Monitor your deployment with the health endpoint:</p>
    <pre><code>curl http://localhost:8000/health
# {"status": "healthy", "service": "morning-drive"}</code></pre>

    <h3>Stopping the Server</h3>
    <pre><code># Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v</code></pre>
    """
    return docs_page("Deployment", content, active_doc="deployment")


@router.get("/docs/development", response_class=HTMLResponse)
async def docs_development():
    """Development documentation page."""
    content = """
    <p>This guide covers setting up a local development environment for Morning Drive.</p>

    <h3>Backend Development</h3>

    <h4>Quick Start (Recommended)</h4>
    <p>The easiest way to run the backend in development mode with auto-reload:</p>
    <pre><code># Navigate to backend directory
cd good-morning/backend

# Copy environment configuration
cp .env.example .env
# Edit .env with your API keys

# Start in development mode
./dev.sh</code></pre>

    <p>This script:</p>
    <ul>
        <li>Automatically detects your machine's IP address</li>
        <li>Starts the server with hot-reload enabled</li>
        <li>Mounts source code so changes apply instantly</li>
        <li>Starts MinIO for music storage</li>
    </ul>

    <div class="note">
        <strong>Auto-reload:</strong> When running via <code>dev.sh</code>, any changes to Python files in <code>src/</code> will automatically reload the server. No rebuild required!
    </div>

    <h4>Manual Setup (Without Docker)</h4>
    <pre><code># Navigate to backend directory
cd good-morning/backend

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install in development mode
pip install -e ".[dev]"

# Copy environment configuration
cp .env.example .env
# Edit .env with your API keys

# Start the development server
python -m src.main</code></pre>

    <h4>Running MinIO for Music Storage</h4>
    <pre><code># Start just the MinIO service (if not using dev.sh)
docker compose up -d minio

# MinIO Console: http://localhost:9001
# Default credentials: minioadmin / minioadmin</code></pre>

    <h4>Viewing Logs</h4>
    <pre><code># Follow backend logs
docker compose logs -f morning-drive

# View last 100 lines
docker compose logs --tail 100 morning-drive</code></pre>

    <h3>iOS App Development</h3>

    <h4>Prerequisites</h4>
    <ul>
        <li>macOS with Xcode installed</li>
        <li>Node.js 18+ and npm</li>
        <li>CocoaPods (<code>brew install cocoapods</code>)</li>
    </ul>

    <h4>Initial Setup</h4>
    <pre><code># Navigate to iOS app directory
cd good-morning/MorningDriveApp

# Install JavaScript dependencies
npm install

# Install iOS native dependencies
cd ios && pod install && cd ..</code></pre>

    <h4>Starting the Metro Bundler</h4>
    <p>Metro is the JavaScript bundler for React Native. It must be running for the app to load:</p>
    <pre><code># Start Metro (keep this terminal open)
npx react-native start

# Metro runs on http://localhost:8081</code></pre>

    <h4>Running on iOS Simulator</h4>
    <pre><code># In a new terminal, run the app
npx react-native run-ios

# Or specify a simulator
npx react-native run-ios --simulator="iPhone 15 Pro"</code></pre>

    <h4>Running on Physical iPhone</h4>
    <ol>
        <li>Connect your iPhone via USB</li>
        <li>Open <code>ios/MorningDriveApp.xcworkspace</code> in Xcode</li>
        <li>Select your device from the device dropdown</li>
        <li>Click the Run button (or press Cmd+R)</li>
    </ol>

    <div class="note">
        <strong>First-time setup:</strong> You'll need to configure code signing in Xcode with your Apple Developer account.
    </div>

    <h4>Connecting the App to Metro (Physical Device)</h4>
    <p>When running on a physical device, the app needs to connect to Metro on your computer:</p>
    <pre><code># Find your computer's IP address
ipconfig getifaddr en0  # macOS</code></pre>
    <p>On your iPhone:</p>
    <ol>
        <li>Shake the device to open the React Native dev menu</li>
        <li>Tap <strong>"Configure Bundler"</strong></li>
        <li>Enter your computer's IP (e.g., <code>192.168.1.100</code>) and port <code>8081</code></li>
        <li>Tap <strong>"Reload"</strong></li>
    </ol>

    <h4>Connecting the App to Backend Server</h4>
    <p>The app also needs to connect to the Morning Drive backend:</p>
    <ol>
        <li>Open the app and go to <strong>Settings</strong></li>
        <li>In the Server URL field, enter your backend URL (e.g., <code>http://192.168.1.100:8000</code>)</li>
        <li>Tap <strong>"Save & Connect"</strong></li>
    </ol>

    <div class="note">
        <strong>Tip:</strong> The backend admin panel shows the server URL you need. Log in at <code>http://localhost:8000/admin</code> to see it.
    </div>

    <h4>Troubleshooting</h4>
    <table>
        <thead>
            <tr><th>Problem</th><th>Solution</th></tr>
        </thead>
        <tbody>
            <tr><td>App shows white screen</td><td>Make sure Metro is running. Shake device and tap "Reload"</td></tr>
            <tr><td>Settings page stuck loading</td><td>Backend is unreachable. Check server URL in Settings (always visible at top)</td></tr>
            <tr><td>"Unable to load script"</td><td>Metro not reachable. Check IP and port in bundler settings</td></tr>
            <tr><td>Metro shows "BUNDLE" but app doesn't update</td><td>Shake device and tap "Reload", or restart Metro</td></tr>
            <tr><td>Can't connect to backend</td><td>Ensure phone and computer are on same WiFi network</td></tr>
        </tbody>
    </table>

    <h3>Running Tests</h3>

    <h4>Backend Tests</h4>
    <pre><code>cd morning-drive/backend

# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_api.py</code></pre>

    <h4>iOS Tests</h4>
    <pre><code>cd morning-drive/ios

# Run tests
npm test</code></pre>

    <h3>Code Quality</h3>

    <h4>Backend Linting</h4>
    <pre><code># Run ruff linter
ruff check src/

# Auto-fix issues
ruff check src/ --fix

# Format code
ruff format src/</code></pre>

    <h4>iOS Linting</h4>
    <pre><code># Run ESLint
npm run lint

# Fix auto-fixable issues
npm run lint -- --fix</code></pre>

    <h3>Project Structure</h3>
    <pre><code>morning-drive/
├── backend/
│   ├── src/
│   │   ├── api/          # REST API routes
│   │   ├── agents/       # Claude content generation
│   │   ├── tools/        # Data fetching (news, sports, weather)
│   │   ├── audio/        # TTS and audio mixing
│   │   ├── storage/      # Database and file storage
│   │   ├── config.py     # Application settings
│   │   ├── main.py       # FastAPI application
│   │   └── scheduler.py  # Background job scheduler
│   ├── assets/           # Audio assets (intro, outro, transitions)
│   ├── data/             # SQLite database, generated audio
│   ├── tests/            # Test suite
│   └── docker-compose.yml
└── ios/                  # React Native iOS app
    ├── src/
    │   ├── screens/      # App screens
    │   ├── components/   # Reusable components
    │   ├── services/     # API client, audio player
    │   └── store/        # State management (Zustand)
    └── ios/              # Native iOS project</code></pre>

    <h3>Custom Audio Assets</h3>
    <p>Replace placeholder audio in <code>backend/assets/</code>:</p>
    <ul>
        <li><code>intro.mp3</code> - Intro music/jingle</li>
        <li><code>transition.mp3</code> - Transition sound between segments</li>
        <li><code>outro.mp3</code> - Outro music</li>
    </ul>

    <h3>Useful Commands</h3>
    <pre><code># View backend logs
docker-compose logs -f morning-drive

# Restart a specific service
docker-compose restart morning-drive

# Access MinIO console
open http://localhost:9001

# Check API documentation
open http://localhost:8000/api/docs</code></pre>
    """
    return docs_page("Development", content, active_doc="development")


@router.get("/docs/api-reference", response_class=HTMLResponse)
async def docs_api_reference():
    """API reference documentation page."""
    content = """
    <p>Complete reference for the Morning Drive REST API. All endpoints use JSON for request/response bodies.</p>

    <div class="note">
        <strong>Interactive API Docs:</strong> Visit <a href="/api/docs">/api/docs</a> for auto-generated Swagger documentation with "Try it out" functionality.
    </div>

    <h3>Base URL</h3>
    <pre><code>http://localhost:8000/api</code></pre>

    <h3>Briefings</h3>

    <h4>Generate a New Briefing</h4>
    <pre><code>POST /api/briefings/generate

# Request body (optional - uses saved settings if omitted)
{
  "duration_minutes": 10
}

# Response
{
  "id": 1,
  "status": "pending",
  "created_at": "2024-01-15T08:00:00Z"
}</code></pre>

    <h4>List All Briefings</h4>
    <pre><code>GET /api/briefings?limit=10&amp;offset=0

# Response
{
  "items": [
    {
      "id": 1,
      "title": "Morning Briefing",
      "status": "completed",
      "duration_seconds": 600,
      "created_at": "2024-01-15T08:00:00Z"
    }
  ],
  "total": 1
}</code></pre>

    <h4>Get Briefing Details</h4>
    <pre><code>GET /api/briefings/{id}

# Response
{
  "id": 1,
  "title": "Morning Briefing",
  "status": "completed",
  "duration_seconds": 600,
  "audio_filename": "briefing_1.mp3",
  "segments_metadata": {...},
  "created_at": "2024-01-15T08:00:00Z"
}</code></pre>

    <h4>Get Generation Status</h4>
    <pre><code>GET /api/briefings/{id}/status

# Response
{
  "status": "generating_audio",
  "progress": 75,
  "current_step": "Generating segment 3 of 4"
}</code></pre>

    <h4>Delete a Briefing</h4>
    <pre><code>DELETE /api/briefings/{id}

# Response: 204 No Content</code></pre>

    <h3>User Settings</h3>

    <h4>Get Current Settings</h4>
    <pre><code>GET /api/settings

# Response
{
  "news_topics": ["technology", "business"],
  "news_sources": ["BBC", "Reuters"],
  "sports_teams": [],
  "sports_leagues": ["NFL"],
  "weather_locations": [
    {"name": "New York", "lat": 40.7128, "lon": -74.006}
  ],
  "fun_segments": ["this_day_in_history", "quote_of_the_day"],
  "duration_minutes": 10,
  "voice_id": "21m00Tcm4TlvDq8ikWAM"
}</code></pre>

    <h4>Update Settings</h4>
    <pre><code>PUT /api/settings
Content-Type: application/json

{
  "news_topics": ["technology", "science"],
  "duration_minutes": 15
}

# Response: Updated settings object</code></pre>

    <h3>Schedule</h3>

    <h4>Get Schedule</h4>
    <pre><code>GET /api/schedule

# Response
{
  "enabled": true,
  "days_of_week": [1, 2, 3, 4, 5],
  "time_hour": 6,
  "time_minute": 30,
  "timezone": "America/New_York",
  "next_run": "2024-01-16T06:30:00-05:00"
}</code></pre>

    <h4>Update Schedule</h4>
    <pre><code>PUT /api/schedule
Content-Type: application/json

{
  "enabled": true,
  "days_of_week": [1, 2, 3, 4, 5],
  "time_hour": 7,
  "time_minute": 0,
  "timezone": "America/New_York"
}</code></pre>

    <h3>Voices</h3>

    <h4>List Available Voices</h4>
    <pre><code>GET /api/voices

# Response
{
  "voices": [
    {
      "voice_id": "21m00Tcm4TlvDq8ikWAM",
      "name": "Rachel",
      "category": "premade",
      "preview_url": "/api/voices/21m00Tcm4TlvDq8ikWAM/preview"
    }
  ]
}</code></pre>

    <h3>Music</h3>

    <h4>List Music Library</h4>
    <pre><code>GET /api/music

# Response
{
  "items": [
    {
      "id": 1,
      "title": "Moonlight Sonata",
      "composer": "Ludwig van Beethoven",
      "duration_seconds": 360,
      "is_active": true
    }
  ]
}</code></pre>

    <h4>Stream Music File</h4>
    <pre><code>GET /api/music/{id}/stream

# Returns audio/mpeg stream</code></pre>

    <h3>Health Check</h3>
    <pre><code>GET /health

# Response
{
  "status": "healthy",
  "service": "morning-drive"
}</code></pre>

    <h3>Briefing Status Values</h3>
    <table>
        <thead>
            <tr><th>Status</th><th>Description</th></tr>
        </thead>
        <tbody>
            <tr><td><code>pending</code></td><td>Briefing queued, not yet started</td></tr>
            <tr><td><code>gathering_content</code></td><td>Fetching news, sports, weather data</td></tr>
            <tr><td><code>writing_script</code></td><td>Claude is generating the script</td></tr>
            <tr><td><code>generating_audio</code></td><td>Converting script to speech</td></tr>
            <tr><td><code>completed</code></td><td>Ready to play</td></tr>
            <tr><td><code>failed</code></td><td>Generation failed (check errors)</td></tr>
        </tbody>
    </table>

    <h3>Error Responses</h3>
    <pre><code># 400 Bad Request
{
  "detail": "Invalid duration: must be between 5 and 30 minutes"
}

# 404 Not Found
{
  "detail": "Briefing not found"
}

# 500 Internal Server Error
{
  "detail": "Failed to generate briefing"
}</code></pre>
    """
    return docs_page("API Reference", content, active_doc="api-reference")


@router.get("/docs", response_class=HTMLResponse)
async def docs_index():
    """Redirect /docs to getting started page."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs/getting-started", status_code=302)
