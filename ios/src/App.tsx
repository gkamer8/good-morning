/**
 * Morning Drive - Main App Component
 */

import React, { useEffect } from 'react';
import { StatusBar } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TrackPlayer from 'react-native-track-player';

import { HomeScreen } from './screens/HomeScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { setupPlayer, playbackService } from './services/audio';
import { api } from './services/api';
import { useAppConfigStore, useBriefingsStore } from './store';
import { setupCarPlay, updateBriefingsList } from './services/carplay';

// Register playback service
TrackPlayer.registerPlaybackService(() => playbackService);

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
  const { setConnected, serverUrl } = useAppConfigStore();
  const { briefings, setCurrentBriefing } = useBriefingsStore();

  useEffect(() => {
    // Initialize app
    const init = async () => {
      // Initialize API
      await api.init();

      // Check server connection
      const isHealthy = await api.healthCheck();
      setConnected(isHealthy);

      // Setup audio player
      await setupPlayer();

      // Setup CarPlay
      setupCarPlay(briefings, (briefing) => {
        setCurrentBriefing(briefing);
      });
    };

    init();
  }, []);

  // Update CarPlay when briefings change
  useEffect(() => {
    updateBriefingsList(briefings, (briefing) => {
      setCurrentBriefing(briefing);
    });
  }, [briefings]);

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
