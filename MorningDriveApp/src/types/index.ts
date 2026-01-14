/**
 * Type definitions for Morning Drive app
 */

// === API Types ===

export interface WeatherLocation {
  name: string;
  lat: number;
  lon: number;
}

export interface SportsTeam {
  name: string;
  league: string;
  team_id?: string;
}

export interface BriefingSegment {
  type: string;
  start_time: number;
  end_time: number;
  title: string;
}

export interface Briefing {
  id: number;
  created_at: string;
  title: string;
  duration_seconds: number;
  audio_url: string;
  status: string;
  segments: BriefingSegment[];
}

export interface BriefingListResponse {
  briefings: Briefing[];
  total: number;
}

export interface GenerationError {
  phase: string;
  component: string;
  message: string;
  recoverable: boolean;
  fallback_description?: string;
}

export interface PendingAction {
  action_id: string;
  error: GenerationError;
  options: string[];
}

export interface GenerationStatus {
  briefing_id: number;
  status: string;  // pending, gathering_content, writing_script, generating_audio, awaiting_confirmation, completed, completed_with_warnings, failed, cancelled
  progress_percent: number;
  current_step?: string;
  error?: string;
  errors: GenerationError[];
  pending_action?: PendingAction;
}

export type BriefingLength = 'short' | 'long';

export interface UserSettings {
  news_topics: string[];
  news_sources: string[];
  sports_teams: SportsTeam[];
  sports_leagues: string[];
  weather_locations: WeatherLocation[];
  fun_segments: string[];
  briefing_length: BriefingLength;
  include_intro_music: boolean;
  include_transitions: boolean;
  news_exclusions: string[];
  voice_id: string;
  voice_style: string;
  voice_speed: number;
  tts_provider: string;
  segment_order: string[];
  include_music: boolean;
  writing_style: string;
  deep_dive_enabled: boolean;
  updated_at: string;
}

export interface Schedule {
  id: number;
  enabled: boolean;
  days_of_week: number[];
  time_hour: number;
  time_minute: number;
  timezone: string;
  next_run?: string;
}

export interface VoiceInfo {
  voice_id: string;
  name: string;
  labels?: Record<string, string>;
  description?: string;
}

// === App State Types ===

export type PlaybackState = 'idle' | 'loading' | 'playing' | 'paused' | 'error';

export interface PlayerState {
  currentBriefing: Briefing | null;
  playbackState: PlaybackState;
  position: number;
  duration: number;
  currentSegment: BriefingSegment | null;
}

// === Navigation Types ===

export type RootStackParamList = {
  Main: undefined;
  Player: { briefingId: number };
  Settings: undefined;
  Teams: undefined;
  NewsTopics: undefined;
  Locations: undefined;
  Schedule: undefined;
};

export type MainTabParamList = {
  Home: undefined;
  Library: undefined;
  SettingsTab: undefined;
};

// === Constants ===

export const NEWS_TOPICS = [
  { id: 'top', label: 'Top Stories' },
  { id: 'world', label: 'World News' },
  { id: 'technology', label: 'Technology' },
  { id: 'business', label: 'Business' },
  { id: 'science', label: 'Science' },
  { id: 'health', label: 'Health' },
  { id: 'entertainment', label: 'Entertainment' },
] as const;

export const NEWS_SOURCES = [
  { id: 'bbc', label: 'BBC News' },
  { id: 'reuters', label: 'Reuters' },
  { id: 'npr', label: 'NPR' },
  { id: 'nyt', label: 'New York Times' },
  { id: 'ap', label: 'Associated Press' },
  { id: 'techcrunch', label: 'TechCrunch' },
  { id: 'hackernews', label: 'Hacker News' },
  { id: 'arstechnica', label: 'Ars Technica' },
] as const;

export const SPORTS_LEAGUES = [
  { id: 'nfl', label: 'NFL' },
  { id: 'mlb', label: 'MLB' },
  { id: 'nhl', label: 'NHL' },
  { id: 'nba', label: 'NBA' },
  { id: 'mls', label: 'MLS' },
  { id: 'premier_league', label: 'Premier League' },
  { id: 'atp', label: 'ATP Tennis' },
  { id: 'wta', label: 'WTA Tennis' },
  { id: 'pga', label: 'PGA Golf' },
] as const;

export const FUN_SEGMENTS = [
  { id: 'this_day_in_history', label: 'This Day in History' },
  { id: 'quote_of_the_day', label: 'Quote of the Day' },
  { id: 'market_minute', label: 'Market Minute' },
  { id: 'word_of_the_day', label: 'Word of the Day' },
  { id: 'dad_joke', label: 'Dad Joke' },
  { id: 'sports_history', label: 'Sports History' },
] as const;

export const DAYS_OF_WEEK = [
  { id: 0, label: 'Monday', short: 'Mon' },
  { id: 1, label: 'Tuesday', short: 'Tue' },
  { id: 2, label: 'Wednesday', short: 'Wed' },
  { id: 3, label: 'Thursday', short: 'Thu' },
  { id: 4, label: 'Friday', short: 'Fri' },
  { id: 5, label: 'Saturday', short: 'Sat' },
  { id: 6, label: 'Sunday', short: 'Sun' },
] as const;

// ElevenLabs voice options (stock voices)
export const ELEVENLABS_VOICE_OPTIONS = [
  { id: '21m00Tcm4TlvDq8ikWAM', label: 'Rachel', description: 'Female, American' },
  { id: 'pNInz6obpgDQGcFmaJgB', label: 'Adam', description: 'Male, American' },
  { id: 'VR6AewLTigWG4xSOukaG', label: 'Arnold', description: 'Male, American (mature)' },
] as const;

// Chatterbox voice options (self-hosted TTS)
export const CHATTERBOX_VOICE_OPTIONS = [
  { id: 'timmy', label: 'Timmy', description: 'Custom voice clone' },
  { id: 'austin', label: 'Austin', description: 'Male, American' },
  { id: 'alice', label: 'Alice', description: 'Female, American' },
] as const;

// Legacy alias for backwards compatibility
export const VOICE_OPTIONS = ELEVENLABS_VOICE_OPTIONS;

// Default voice IDs per provider
export const DEFAULT_VOICE_IDS = {
  elevenlabs: 'pNInz6obpgDQGcFmaJgB',  // Adam
  chatterbox: 'timmy',
  edge: 'en-US-GuyNeural',  // Not selectable, but here for reference
} as const;

export const VOICE_STYLES = [
  { id: 'energetic', label: 'Energetic', description: 'Upbeat morning show vibe' },
  { id: 'professional', label: 'Professional', description: 'News anchor style' },
  { id: 'calm', label: 'Calm', description: 'Relaxed and soothing' },
] as const;

export const WRITING_STYLES = [
  { id: 'good_morning_america', label: 'Good Morning, America', description: 'Upbeat, energetic morning show' },
  { id: 'firing_line', label: 'Firing Line', description: 'Intellectual wit of William F. Buckley' },
  { id: 'ernest_hemingway', label: 'Ernest Hemingway', description: 'Terse, direct literary style' },
] as const;

export const SEGMENT_TYPES = [
  { id: 'news', label: 'News', icon: 'newspaper-outline' },
  { id: 'sports', label: 'Sports', icon: 'football-outline' },
  { id: 'weather', label: 'Weather', icon: 'cloudy-outline' },
  { id: 'fun', label: 'Fun Segments', icon: 'happy-outline' },
] as const;

export const DEFAULT_SEGMENT_ORDER = ['news', 'sports', 'weather', 'fun'];

export const BRIEFING_LENGTHS = [
  {
    id: 'short' as BriefingLength,
    label: 'Short',
    description: '~5 minutes • Key headlines, favorite teams only',
  },
  {
    id: 'long' as BriefingLength,
    label: 'Long',
    description: '~10 minutes • More stories, full sports coverage',
  },
] as const;
