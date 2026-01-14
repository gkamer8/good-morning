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
import { authService, AuthResponse, TokenPair, AppleSignInRequest } from './auth';

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
    options: RequestInit = {},
    skipAuth: boolean = false
  ): Promise<T> {
    const url = `${this.baseUrl}/api${endpoint}`;

    // Build headers with auth token if available
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    const accessToken = authService.getAccessToken();
    if (accessToken && !skipAuth) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }

    let response = await fetch(url, {
      ...options,
      headers,
    });

    // Handle 401 - try token refresh
    if (response.status === 401 && accessToken && !skipAuth) {
      const refreshed = await this.tryRefreshToken();
      if (refreshed) {
        // Retry with new token
        headers['Authorization'] = `Bearer ${authService.getAccessToken()}`;
        response = await fetch(url, {
          ...options,
          headers,
        });
      }
    }

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API Error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  /**
   * Try to refresh the access token using the refresh token.
   * Returns true if successful.
   */
  private async tryRefreshToken(): Promise<boolean> {
    const refreshToken = authService.getRefreshToken();
    if (!refreshToken) {
      return false;
    }

    try {
      const tokens = await this.refreshTokens(refreshToken);
      await authService.storeTokens(tokens);
      return true;
    } catch (error) {
      console.log('[API] Token refresh failed:', error);
      await authService.clearTokens();
      return false;
    }
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

  async cancelBriefing(id: number): Promise<{ status: string; briefing_id: number }> {
    return this.request(`/briefings/${id}/cancel`, { method: 'POST' });
  }

  getAudioUrl(audioPath: string): string {
    // audioPath is like "/audio/briefing_1_abc123.mp3"
    return `${this.baseUrl}${audioPath}`;
  }

  getVoicePreviewUrl(voiceId: string): string {
    return `${this.baseUrl}/api/voices/${voiceId}/preview`;
  }

  // === Voices ===

  async listVoices(ttsProvider?: string): Promise<{ voices: VoiceInfo[]; total: number }> {
    const params = ttsProvider ? `?tts_provider=${ttsProvider}` : '';
    return this.request<{ voices: VoiceInfo[]; total: number }>(`/voices${params}`);
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

  // === Auth ===

  async appleSignIn(data: AppleSignInRequest): Promise<AuthResponse> {
    return this.request<AuthResponse>(
      '/auth/apple',
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
      true // Skip auth - this is the login endpoint
    );
  }

  async refreshTokens(refreshToken: string): Promise<TokenPair> {
    return this.request<TokenPair>(
      '/auth/refresh',
      {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      },
      true // Skip auth - uses refresh token in body
    );
  }
}

export const api = new ApiClient();
