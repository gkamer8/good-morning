/**
 * Morning Drive - Main App Component
 */

import React, { useEffect, useCallback, useRef, useState } from 'react';
import { StatusBar, LogBox, View, ActivityIndicator, StyleSheet } from 'react-native';

// Suppress common warnings that don't affect functionality
LogBox.ignoreLogs([
  'Sending `onAnimatedValueUpdate` with no listeners registered',
  'Non-serializable values were found in the navigation state',
  'ViewPropTypes will be removed from React Native',
  'new NativeEventEmitter',
  'Debugger and device times have drifted',
  'Remote debugger is in a background tab',
  'Require cycle:',
  // TrackPlayer sleep timer warnings (methods not implemented in native module)
  'getSleepTimerProgress',
  'setSleepTimer',
  'sleepWhenActiveTrackReachesEnd',
  'clearSleepTimer',
  'The Objective-C',
  'JS method will not be available',
  // Apple Auth and Keychain warnings
  'RNAppleAuthentication',
  'RNKeychain',
  // Modal and presentation warnings
  'Modal',
  'presentationStyle',
]);
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { HomeScreen } from './screens/HomeScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { PlayerScreen } from './screens/PlayerScreen';
import { LoginScreen } from './screens/LoginScreen';
import { setupPlayer } from './services/audio';
import { api } from './services/api';
import { authService } from './services/auth';
import { useAppConfigStore, useBriefingsStore, useAuthStore } from './store';
import { setupCarPlay, updateBriefingsList } from './services/carplay';
import { RootStackParamList } from './types';

// Create query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 2,
    },
  },
});

const Stack = createNativeStackNavigator<RootStackParamList>();

function AppContent() {
  const { serverUrl, setConnected, _hasHydrated } = useAppConfigStore();
  const { briefings, setCurrentBriefing } = useBriefingsStore();
  const { isAuthenticated, isInitialized, setAuthenticated, setInitialized } =
    useAuthStore();
  const [isApiReady, setApiReady] = useState(false);

  const handleBriefingSelect = useCallback(
    (briefing: import('./types').Briefing) => {
      setCurrentBriefing(briefing);
    },
    [setCurrentBriefing]
  );

  const handleLoginSuccess = useCallback(() => {
    setAuthenticated(true);
    // Invalidate all queries to refresh data with new user
    queryClient.invalidateQueries();
  }, [setAuthenticated]);

  // Wait for Zustand to hydrate, then initialize API and auth
  useEffect(() => {
    if (!_hasHydrated) return;

    const init = async () => {
      try {
        // Set API base URL directly from hydrated Zustand store
        // This is the persisted URL the user configured
        await api.setBaseUrl(serverUrl);

        // Initialize auth service and check for existing tokens
        const hasTokens = await authService.init();
        setAuthenticated(hasTokens);
        setInitialized(true);

        // Mark API as ready BEFORE health check so queries can start
        setApiReady(true);

        // Check server connection
        const healthResult = await api.healthCheck();
        setConnected(healthResult.ok);

        // Setup audio player
        try {
          await setupPlayer();
        } catch (audioError) {
          console.warn('Audio player setup failed:', audioError);
        }

        // Setup CarPlay
        try {
          setupCarPlay(briefings, handleBriefingSelect);
        } catch (carplayError) {
          console.warn('CarPlay setup failed:', carplayError);
        }
      } catch (error) {
        console.error('App initialization failed:', error);
        setConnected(false);
        setInitialized(true);
        setApiReady(true);
      }
    };

    init();
  }, [_hasHydrated, serverUrl, setConnected, setAuthenticated, setInitialized, briefings, handleBriefingSelect]);

  // Sync API URL when serverUrl changes in Zustand store
  useEffect(() => {
    if (isApiReady && serverUrl && serverUrl !== api.getBaseUrl()) {
      api.setBaseUrl(serverUrl);
    }
  }, [serverUrl, isApiReady]);

  // Update CarPlay when briefings change
  useEffect(() => {
    if (!isApiReady) return;
    try {
      updateBriefingsList(briefings, handleBriefingSelect);
    } catch (error) {
      console.warn('Failed to update CarPlay briefings list:', error);
    }
  }, [briefings, handleBriefingSelect, isApiReady]);

  // Show loading screen until Zustand hydrates, API is initialized, and auth is checked
  if (!_hasHydrated || !isApiReady || !isInitialized) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#4f46e5" />
      </View>
    );
  }

  // Show login screen if not authenticated
  if (!isAuthenticated) {
    return (
      <>
        <StatusBar barStyle="dark-content" />
        <LoginScreen onLoginSuccess={handleLoginSuccess} />
      </>
    );
  }

  return (
    <NavigationContainer>
      <StatusBar barStyle="dark-content" />
      <Stack.Navigator
        screenOptions={{
          headerShown: false,
        }}
      >
        <Stack.Screen name="Home" component={HomeScreen} />
        <Stack.Screen
          name="Settings"
          component={SettingsScreen}
          options={{
            presentation: 'modal',
          }}
        />
        <Stack.Screen
          name="Player"
          component={PlayerScreen}
          options={{
            presentation: 'modal',
            animation: 'slide_from_bottom',
          }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f5f5f7',
  },
});
