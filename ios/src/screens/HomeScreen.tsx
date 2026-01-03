/**
 * Home screen - main dashboard for Morning Drive
 */

import React, { useEffect, useCallback } from 'react';
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
import { loadBriefing, play } from '../services/audio';
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

  // Poll generation status
  const pollGenerationStatus = useCallback(
    async (briefingId: number) => {
      const checkStatus = async () => {
        try {
          const status = await api.getBriefingStatus(briefingId);
          setGenerationProgress(status.progress_percent, status.current_step || null);

          if (status.status === 'completed') {
            setGenerating(false);
            queryClient.invalidateQueries({ queryKey: ['briefings'] });
            Alert.alert('Success', 'Your morning briefing is ready!');
          } else if (status.status === 'failed') {
            setGenerating(false);
            Alert.alert('Error', status.error || 'Generation failed');
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
    [setGenerating, setGenerationProgress, queryClient]
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
            refreshing={isRefetching}
            onRefresh={refetch}
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
              <ActivityIndicator color="#fff" size="small" />
              <Text style={styles.generateButtonText}>
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

        {/* Progress Bar */}
        {isGenerating && (
          <View style={styles.progressBar}>
            <View
              style={[styles.progressFill, { width: `${generationProgress}%` }]}
            />
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
        <TouchableOpacity
          style={styles.miniPlayer}
          onPress={() =>
            navigation.navigate('Player' as never, {
              briefingId: currentBriefing.id,
            } as never)
          }
        >
          <View style={styles.miniPlayerContent}>
            <Icon name="radio" size={24} color="#4f46e5" />
            <View style={styles.miniPlayerText}>
              <Text style={styles.miniPlayerTitle} numberOfLines={1}>
                {currentBriefing.title}
              </Text>
              <Text style={styles.miniPlayerSubtitle}>Playing...</Text>
            </View>
          </View>
          <TouchableOpacity style={styles.miniPlayerControl}>
            <Icon name="pause" size={24} color="#4f46e5" />
          </TouchableOpacity>
        </TouchableOpacity>
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
  generateButton: {
    backgroundColor: '#4f46e5',
    marginHorizontal: 16,
    marginVertical: 16,
    borderRadius: 16,
    padding: 20,
  },
  generateButtonDisabled: {
    backgroundColor: '#8b85f2',
  },
  generateContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  generatingContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  generateButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  progressText: {
    color: '#fff',
    fontSize: 14,
    opacity: 0.8,
  },
  progressBar: {
    height: 4,
    backgroundColor: '#e0e0e0',
    marginHorizontal: 16,
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
