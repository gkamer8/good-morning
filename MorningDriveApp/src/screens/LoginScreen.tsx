/**
 * Login screen for Apple Sign-In authentication
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Modal,
  SafeAreaView,
} from 'react-native';
import {
  appleAuth,
  AppleButton,
} from '@invertase/react-native-apple-authentication';
import Icon from 'react-native-vector-icons/Ionicons';

import { api } from '../services/api';
import { authService } from '../services/auth';
import { useAppConfigStore } from '../store';

interface LoginScreenProps {
  onLoginSuccess: () => void;
}

export function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const [inviteCode, setInviteCode] = useState('');
  const [showInviteInput, setShowInviteInput] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showServerSettings, setShowServerSettings] = useState(false);
  const [serverUrl, setServerUrl] = useState(api.getBaseUrl());
  const { setServerUrl: saveServerUrl, setConnected } = useAppConfigStore();

  const handleSaveServerUrl = async () => {
    let finalUrl = serverUrl.trim();
    if (!finalUrl) {
      Alert.alert('Error', 'Please enter a server URL');
      return;
    }
    if (!finalUrl.startsWith('http://') && !finalUrl.startsWith('https://')) {
      finalUrl = `http://${finalUrl}`;
      setServerUrl(finalUrl);
    }

    await api.setBaseUrl(finalUrl);
    saveServerUrl(finalUrl);

    // Test connection
    const result = await api.healthCheck();
    setConnected(result.ok);

    if (result.ok) {
      Alert.alert('Connected', `Successfully connected to ${finalUrl}`);
      setShowServerSettings(false);
    } else {
      Alert.alert('Connection Failed', result.error || 'Could not connect to server');
    }
  };

  const handleAppleSignIn = async () => {
    setError(null);
    setIsLoading(true);

    try {
      // Perform Apple Sign-In
      const appleAuthResponse = await appleAuth.performRequest({
        requestedOperation: appleAuth.Operation.LOGIN,
        requestedScopes: [appleAuth.Scope.EMAIL, appleAuth.Scope.FULL_NAME],
      });

      // Get the identity token
      const { identityToken, fullName } = appleAuthResponse;

      if (!identityToken) {
        throw new Error('Apple Sign-In failed: No identity token received');
      }

      // Build user name from Apple response (only provided on first sign-in)
      let userName: string | undefined;
      if (fullName?.givenName || fullName?.familyName) {
        userName = [fullName.givenName, fullName.familyName]
          .filter(Boolean)
          .join(' ');
      }

      // Send to backend
      const response = await api.appleSignIn({
        identity_token: identityToken,
        user_name: userName,
        invite_code: showInviteInput ? inviteCode.trim() : undefined,
      });

      // Store tokens
      await authService.storeTokens(response.tokens);

      // Success - navigate to main app
      onLoginSuccess();
    } catch (err: any) {
      console.log('[LoginScreen] Sign-in error:', err);

      // Handle specific error cases
      const errorMessage = err.message || 'Unknown error';

      if (errorMessage.includes('invite code required') || errorMessage.includes('Invite code required')) {
        // User needs to enter an invite code
        setShowInviteInput(true);
        setError('An invite code is required to create a new account.');
      } else if (errorMessage.includes('Invalid invite code') || errorMessage.includes('expired')) {
        setError('Invalid or expired invite code. Please check and try again.');
      } else if (errorMessage.includes('cancelled') || err.code === '1001') {
        // User cancelled - no error to show
        setError(null);
      } else {
        setError(errorMessage);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.content}>
        {/* Logo/Header */}
        <View style={styles.header}>
          <Icon name="sunny" size={64} color="#4f46e5" />
          <Text style={styles.title}>Morning Drive</Text>
          <Text style={styles.subtitle}>
            Your personalized morning briefing
          </Text>
        </View>

        {/* Error Message */}
        {error && (
          <View style={styles.errorContainer}>
            <Icon name="alert-circle" size={20} color="#dc2626" />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* Invite Code Input */}
        {showInviteInput && (
          <View style={styles.inviteContainer}>
            <Text style={styles.inviteLabel}>Invite Code</Text>
            <TextInput
              style={styles.inviteInput}
              value={inviteCode}
              onChangeText={setInviteCode}
              placeholder="Enter your invite code"
              placeholderTextColor="#999"
              autoCapitalize="none"
              autoCorrect={false}
            />
            <Text style={styles.inviteHint}>
              Don't have an invite code? Contact the app administrator.
            </Text>
          </View>
        )}

        {/* Sign In Button */}
        <View style={styles.buttonContainer}>
          {isLoading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#4f46e5" />
              <Text style={styles.loadingText}>Signing in...</Text>
            </View>
          ) : (
            <>
              <AppleButton
                buttonStyle={AppleButton.Style.BLACK}
                buttonType={AppleButton.Type.SIGN_IN}
                style={styles.appleButton}
                onPress={handleAppleSignIn}
              />

              {showInviteInput && (
                <TouchableOpacity
                  style={styles.backButton}
                  onPress={() => {
                    setShowInviteInput(false);
                    setInviteCode('');
                    setError(null);
                  }}
                >
                  <Text style={styles.backButtonText}>
                    Already have an account? Try again
                  </Text>
                </TouchableOpacity>
              )}
            </>
          )}
        </View>

        {/* Footer - hide when invite input is shown to avoid keyboard overlap */}
        {!showInviteInput && (
          <View style={styles.footer}>
            <Text style={styles.footerText}>
              By signing in, you agree to our Terms of Service and Privacy Policy
            </Text>
          </View>
        )}

        {/* Settings Gear Icon - Top Right */}
        <TouchableOpacity
          style={styles.gearButton}
          onPress={() => setShowServerSettings(true)}
        >
          <Icon name="settings-outline" size={24} color="#999" />
        </TouchableOpacity>
      </View>

      {/* Server Settings Modal */}
      <Modal
        visible={showServerSettings}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowServerSettings(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Server Settings</Text>
            <TouchableOpacity onPress={() => setShowServerSettings(false)}>
              <Icon name="close" size={28} color="#333" />
            </TouchableOpacity>
          </View>
          <View style={styles.modalContent}>
            <Text style={styles.inviteLabel}>Server URL</Text>
            <TextInput
              style={styles.inviteInput}
              value={serverUrl}
              onChangeText={setServerUrl}
              placeholder="https://morning.g0rdon.com"
              placeholderTextColor="#999"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
            />
            <Text style={styles.serverHint}>
              For local development, use your Mac's IP address (e.g., http://10.0.0.173:8000)
            </Text>
            <TouchableOpacity style={styles.saveButton} onPress={handleSaveServerUrl}>
              <Text style={styles.saveButtonText}>Save & Connect</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f7',
  },
  content: {
    flex: 1,
    paddingHorizontal: 32,
    justifyContent: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: 48,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: '#1a1a2e',
    marginTop: 16,
  },
  subtitle: {
    fontSize: 16,
    color: '#666',
    marginTop: 8,
    textAlign: 'center',
  },
  errorContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fef2f2',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
    gap: 12,
  },
  errorText: {
    flex: 1,
    fontSize: 14,
    color: '#dc2626',
    lineHeight: 20,
  },
  inviteContainer: {
    marginBottom: 24,
  },
  inviteLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#666',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  inviteInput: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: '#1a1a2e',
  },
  inviteHint: {
    fontSize: 13,
    color: '#888',
    marginTop: 8,
    textAlign: 'center',
  },
  buttonContainer: {
    alignItems: 'center',
  },
  appleButton: {
    width: '100%',
    height: 50,
  },
  loadingContainer: {
    alignItems: 'center',
    padding: 16,
  },
  loadingText: {
    fontSize: 14,
    color: '#666',
    marginTop: 12,
  },
  backButton: {
    marginTop: 16,
    padding: 12,
  },
  backButtonText: {
    fontSize: 14,
    color: '#4f46e5',
    textAlign: 'center',
  },
  gearButton: {
    position: 'absolute',
    top: 60,
    right: 20,
    padding: 8,
  },
  modalContainer: {
    flex: 1,
    backgroundColor: '#f5f5f7',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
    backgroundColor: '#fff',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1a1a2e',
  },
  modalContent: {
    padding: 20,
  },
  serverHint: {
    fontSize: 13,
    color: '#888',
    marginTop: 8,
  },
  saveButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 12,
    padding: 14,
    marginTop: 24,
    alignItems: 'center',
  },
  saveButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    position: 'absolute',
    bottom: 48,
    left: 32,
    right: 32,
  },
  footerText: {
    fontSize: 12,
    color: '#999',
    textAlign: 'center',
    lineHeight: 18,
  },
});
