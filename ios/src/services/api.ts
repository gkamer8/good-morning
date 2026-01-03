/**
 * API client for Morning Drive backend
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  Briefing,
  BriefingListResponse,
  GenerationStatus,
  Schedule,
  UserSettings,
} from '../types';

// Default to localhost for development
const DEFAULT_BASE_URL = 'http://localhost:8000';

class ApiClient {
  private baseUrl: string = DEFAULT_BASE_URL;

  async init() {
    const savedUrl = await AsyncStorage.getItem('api_base_url');
    if (savedUrl) {
      this.baseUrl = savedUrl;
    }
  }

  async setBaseUrl(url: string) {
    this.baseUrl = url;
    await AsyncStorage.setItem('api_base_url', url);
  }

  getBaseUrl() {
    return this.baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}/api${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API Error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  // === Briefings ===

  async generateBriefing(options?: {
    override_duration_minutes?: number;
    override_topics?: string[];
  }): Promise<GenerationStatus> {
    return this.request<GenerationStatus>('/briefings/generate', {
      method: 'POST',
      body: JSON.stringify(options || {}),
    });
  }

  async listBriefings(limit = 10, offset = 0): Promise<BriefingListResponse> {
    return this.request<BriefingListResponse>(
      `/briefings?limit=${limit}&offset=${offset}`
    );
  }

  async getBriefing(id: number): Promise<Briefing> {
    return this.request<Briefing>(`/briefings/${id}`);
  }

  async getBriefingStatus(id: number): Promise<GenerationStatus> {
    return this.request<GenerationStatus>(`/briefings/${id}/status`);
  }

  async deleteBriefing(id: number): Promise<void> {
    await this.request(`/briefings/${id}`, { method: 'DELETE' });
  }

  getAudioUrl(audioPath: string): string {
    // audioPath is like "/audio/briefing_1_abc123.mp3"
    return `${this.baseUrl}${audioPath}`;
  }

  // === Settings ===

  async getSettings(): Promise<UserSettings> {
    return this.request<UserSettings>('/settings');
  }

  async updateSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
    return this.request<UserSettings>('/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  // === Schedule ===

  async getSchedule(): Promise<Schedule> {
    return this.request<Schedule>('/schedule');
  }

  async updateSchedule(schedule: Partial<Schedule>): Promise<Schedule> {
    return this.request<Schedule>('/schedule', {
      method: 'PUT',
      body: JSON.stringify(schedule),
    });
  }

  // === Health ===

  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }
}

export const api = new ApiClient();
