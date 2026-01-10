/**
 * Home screen - main dashboard for Morning Drive
 */

import React, { useEffect, useCallback, useState, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  Alert,
  Animated,
  Easing,
} from 'react-native';
import TextTicker from 'react-native-text-ticker';

import { useNavigation } from '@react-navigation/native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Icon from 'react-native-vector-icons/Ionicons';
import { format } from 'date-fns';

import { api } from '../services/api';
import { loadBriefing, play, pause, usePlayerState } from '../services/audio';
import { BriefingCard } from '../components/BriefingCard';
import { useBriefingsStore } from '../store';
import { Briefing } from '../types';

export function HomeScreen() {
  const navigation = useNavigation();
  const queryClient = useQueryClient();

  const {
    currentBriefing,
    setCurrentBriefing,
    isGenerating,
    generatingBriefingId,
    startGeneration,
    stopGeneration,
    setGenerationProgress,
    generationProgress,
    generationStep,
  } = useBriefingsStore();

  // Ref to track the polling timeout so we can cancel it
  const pollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Ref to track if polling should continue (prevents stale closures)
  const shouldPollRef = useRef(false);

  const { isPlaying } = usePlayerState();

  // Animated progress value for smooth transitions
  const animatedProgress = useRef(new Animated.Value(0)).current;
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // Track manual pull-to-refresh separately from automatic background refetches
  const [isManualRefreshing, setIsManualRefreshing] = useState(false);

  // Track if error dialog is currently showing to prevent duplicates
  const [errorDialogShowing, setErrorDialogShowing] = useState<string | null>(null);

  // Animate progress bar smoothly when progress changes
  useEffect(() => {
    Animated.timing(animatedProgress, {
      toValue: generationProgress,
      duration: 600,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [generationProgress, animatedProgress]);

  // Pulse animation for the generating indicator
  useEffect(() => {
    if (isGenerating) {
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.05,
            duration: 1000,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 1000,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    } else {
      pulseAnim.setValue(1);
    }
  }, [isGenerating, pulseAnim]);

  const handleMiniPlayerToggle = async () => {
    if (isPlaying) {
      await pause();
    } else {
      await play();
    }
  };

  // Fetch briefings
  const {
    data: briefingsData,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['briefings'],
    queryFn: () => api.listBriefings(20),
    refetchInterval: isGenerating ? 5000 : false,
  });

  // Generate briefing mutation
  const generateMutation = useMutation({
    mutationFn: () => api.generateBriefing(),
    onSuccess: async (data) => {
      // Use startGeneration with briefing ID instead of setGenerating
      startGeneration(data.briefing_id);
      pollGenerationStatus(data.briefing_id);
    },
    onError: (error) => {
      Alert.alert('Error', `Failed to start generation: ${error.message}`);
    },
  });

  // Stop polling and clean up
  const cancelPolling = useCallback(() => {
    shouldPollRef.current = false;
    if (pollingTimeoutRef.current) {
      clearTimeout(pollingTimeoutRef.current);
      pollingTimeoutRef.current = null;
    }
  }, []);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      cancelPolling();
    };
  }, [cancelPolling]);

  // Handle user's decision on an error
  const handleErrorDecision = useCallback(
    async (briefingId: number, actionId: string, decision: 'continue' | 'cancel' | 'retry') => {
      setErrorDialogShowing(null);
      try {
        await api.resolveBriefingError(briefingId, actionId, decision);
        if (decision === 'cancel') {
          cancelPolling();
          stopGeneration();
          Alert.alert('Cancelled', 'Briefing generation was cancelled.');
        }
      } catch (error) {
        console.error('Error resolving:', error);
        Alert.alert('Error', 'Failed to send decision to server.');
      }
    },
    [stopGeneration, cancelPolling]
  );

  // Show error dialog for user confirmation
  const showErrorDialog = useCallback(
    (briefingId: number, pendingAction: { action_id: string; error: { message: string; fallback_description?: string }; options: string[] }) => {
      const { action_id, error, options } = pendingAction;

      if (errorDialogShowing === action_id) {
        return;
      }
      setErrorDialogShowing(action_id);

      const buttons: Array<{ text: string; style?: 'cancel' | 'default' | 'destructive'; onPress?: () => void }> = [];

      if (options.includes('cancel')) {
        buttons.push({
          text: 'Cancel Generation',
          style: 'destructive',
          onPress: () => handleErrorDecision(briefingId, action_id, 'cancel'),
        });
      }

      if (options.includes('retry')) {
        buttons.push({
          text: 'Retry',
          style: 'default',
          onPress: () => handleErrorDecision(briefingId, action_id, 'retry'),
        });
      }

      if (options.includes('continue')) {
        buttons.push({
          text: error.fallback_description ? 'Continue with Fallback' : 'Continue',
          style: 'default',
          onPress: () => handleErrorDecision(briefingId, action_id, 'continue'),
        });
      }

      const message = error.fallback_description
        ? `${error.message}\n\nIf you continue: ${error.fallback_description}`
        : error.message;

      Alert.alert('Generation Issue', message, buttons, { cancelable: false });
    },
    [handleErrorDecision, errorDialogShowing]
  );

  // Poll generation status with proper cancellation and ID validation
  const pollGenerationStatus = useCallback(
    (briefingId: number) => {
      // Cancel any existing polling loop before starting a new one
      cancelPolling();
      shouldPollRef.current = true;

      const checkStatus = async () => {
        // Check if we should still be polling
        if (!shouldPollRef.current) {
          console.log(`[Polling] Stopped for briefing ${briefingId} (shouldPoll=false)`);
          return;
        }

        // Validate that we're still polling for the correct briefing
        const currentGeneratingId = useBriefingsStore.getState().generatingBriefingId;
        if (currentGeneratingId !== briefingId) {
          console.log(`[Polling] Stopped for briefing ${briefingId} (current is ${currentGeneratingId})`);
          return;
        }

        try {
          const status = await api.getBriefingStatus(briefingId);

          // Double-check we're still the active generation after the async call
          if (!shouldPollRef.current || useBriefingsStore.getState().generatingBriefingId !== briefingId) {
            console.log(`[Polling] Ignoring stale response for briefing ${briefingId}`);
            return;
          }

          setGenerationProgress(status.progress_percent, status.current_step || null);

          if (status.status === 'completed' || status.status === 'completed_with_warnings') {
            cancelPolling();
            stopGeneration();
            queryClient.invalidateQueries({ queryKey: ['briefings'] });

            if (status.status === 'completed_with_warnings' && status.errors?.length > 0) {
              const warningCount = status.errors.length;
              Alert.alert(
                'Briefing Ready',
                `Your briefing is ready, but ${warningCount} issue${warningCount > 1 ? 's' : ''} occurred during generation. Some content may be missing.`
              );
            } else {
              Alert.alert('Success', 'Your briefing is ready to play!');
            }
          } else if (status.status === 'failed') {
            cancelPolling();
            stopGeneration();
            const errorMsg = status.errors?.length > 0
              ? status.errors[status.errors.length - 1].message
              : status.error || 'Generation failed';
            Alert.alert('Error', errorMsg);
          } else if (status.status === 'cancelled') {
            cancelPolling();
            stopGeneration();
          } else if (status.status === 'awaiting_confirmation' && status.pending_action) {
            showErrorDialog(briefingId, status.pending_action);
            pollingTimeoutRef.current = setTimeout(checkStatus, 2000);
          } else {
            pollingTimeoutRef.current = setTimeout(checkStatus, 3000);
          }
        } catch (error) {
          console.error('Error polling status:', error);
          // Only continue polling if we should still be polling
          if (shouldPollRef.current && useBriefingsStore.getState().generatingBriefingId === briefingId) {
            pollingTimeoutRef.current = setTimeout(checkStatus, 5000);
          }
        }
      };

      checkStatus();
    },
    [stopGeneration, cancelPolling, setGenerationProgress, queryClient, showErrorDialog]
  );

  const handlePlayBriefing = async (briefing: Briefing) => {
    try {
      setCurrentBriefing(briefing);
      await loadBriefing(briefing);
      await play();
    } catch (error) {
      Alert.alert('Error', 'Failed to play briefing');
    }
  };

  const handleGenerateBriefing = () => {
    Alert.alert(
      'Generate New Briefing',
      'Create a fresh briefing with the latest news, sports, and weather. This typically takes 2-3 minutes.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Generate', onPress: () => generateMutation.mutate() },
      ]
    );
  };

  const handleCancelGeneration = () => {
    Alert.alert(
      'Cancel Generation?',
      'The briefing is still being created. Are you sure you want to cancel?',
      [
        { text: 'Keep Going', style: 'cancel' },
        {
          text: 'Cancel',
          style: 'destructive',
          onPress: async () => {
            const briefingId = generatingBriefingId;
            // Stop polling immediately
            cancelPolling();
            stopGeneration();

            // Tell the backend to cancel (best effort, don't wait for response)
            if (briefingId) {
              try {
                await api.cancelBriefing(briefingId);
              } catch (error) {
                console.log('Failed to cancel on server (may have already finished):', error);
              }
            }
          },
        },
      ]
    );
  };

  const briefings = briefingsData?.briefings || [];
  const latestBriefing = briefings[0];

  // Get time-appropriate greeting
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  return (
    <View style={styles.container}>
      {/* Fixed Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>{getGreeting()}</Text>
          <Text style={styles.date}>
            {format(new Date(), 'EEEE, MMMM d')}
          </Text>
        </View>
        <View style={styles.headerActions}>
          {/* Generate Button - subtle in header */}
          <TouchableOpacity
            style={[
              styles.headerButton,
              (isGenerating || generateMutation.isPending) && styles.headerButtonDisabled,
            ]}
            onPress={handleGenerateBriefing}
            disabled={isGenerating || generateMutation.isPending}
          >
            <Icon
              name="add-circle-outline"
              size={26}
              color={(isGenerating || generateMutation.isPending) ? '#ccc' : '#4f46e5'}
            />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.headerButton}
            onPress={() => navigation.navigate('Settings' as never)}
          >
            <Icon name="settings-outline" size={24} color="#666" />
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={isManualRefreshing}
            onRefresh={async () => {
              setIsManualRefreshing(true);
              await queryClient.refetchQueries({ queryKey: ['briefings'] });
              setIsManualRefreshing(false);
            }}
            tintColor="#4f46e5"
            colors={['#4f46e5']}
          />
        }
      >
        {/* Generation Progress Card - only shown when generating */}
        {(isGenerating || generateMutation.isPending) && (
          <View style={styles.generationCardWrapper}>
            <Animated.View
              style={[
                styles.generationCard,
                { transform: [{ scale: pulseAnim }] }
              ]}
            >
              <View style={styles.generationHeader}>
                <View style={styles.generationTitleRow}>
                  <Icon name="sparkles" size={20} color="#4f46e5" />
                  <Text style={styles.generationTitle}>Creating Your Briefing</Text>
                </View>
                <TouchableOpacity onPress={handleCancelGeneration}>
                  <Icon name="close-circle" size={24} color="#999" />
                </TouchableOpacity>
              </View>

              <Text style={styles.generationStep} numberOfLines={1}>
                {generationStep || 'Starting...'}
              </Text>

              {/* Smooth animated progress bar */}
              <View style={styles.progressBarContainer}>
                <Animated.View
                  style={[
                    styles.progressBarFill,
                    {
                      width: animatedProgress.interpolate({
                        inputRange: [0, 100],
                        outputRange: ['0%', '100%'],
                      }),
                    },
                  ]}
                />
              </View>

              <View style={styles.generationFooter}>
                <ActivityIndicator size="small" color="#4f46e5" />
                <Text style={styles.generationPercent}>
                  {Math.round(generationProgress)}% complete
                </Text>
              </View>
            </Animated.View>
          </View>
        )}

        {/* Latest Briefing */}
        {latestBriefing && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Latest Briefing</Text>
            <BriefingCard
              briefing={latestBriefing}
              onPress={() => handlePlayBriefing(latestBriefing)}
              isPlaying={currentBriefing?.id === latestBriefing.id}
            />
          </View>
        )}

        {/* Previous Briefings */}
        {briefings.length > 1 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Previous Briefings</Text>
            {briefings.slice(1, 5).map((briefing) => (
              <BriefingCard
                key={briefing.id}
                briefing={briefing}
                onPress={() => handlePlayBriefing(briefing)}
                isPlaying={currentBriefing?.id === briefing.id}
              />
            ))}
          </View>
        )}

        {/* Empty State */}
        {!isLoading && briefings.length === 0 && !isGenerating && (
          <View style={styles.emptyState}>
            <View style={styles.emptyIconContainer}>
              <Icon name="radio-outline" size={48} color="#4f46e5" />
            </View>
            <Text style={styles.emptyTitle}>No briefings yet</Text>
            <Text style={styles.emptyText}>
              Your personalized briefings will appear here.{'\n'}
              They're automatically generated each morning,{'\n'}
              or you can create one now.
            </Text>
            <TouchableOpacity
              style={styles.emptyButton}
              onPress={handleGenerateBriefing}
              disabled={generateMutation.isPending}
            >
              <Icon name="sparkles" size={20} color="#fff" />
              <Text style={styles.emptyButtonText}>Create Your First Briefing</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Loading State */}
        {isLoading && (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#4f46e5" />
          </View>
        )}
      </ScrollView>

      {/* Mini Player */}
      {currentBriefing && (
        <View style={styles.miniPlayer}>
          <TouchableOpacity
            style={styles.miniPlayerContent}
            onPress={() =>
              navigation.navigate('Player' as never, {
                briefingId: currentBriefing.id,
              } as never)
            }
          >
            <Icon name="radio" size={24} color="#4f46e5" />
            <View style={styles.miniPlayerText}>
              <TextTicker
                style={styles.miniPlayerTitle}
                duration={10000}
                loop
                bounce={false}
                repeatSpacer={50}
                marqueeDelay={1000}
                scrollSpeed={50}
              >
                {currentBriefing.title}
              </TextTicker>
              <Text style={styles.miniPlayerSubtitle}>
                {isPlaying ? 'Now Playing' : 'Paused'}
              </Text>
            </View>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.miniPlayerControl}
            onPress={handleMiniPlayerToggle}
          >
            <Icon
              name={isPlaying ? 'pause-circle' : 'play-circle'}
              size={44}
              color="#4f46e5"
            />
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f7',
  },
  scrollContent: {
    paddingBottom: 100,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 60,
    paddingBottom: 16,
    backgroundColor: '#f5f5f7',
  },
  greeting: {
    fontSize: 28,
    fontWeight: '700',
    color: '#1a1a2e',
  },
  date: {
    fontSize: 16,
    color: '#666',
    marginTop: 4,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerButton: {
    padding: 8,
  },
  headerButtonDisabled: {
    opacity: 0.5,
  },
  // Generation Progress Card wrapper - provides space for scale animation
  generationCardWrapper: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 20,
  },
  generationCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 16,
    shadowColor: '#4f46e5',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 6,
    borderWidth: 1,
    borderColor: '#e8e6f9',
  },
  generationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  generationTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  generationTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1a1a2e',
  },
  generationStep: {
    fontSize: 14,
    color: '#666',
    marginBottom: 12,
  },
  progressBarContainer: {
    height: 6,
    backgroundColor: '#e8e6f9',
    borderRadius: 3,
    overflow: 'hidden',
    marginBottom: 12,
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: '#4f46e5',
    borderRadius: 3,
  },
  generationFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  generationPercent: {
    fontSize: 13,
    color: '#666',
    fontWeight: '500',
  },
  section: {
    marginTop: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1a1a2e',
    marginHorizontal: 20,
    marginBottom: 12,
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 60,
    paddingHorizontal: 40,
  },
  emptyIconContainer: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#f0eeff',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 20,
  },
  emptyTitle: {
    fontSize: 22,
    fontWeight: '600',
    color: '#1a1a2e',
    marginBottom: 12,
  },
  emptyText: {
    fontSize: 15,
    color: '#666',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 24,
  },
  emptyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#4f46e5',
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
    gap: 10,
  },
  emptyButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  loadingContainer: {
    paddingVertical: 60,
  },
  miniPlayer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#fff',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    paddingBottom: 34,
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 5,
  },
  miniPlayerContent: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 12,
  },
  miniPlayerText: {
    flex: 1,
  },
  miniPlayerTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1a1a2e',
  },
  miniPlayerSubtitle: {
    fontSize: 12,
    color: '#666',
  },
  miniPlayerControl: {
    padding: 8,
  },
});
