/**
 * Authentication service for Apple Sign-In and token management
 */

import * as Keychain from 'react-native-keychain';

const KEYCHAIN_SERVICE = 'com.g0rdon.morning-drive';
const ACCESS_TOKEN_USERNAME = 'access_token';
const REFRESH_TOKEN_USERNAME = 'refresh_token';

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthResponse {
  user_id: number;
  display_name: string | null;
  email: string | null;
  tokens: TokenPair;
  is_new_user: boolean;
}

export interface AppleSignInRequest {
  identity_token: string;
  user_name?: string;
  invite_code?: string;
}

class AuthService {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private isInitialized: boolean = false;

  /**
   * Initialize the auth service by loading tokens from Keychain.
   * Returns true if tokens were found.
   */
  async init(): Promise<boolean> {
    if (this.isInitialized) {
      return this.accessToken !== null;
    }

    try {
      const accessCreds = await Keychain.getGenericPassword({
        service: `${KEYCHAIN_SERVICE}.${ACCESS_TOKEN_USERNAME}`,
      });
      const refreshCreds = await Keychain.getGenericPassword({
        service: `${KEYCHAIN_SERVICE}.${REFRESH_TOKEN_USERNAME}`,
      });

      if (accessCreds && refreshCreds) {
        this.accessToken = accessCreds.password;
        this.refreshToken = refreshCreds.password;
        this.isInitialized = true;
        return true;
      }
    } catch (error) {
      console.log('[Auth] Failed to load tokens from Keychain:', error);
    }

    this.isInitialized = true;
    return false;
  }

  /**
   * Get the current access token, or null if not authenticated.
   */
  getAccessToken(): string | null {
    return this.accessToken;
  }

  /**
   * Get the current refresh token, or null if not authenticated.
   */
  getRefreshToken(): string | null {
    return this.refreshToken;
  }

  /**
   * Check if the user is authenticated.
   */
  isAuthenticated(): boolean {
    return this.accessToken !== null;
  }

  /**
   * Store tokens securely in Keychain.
   */
  async storeTokens(tokens: TokenPair): Promise<void> {
    this.accessToken = tokens.access_token;
    this.refreshToken = tokens.refresh_token;

    await Keychain.setGenericPassword(ACCESS_TOKEN_USERNAME, tokens.access_token, {
      service: `${KEYCHAIN_SERVICE}.${ACCESS_TOKEN_USERNAME}`,
    });
    await Keychain.setGenericPassword(REFRESH_TOKEN_USERNAME, tokens.refresh_token, {
      service: `${KEYCHAIN_SERVICE}.${REFRESH_TOKEN_USERNAME}`,
    });
  }

  /**
   * Clear stored tokens (logout).
   */
  async clearTokens(): Promise<void> {
    this.accessToken = null;
    this.refreshToken = null;

    await Keychain.resetGenericPassword({
      service: `${KEYCHAIN_SERVICE}.${ACCESS_TOKEN_USERNAME}`,
    });
    await Keychain.resetGenericPassword({
      service: `${KEYCHAIN_SERVICE}.${REFRESH_TOKEN_USERNAME}`,
    });
  }

  /**
   * Update the access token (used after refresh).
   */
  updateAccessToken(token: string): void {
    this.accessToken = token;
    Keychain.setGenericPassword(ACCESS_TOKEN_USERNAME, token, {
      service: `${KEYCHAIN_SERVICE}.${ACCESS_TOKEN_USERNAME}`,
    });
  }
}

export const authService = new AuthService();
