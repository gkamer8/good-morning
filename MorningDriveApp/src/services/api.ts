/**
 * API client for Morning Drive backend
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  Briefing,
  BriefingLength,
  BriefingListResponse,
  GenerationStatus,
  Schedule,
  UserSettings,
  VoiceInfo,
} from '../types';

// Default server URL - production Cloudflare tunnel
const DEFAULT_BASE_URL = 'https://morning.g0rdon.com';

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
    override_length?: BriefingLength;
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

  async resolveBriefingError(
    id: number,
    actionId: string,
    decision: 'continue' | 'cancel' | 'retry'
  ): Promise<{ status: string; briefing_id: number; decision?: string }> {
    return this.request(`/briefings/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ action_id: actionId, decision }),
    });
  }

  async deleteBriefing(id: number): Promise<void> {
    await this.request(`/briefings/${id}`, { method: 'DELETE' });
  }

  getAudioUrl(audioPath: string): string {
    // audioPath is like "/audio/briefing_1_abc123.mp3"
    return `${this.baseUrl}${audioPath}`;
  }

  getVoicePreviewUrl(voiceId: string): string {
    return `${this.baseUrl}/api/voices/${voiceId}/preview`;
  }

  // === Voices ===

  async listVoices(): Promise<{ voices: VoiceInfo[]; total: number }> {
    return this.request<{ voices: VoiceInfo[]; total: number }>('/voices');
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

  async healthCheck(): Promise<{ ok: boolean; error?: string }> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        return { ok: true };
      } else {
        return { ok: false, error: `Server returned ${response.status}` };
      }
    } catch (error: any) {
      clearTimeout(timeoutId);

      if (error.name === 'AbortError') {
        return { ok: false, error: 'Connection timed out (5s)' };
      }

      // Provide more specific error messages
      const message = error.message || 'Unknown error';
      if (message.includes('Network request failed')) {
        return { ok: false, error: 'Network error - check IP and ensure phone is on same WiFi' };
      }

      return { ok: false, error: message };
    }
  }

  // Simple boolean version for backward compatibility
  async isHealthy(): Promise<boolean> {
    const result = await this.healthCheck();
    return result.ok;
  }
}

export const api = new ApiClient();
