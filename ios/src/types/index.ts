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

export interface GenerationStatus {
  briefing_id: number;
  status: string;
  progress_percent: number;
  current_step?: string;
  error?: string;
}

export interface UserSettings {
  news_topics: string[];
  news_sources: string[];
  sports_teams: SportsTeam[];
  sports_leagues: string[];
  weather_locations: WeatherLocation[];
  fun_segments: string[];
  duration_minutes: number;
  include_intro_music: boolean;
  include_transitions: boolean;
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
