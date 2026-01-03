/**
 * Home screen - main dashboard for Morning Drive
 */

import React, { useEffect, useCallback, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  Alert,
} from 'react-native';
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
    setGenerating,
    setGenerationProgress,
    generationProgress,
    generationStep,
  } = useBriefingsStore();

  const { isPlaying } = usePlayerState();

  // Track manual pull-to-refresh separately from automatic background refetches
  const [isManualRefreshing, setIsManualRefreshing] = useState(false);

  // Track if error dialog is currently showing to prevent duplicates
  const [errorDialogShowing, setErrorDialogShowing] = useState<string | null>(null);

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
    isRefetching,
  } = useQuery({
    queryKey: ['briefings'],
    queryFn: () => api.listBriefings(20),
    refetchInterval: isGenerating ? 5000 : false,
  });

  // Generate briefing mutation
  const generateMutation = useMutation({
    mutationFn: () => api.generateBriefing(),
    onSuccess: async (data) => {
      setGenerating(true);
      pollGenerationStatus(data.briefing_id);
    },
    onError: (error) => {
      Alert.alert('Error', `Failed to start generation: ${error.message}`);
    },
  });

  // Handle user's decision on an error
  const handleErrorDecision = useCallback(
    async (briefingId: number, actionId: string, decision: 'continue' | 'cancel' | 'retry') => {
      setErrorDialogShowing(null);  // Clear dialog state
      try {
        await api.resolveBriefingError(briefingId, actionId, decision);
        if (decision === 'cancel') {
          setGenerating(false);
          Alert.alert('Cancelled', 'Briefing generation was cancelled.');
        }
        // For continue/retry, polling will resume and pick up new status
      } catch (error) {
        console.error('Error resolving:', error);
        Alert.alert('Error', 'Failed to send decision to server.');
      }
    },
    [setGenerating]
  );

  // Show error dialog for user confirmation
  const showErrorDialog = useCallback(
    (briefingId: number, pendingAction: { action_id: string; error: { message: string; fallback_description?: string }; options: string[] }) => {
      const { action_id, error, options } = pendingAction;

      // Prevent showing the same dialog multiple times
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

  // Poll generation status
  const pollGenerationStatus = useCallback(
    async (briefingId: number) => {
      const checkStatus = async () => {
        try {
          const status = await api.getBriefingStatus(briefingId);
          setGenerationProgress(status.progress_percent, status.current_step || null);

          if (status.status === 'completed' || status.status === 'completed_with_warnings') {
            setGenerating(false);
            queryClient.invalidateQueries({ queryKey: ['briefings'] });

            if (status.status === 'completed_with_warnings' && status.errors?.length > 0) {
              const warningCount = status.errors.length;
              Alert.alert(
                'Briefing Ready',
                `Your briefing is ready, but ${warningCount} issue${warningCount > 1 ? 's' : ''} occurred during generation. Some content may be missing.`
              );
            } else {
              Alert.alert('Success', 'Your morning briefing is ready!');
            }
          } else if (status.status === 'failed') {
            setGenerating(false);
            const errorMsg = status.errors?.length > 0
              ? status.errors[status.errors.length - 1].message
              : status.error || 'Generation failed';
            Alert.alert('Error', errorMsg);
          } else if (status.status === 'cancelled') {
            setGenerating(false);
            // User already got cancellation confirmation
          } else if (status.status === 'awaiting_confirmation' && status.pending_action) {
            // Show dialog and wait for user decision
            showErrorDialog(briefingId, status.pending_action);
            // Continue polling to detect when user has responded
            setTimeout(checkStatus, 2000);
          } else {
            // Continue polling
            setTimeout(checkStatus, 3000);
          }
        } catch (error) {
          console.error('Error polling status:', error);
          setTimeout(checkStatus, 5000);
        }
      };

      checkStatus();
    },
    [setGenerating, setGenerationProgress, queryClient, showErrorDialog]
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
      'This will create a new morning briefing with the latest news, sports, and weather.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Generate', onPress: () => generateMutation.mutate() },
      ]
    );
  };

  const briefings = briefingsData?.briefings || [];
  const latestBriefing = briefings[0];

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={isManualRefreshing}
            onRefresh={async () => {
              setIsManualRefreshing(true);
              await refetch();
              setIsManualRefreshing(false);
            }}
            tintColor="#4f46e5"
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>Good morning</Text>
            <Text style={styles.date}>
              {format(new Date(), 'EEEE, MMMM d')}
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => navigation.navigate('Settings' as never)}
          >
            <Icon name="settings-outline" size={24} color="#666" />
          </TouchableOpacity>
        </View>

        {/* Generate Button */}
        <View style={styles.generateButtonContainer}>
          <TouchableOpacity
            style={[
              styles.generateButton,
              (isGenerating || generateMutation.isPending) &&
                styles.generateButtonDisabled,
            ]}
            onPress={handleGenerateBriefing}
            disabled={isGenerating || generateMutation.isPending}
          >
            {isGenerating || generateMutation.isPending ? (
              <View style={styles.generatingContent}>
                <ActivityIndicator color="#fff" size="small" style={styles.generatingSpinner} />
                <Text style={styles.generatingStepText} numberOfLines={1}>
                  {generationStep || 'Generating...'}
                </Text>
                <Text style={styles.progressText}>{generationProgress}%</Text>
              </View>
            ) : (
              <View style={styles.generateContent}>
                <Icon name="sparkles" size={24} color="#fff" />
                <Text style={styles.generateButtonText}>
                  Generate Today's Briefing
                </Text>
              </View>
            )}
          </TouchableOpacity>

          {/* Progress Bar - always rendered to prevent layout shift */}
          <View style={styles.progressBar}>
            <View
              style={[
                styles.progressFill,
                { width: isGenerating ? `${generationProgress}%` : '0%' },
              ]}
            />
          </View>
        </View>

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
        {!isLoading && briefings.length === 0 && (
          <View style={styles.emptyState}>
            <Icon name="radio-outline" size={64} color="#ccc" />
            <Text style={styles.emptyTitle}>No briefings yet</Text>
            <Text style={styles.emptyText}>
              Generate your first morning briefing to get started!
            </Text>
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
              <Text style={styles.miniPlayerTitle} numberOfLines={1}>
                {currentBriefing.title}
              </Text>
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
    paddingBottom: 20,
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
  generateButtonContainer: {
    marginHorizontal: 16,
    marginVertical: 16,
  },
  generateButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 16,
    padding: 20,
    minHeight: 68, // Fixed height to prevent layout shift
  },
  generateButtonDisabled: {
    backgroundColor: '#8b85f2',
  },
  generateContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    height: 28, // Fixed height to prevent layout shift
    gap: 12,
  },
  generatingContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 28, // Fixed height to match generateContent
  },
  generatingSpinner: {
    width: 24,
    height: 24, // Explicit size to prevent layout shift
    marginRight: 10,
  },
  generatingStepText: {
    flex: 1,
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    lineHeight: 20, // Fixed line height
  },
  generateButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  progressText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 10,
    minWidth: 40,
    textAlign: 'right',
  },
  progressBar: {
    height: 4,
    backgroundColor: '#e0e0e0',
    marginTop: 8,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#4f46e5',
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
  emptyTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#333',
    marginTop: 16,
  },
  emptyText: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    marginTop: 8,
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
