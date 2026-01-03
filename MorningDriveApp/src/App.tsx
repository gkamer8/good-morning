/**
 * Morning Drive - Main App Component
 */

import React, { useEffect, useCallback, useRef } from 'react';
import { StatusBar, LogBox } from 'react-native';

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
]);
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { HomeScreen } from './screens/HomeScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { PlayerScreen } from './screens/PlayerScreen';
import { setupPlayer } from './services/audio';
import { api } from './services/api';
import { useAppConfigStore, useBriefingsStore } from './store';
import { setupCarPlay, updateBriefingsList } from './services/carplay';

// Create query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 2,
    },
  },
});

const Stack = createNativeStackNavigator();

function AppContent() {
  const { setConnected } = useAppConfigStore();
  const { briefings, setCurrentBriefing } = useBriefingsStore();
  const isInitialized = useRef(false);

  const handleBriefingSelect = useCallback(
    (briefing: import('./types').Briefing) => {
      setCurrentBriefing(briefing);
    },
    [setCurrentBriefing]
  );

  useEffect(() => {
    // Only initialize once
    if (isInitialized.current) return;
    isInitialized.current = true;

    const init = async () => {
      try {
        // Initialize API
        await api.init();

        // Check server connection
        const isHealthy = await api.healthCheck();
        setConnected(isHealthy);

        // Setup audio player
        try {
          await setupPlayer();
        } catch (audioError) {
          console.warn('Audio player setup failed:', audioError);
          // Continue without audio - user can retry later
        }

        // Setup CarPlay
        try {
          setupCarPlay(briefings, handleBriefingSelect);
        } catch (carplayError) {
          console.warn('CarPlay setup failed:', carplayError);
          // CarPlay is optional, continue without it
        }
      } catch (error) {
        console.error('App initialization failed:', error);
        setConnected(false);
      }
    };

    init();
  }, [setConnected, briefings, handleBriefingSelect]);

  // Update CarPlay when briefings change
  useEffect(() => {
    try {
      updateBriefingsList(briefings, handleBriefingSelect);
    } catch (error) {
      console.warn('Failed to update CarPlay briefings list:', error);
    }
  }, [briefings, handleBriefingSelect]);

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
