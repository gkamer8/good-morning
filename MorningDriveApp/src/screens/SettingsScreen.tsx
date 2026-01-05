/**
 * Settings screen for configuring preferences
 */

import React, { useEffect, useState, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  Switch,
  TextInput,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Icon from 'react-native-vector-icons/Ionicons';
import { Event } from 'react-native-track-player';
import TrackPlayer from 'react-native-track-player';

import { api } from '../services/api';
import { playVoicePreview, stopVoicePreview } from '../services/audio';
import { useSettingsStore, useAppConfigStore } from '../store';
import {
  NEWS_TOPICS,
  NEWS_SOURCES,
  SPORTS_LEAGUES,
  FUN_SEGMENTS,
  DAYS_OF_WEEK,
  VOICE_OPTIONS,
  VOICE_STYLES,
  WRITING_STYLES,
  SEGMENT_TYPES,
  DEFAULT_SEGMENT_ORDER,
  SportsTeam,
  WeatherLocation,
  VoiceInfo,
} from '../types';

export function SettingsScreen() {
  const navigation = useNavigation();
  const queryClient = useQueryClient();

  const { settings, setSettings, schedule, setSchedule } = useSettingsStore();
  const { serverUrl, setServerUrl, isConnected, setConnected } =
    useAppConfigStore();

  const [localServerUrl, setLocalServerUrl] = useState(serverUrl);
  const [newExclusion, setNewExclusion] = useState('');
  const [newPriorityTopic, setNewPriorityTopic] = useState('');
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamLeague, setNewTeamLeague] = useState('');
  const [newLocationName, setNewLocationName] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);

  // Listen for playback end to update preview state
  useEffect(() => {
    const subscription = TrackPlayer.addEventListener(
      Event.PlaybackQueueEnded,
      () => {
        setPreviewingVoice(null);
      }
    );

    return () => {
      subscription.remove();
      // Stop any preview when leaving settings
      stopVoicePreview();
    };
  }, []);

  const handlePlayPreview = async (voiceId: string) => {
    // If clicking same voice that's playing, just stop
    if (previewingVoice === voiceId) {
      await stopVoicePreview();
      setPreviewingVoice(null);
      return;
    }

    setPreviewLoading(voiceId);

    // Use api service for consistent URL handling
    const previewUrl = api.getVoicePreviewUrl(voiceId);
    console.log('handlePlayPreview: voiceId=', voiceId, 'url=', previewUrl);

    try {
      // First verify the URL is reachable using Range request (only downloads 1 byte)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      try {
        const testResponse = await fetch(previewUrl, {
          method: 'GET',
          headers: { Range: 'bytes=0-0' },
          signal: controller.signal,
        });
        clearTimeout(timeoutId);

        // 206 Partial Content or 200 OK are both acceptable
        if (!testResponse.ok && testResponse.status !== 206) {
          const errorText = await testResponse.text();
          throw new Error(`Server returned ${testResponse.status}: ${errorText}`);
        }
      } catch (fetchError: any) {
        clearTimeout(timeoutId);
        if (fetchError.name === 'AbortError') {
          throw new Error('Connection timed out. Check server is running.');
        }
        throw new Error(`Network error: ${fetchError.message}`);
      }

      // URL is reachable, now play with TrackPlayer
      await playVoicePreview(previewUrl);
      setPreviewingVoice(voiceId);
    } catch (error: any) {
      console.log('Failed to play preview:', error);
      Alert.alert(
        'Preview Error',
        `Failed to play preview.\n\nURL: ${previewUrl}\n\nError: ${error?.message || 'Unknown error'}`
      );
    } finally {
      setPreviewLoading(null);
    }
  };

  const handleStopPreview = async () => {
    await stopVoicePreview();
    setPreviewingVoice(null);
  };

  // Fetch settings
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.getSettings(),
  });

  // Fetch schedule
  const scheduleQuery = useQuery({
    queryKey: ['schedule'],
    queryFn: () => api.getSchedule(),
  });

  // Fetch available voices (includes custom voices from ElevenLabs)
  const voicesQuery = useQuery({
    queryKey: ['voices'],
    queryFn: () => api.listVoices(),
    staleTime: 1000 * 60 * 10, // Cache for 10 minutes
  });

  // Merge hardcoded voices with API voices to get custom voices like "Firing Line"
  const allVoices = React.useMemo(() => {
    const hardcodedVoices = VOICE_OPTIONS.map(v => ({
      id: v.id,
      label: v.label,
      description: v.description,
      isCustom: false,
    }));

    // Get API voices and find any that aren't in our hardcoded list
    const apiVoices = voicesQuery.data?.voices || [];
    const customVoices = apiVoices
      .filter(v => !VOICE_OPTIONS.some(opt => opt.id === v.voice_id))
      .map(v => ({
        id: v.voice_id,
        label: v.name,
        description: v.labels?.accent
          ? `${v.labels.gender || 'Voice'}, ${v.labels.accent}`
          : v.description || 'Custom voice',
        isCustom: true,
      }));

    return [...customVoices, ...hardcodedVoices];
  }, [voicesQuery.data]);

  // Update settings mutation
  const updateSettingsMutation = useMutation({
    mutationFn: (newSettings: Partial<typeof settings>) =>
      api.updateSettings(newSettings as any),
    onSuccess: (data) => {
      setSettings(data);
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  // Update schedule mutation
  const updateScheduleMutation = useMutation({
    mutationFn: (newSchedule: Partial<typeof schedule>) =>
      api.updateSchedule(newSchedule as any),
    onSuccess: (data) => {
      setSchedule(data);
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
  });

  useEffect(() => {
    if (settingsQuery.data) {
      setSettings(settingsQuery.data);
    }
  }, [settingsQuery.data]);

  useEffect(() => {
    if (scheduleQuery.data) {
      setSchedule(scheduleQuery.data);
    }
  }, [scheduleQuery.data]);

  const handleToggleNewsTopic = (topic: string) => {
    if (!settings) return;
    const newTopics = settings.news_topics.includes(topic)
      ? settings.news_topics.filter((t) => t !== topic)
      : [...settings.news_topics, topic];
    updateSettingsMutation.mutate({ news_topics: newTopics });
  };

  const handleToggleNewsSource = (source: string) => {
    if (!settings) return;
    const newSources = settings.news_sources.includes(source)
      ? settings.news_sources.filter((s) => s !== source)
      : [...settings.news_sources, source];
    updateSettingsMutation.mutate({ news_sources: newSources });
  };

  const handleToggleLeague = (league: string) => {
    if (!settings) return;
    const newLeagues = settings.sports_leagues.includes(league)
      ? settings.sports_leagues.filter((l) => l !== league)
      : [...settings.sports_leagues, league];
    updateSettingsMutation.mutate({ sports_leagues: newLeagues });
  };

  const handleToggleFunSegment = (segment: string) => {
    if (!settings) return;
    const newSegments = settings.fun_segments.includes(segment)
      ? settings.fun_segments.filter((s) => s !== segment)
      : [...settings.fun_segments, segment];
    updateSettingsMutation.mutate({ fun_segments: newSegments });
  };

  const handleAddExclusion = () => {
    if (!settings || !newExclusion.trim()) return;
    const exclusions = settings.news_exclusions || [];
    if (!exclusions.includes(newExclusion.trim())) {
      updateSettingsMutation.mutate({
        news_exclusions: [...exclusions, newExclusion.trim()],
      });
    }
    setNewExclusion('');
  };

  const handleRemoveExclusion = (exclusion: string) => {
    if (!settings) return;
    const exclusions = settings.news_exclusions || [];
    updateSettingsMutation.mutate({
      news_exclusions: exclusions.filter((e) => e !== exclusion),
    });
  };

  const handleAddPriorityTopic = () => {
    if (!settings || !newPriorityTopic.trim()) return;
    const topics = settings.priority_topics || [];
    if (!topics.includes(newPriorityTopic.trim())) {
      updateSettingsMutation.mutate({
        priority_topics: [...topics, newPriorityTopic.trim()],
      });
    }
    setNewPriorityTopic('');
  };

  const handleRemovePriorityTopic = (topic: string) => {
    if (!settings) return;
    const topics = settings.priority_topics || [];
    updateSettingsMutation.mutate({
      priority_topics: topics.filter((t) => t !== topic),
    });
  };

  const handleToggleScheduleDay = (day: number) => {
    if (!schedule) return;
    const newDays = schedule.days_of_week.includes(day)
      ? schedule.days_of_week.filter((d) => d !== day)
      : [...schedule.days_of_week, day].sort();
    updateScheduleMutation.mutate({ days_of_week: newDays });
  };

  const handleMoveSegment = (segmentId: string, direction: 'up' | 'down') => {
    if (!settings) return;
    const currentOrder = settings.segment_order || DEFAULT_SEGMENT_ORDER;
    const index = currentOrder.indexOf(segmentId);
    if (index === -1) return;

    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= currentOrder.length) return;

    const newOrder = [...currentOrder];
    [newOrder[index], newOrder[newIndex]] = [newOrder[newIndex], newOrder[index]];
    updateSettingsMutation.mutate({ segment_order: newOrder });
  };

  const handleAddTeam = () => {
    if (!settings || !newTeamName.trim()) return;
    const teams = settings.sports_teams || [];
    const newTeam: SportsTeam = {
      name: newTeamName.trim(),
      league: newTeamLeague.trim() || 'other',
    };
    if (!teams.some(t => t.name.toLowerCase() === newTeam.name.toLowerCase())) {
      updateSettingsMutation.mutate({
        sports_teams: [...teams, newTeam],
      });
    }
    setNewTeamName('');
    setNewTeamLeague('');
  };

  const handleRemoveTeam = (teamName: string) => {
    if (!settings) return;
    const teams = settings.sports_teams || [];
    updateSettingsMutation.mutate({
      sports_teams: teams.filter((t) => t.name !== teamName),
    });
  };

  const handleAddLocation = async () => {
    if (!settings || !newLocationName.trim()) return;
    const locations = settings.weather_locations || [];

    // Simple geocoding using Open-Meteo's geocoding API
    try {
      const response = await fetch(
        `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(newLocationName.trim())}&count=1`
      );
      const data = await response.json();

      if (data.results && data.results.length > 0) {
        const result = data.results[0];
        const newLocation: WeatherLocation = {
          name: result.name + (result.admin1 ? `, ${result.admin1}` : ''),
          lat: result.latitude,
          lon: result.longitude,
        };

        if (!locations.some(loc => loc.name === newLocation.name)) {
          updateSettingsMutation.mutate({
            weather_locations: [...locations, newLocation],
          });
        }
      } else {
        Alert.alert('Location Not Found', 'Could not find that location. Try a different name.');
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to look up location');
    }

    setNewLocationName('');
  };

  const handleRemoveLocation = (locationName: string) => {
    if (!settings) return;
    const locations = settings.weather_locations || [];
    updateSettingsMutation.mutate({
      weather_locations: locations.filter((loc) => loc.name !== locationName),
    });
  };

  const handleSaveServerUrl = async () => {
    // Validate URL format
    const urlToTest = localServerUrl.trim();
    if (!urlToTest) {
      Alert.alert('Error', 'Please enter a server URL');
      return;
    }

    // Ensure URL has protocol
    let finalUrl = urlToTest;
    if (!urlToTest.startsWith('http://') && !urlToTest.startsWith('https://')) {
      finalUrl = `http://${urlToTest}`;
      setLocalServerUrl(finalUrl);
    }

    setIsConnecting(true);

    try {
      await api.setBaseUrl(finalUrl);
      setServerUrl(finalUrl);

      console.log('Testing connection to:', finalUrl);
      const result = await api.healthCheck();
      console.log('Health check result:', result);

      setConnected(result.ok);

      if (result.ok) {
        Alert.alert('Connected', `Successfully connected to ${finalUrl}`);
        queryClient.invalidateQueries();
      } else {
        Alert.alert(
          'Connection Failed',
          `Could not connect to server.\n\nURL: ${finalUrl}\n\nError: ${result.error || 'Unknown error'}\n\nMake sure:\n• The backend is running\n• Your phone is on the same WiFi network\n• The IP address is correct`
        );
      }
    } catch (error: any) {
      console.log('Save URL error:', error);
      Alert.alert('Error', `Failed to save URL: ${error.message || 'Unknown error'}`);
    } finally {
      setIsConnecting(false);
    }
  };

  // Show loading state for content below server connection, but always show server connection
  const isContentLoading = settingsQuery.isLoading || scheduleQuery.isLoading;
  const hasConnectionError = settingsQuery.isError || scheduleQuery.isError;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={0}
    >
    <ScrollView
      style={styles.scrollView}
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ paddingBottom: 100 }}
    >
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="arrow-back" size={24} color="#1a1a2e" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Settings</Text>
        <View style={{ width: 24 }} />
      </View>

      {/* Show error message if connection failed */}
      {hasConnectionError && (
        <View style={styles.section}>
          <View style={[styles.card, { backgroundColor: '#fef2f2', padding: 16 }]}>
            <Text style={{ color: '#dc2626', fontWeight: '600', marginBottom: 8 }}>
              Connection Error
            </Text>
            <Text style={{ color: '#7f1d1d', fontSize: 14 }}>
              Could not connect to the server. Check Advanced Settings at the bottom to configure the server URL.
            </Text>
          </View>
        </View>
      )}

      {/* Show loading indicator for remaining content */}
      {isContentLoading && !hasConnectionError && (
        <View style={styles.section}>
          <View style={[styles.card, { padding: 24, alignItems: 'center' }]}>
            <ActivityIndicator size="large" color="#4f46e5" />
            <Text style={{ marginTop: 12, color: '#666' }}>Loading settings...</Text>
          </View>
        </View>
      )}

      {/* Only show rest of settings when loaded successfully */}
      {!isContentLoading && !hasConnectionError && (
        <>
          {/* Briefing Duration */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Briefing Duration</Text>
        <View style={styles.card}>
          <View style={styles.durationOptions}>
            {[5, 10, 15, 20].map((mins) => (
              <TouchableOpacity
                key={mins}
                style={[
                  styles.durationOption,
                  settings?.duration_minutes === mins &&
                    styles.durationOptionSelected,
                ]}
                onPress={() =>
                  updateSettingsMutation.mutate({ duration_minutes: mins })
                }
              >
                <Text
                  style={[
                    styles.durationText,
                    settings?.duration_minutes === mins &&
                      styles.durationTextSelected,
                  ]}
                >
                  {mins} min
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>

      {/* Segment Order */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Segment Order</Text>
        <View style={styles.card}>
          <Text style={styles.exclusionHint}>
            Drag segments to reorder how they appear in your briefing
          </Text>
          {(settings?.segment_order || DEFAULT_SEGMENT_ORDER).map((segmentId, index) => {
            const segment = SEGMENT_TYPES.find(s => s.id === segmentId);
            if (!segment) return null;
            const isFirst = index === 0;
            const isLast = index === (settings?.segment_order || DEFAULT_SEGMENT_ORDER).length - 1;
            return (
              <View key={segmentId} style={styles.segmentOrderRow}>
                <View style={styles.segmentOrderInfo}>
                  <Icon name={segment.icon as any} size={22} color="#4f46e5" />
                  <Text style={styles.segmentOrderLabel}>{segment.label}</Text>
                </View>
                <View style={styles.segmentOrderButtons}>
                  <TouchableOpacity
                    style={[styles.segmentOrderButton, isFirst && styles.segmentOrderButtonDisabled]}
                    onPress={() => handleMoveSegment(segmentId, 'up')}
                    disabled={isFirst}
                  >
                    <Icon name="chevron-up" size={20} color={isFirst ? '#ccc' : '#4f46e5'} />
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.segmentOrderButton, isLast && styles.segmentOrderButtonDisabled]}
                    onPress={() => handleMoveSegment(segmentId, 'down')}
                    disabled={isLast}
                  >
                    <Icon name="chevron-down" size={20} color={isLast ? '#ccc' : '#4f46e5'} />
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
        </View>
      </View>

      {/* News Topics */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>News Topics</Text>
        <View style={styles.card}>
          {NEWS_TOPICS.map((topic) => (
            <TouchableOpacity
              key={topic.id}
              style={styles.toggleRow}
              onPress={() => handleToggleNewsTopic(topic.id)}
            >
              <Text style={styles.toggleLabel}>{topic.label}</Text>
              <Switch
                value={settings?.news_topics.includes(topic.id)}
                onValueChange={() => handleToggleNewsTopic(topic.id)}
                trackColor={{ false: '#e0e0e0', true: '#4f46e5' }}
              />
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* News Sources */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>News Sources</Text>
        <View style={styles.card}>
          {NEWS_SOURCES.map((source) => (
            <TouchableOpacity
              key={source.id}
              style={styles.toggleRow}
              onPress={() => handleToggleNewsSource(source.id)}
            >
              <Text style={styles.toggleLabel}>{source.label}</Text>
              <Switch
                value={settings?.news_sources.includes(source.id)}
                onValueChange={() => handleToggleNewsSource(source.id)}
                trackColor={{ false: '#e0e0e0', true: '#4f46e5' }}
              />
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Priority Topics */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Priority Topics</Text>
        <View style={styles.card}>
          <Text style={styles.exclusionHint}>
            Add topics you want emphasized (e.g., "tech startups", "AI news", "climate policy")
          </Text>
          <View style={styles.exclusionInputRow}>
            <TextInput
              style={styles.exclusionInput}
              value={newPriorityTopic}
              onChangeText={setNewPriorityTopic}
              placeholder="Enter topic to prioritize..."
              onSubmitEditing={handleAddPriorityTopic}
              returnKeyType="done"
            />
            <TouchableOpacity
              style={[styles.addExclusionButton, { backgroundColor: '#22c55e' }]}
              onPress={handleAddPriorityTopic}
            >
              <Icon name="add" size={24} color="#fff" />
            </TouchableOpacity>
          </View>
          <View style={styles.exclusionTags}>
            {(settings?.priority_topics || []).length === 0 && (
              <Text style={styles.emptyTagsText}>No priority topics added yet</Text>
            )}
            {(settings?.priority_topics || []).map((topic, index) => (
              <View key={index} style={[styles.exclusionTag, styles.priorityTag]}>
                <Icon name="star" size={14} color="#22c55e" />
                <Text style={styles.exclusionTagText} numberOfLines={1}>{topic}</Text>
                <TouchableOpacity
                  onPress={() => handleRemovePriorityTopic(topic)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <Icon name="close-circle" size={18} color="#666" />
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* News Exclusions */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Skip These Topics</Text>
        <View style={styles.card}>
          <Text style={styles.exclusionHint}>
            Add topics you don't want to hear about (e.g., "earthquakes outside US", "celebrity gossip")
          </Text>
          <View style={styles.exclusionInputRow}>
            <TextInput
              style={styles.exclusionInput}
              value={newExclusion}
              onChangeText={setNewExclusion}
              placeholder="Enter topic to exclude..."
              onSubmitEditing={handleAddExclusion}
              returnKeyType="done"
            />
            <TouchableOpacity
              style={[styles.addExclusionButton, { backgroundColor: '#ef4444' }]}
              onPress={handleAddExclusion}
            >
              <Icon name="add" size={24} color="#fff" />
            </TouchableOpacity>
          </View>
          <View style={styles.exclusionTags}>
            {(settings?.news_exclusions || []).length === 0 && (
              <Text style={styles.emptyTagsText}>No exclusions added yet</Text>
            )}
            {(settings?.news_exclusions || []).map((exclusion, index) => (
              <View key={index} style={[styles.exclusionTag, styles.excludeTag]}>
                <Icon name="remove-circle" size={14} color="#ef4444" />
                <Text style={styles.exclusionTagText} numberOfLines={1}>{exclusion}</Text>
                <TouchableOpacity
                  onPress={() => handleRemoveExclusion(exclusion)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <Icon name="close-circle" size={18} color="#666" />
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* Sports Leagues */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Sports Leagues</Text>
        <View style={styles.card}>
          {SPORTS_LEAGUES.map((league) => (
            <TouchableOpacity
              key={league.id}
              style={styles.toggleRow}
              onPress={() => handleToggleLeague(league.id)}
            >
              <Text style={styles.toggleLabel}>{league.label}</Text>
              <Switch
                value={settings?.sports_leagues.includes(league.id)}
                onValueChange={() => handleToggleLeague(league.id)}
                trackColor={{ false: '#e0e0e0', true: '#4f46e5' }}
              />
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Favorite Teams & Players */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Favorite Teams & Players</Text>
        <View style={styles.card}>
          <Text style={styles.exclusionHint}>
            Add specific teams or players to follow (e.g., "Yankees", "Lakers", "Roger Federer")
          </Text>
          <View style={styles.exclusionInputRow}>
            <TextInput
              style={[styles.exclusionInput, { flex: 2 }]}
              value={newTeamName}
              onChangeText={setNewTeamName}
              placeholder="Team or player name..."
              onSubmitEditing={handleAddTeam}
              returnKeyType="done"
            />
            <TextInput
              style={[styles.exclusionInput, { flex: 1, marginLeft: 8 }]}
              value={newTeamLeague}
              onChangeText={setNewTeamLeague}
              placeholder="League"
              onSubmitEditing={handleAddTeam}
              returnKeyType="done"
            />
            <TouchableOpacity
              style={[styles.addExclusionButton, { backgroundColor: '#4f46e5' }]}
              onPress={handleAddTeam}
            >
              <Icon name="add" size={24} color="#fff" />
            </TouchableOpacity>
          </View>
          <View style={styles.exclusionTags}>
            {(settings?.sports_teams || []).length === 0 && (
              <Text style={styles.emptyTagsText}>No favorite teams or players added yet</Text>
            )}
            {(settings?.sports_teams || []).map((team, index) => (
              <View key={index} style={[styles.exclusionTag, styles.teamTag]}>
                <Icon name="star" size={14} color="#4f46e5" />
                <Text style={styles.exclusionTagText} numberOfLines={1}>
                  {team.name}{team.league && team.league !== 'other' ? ` (${team.league})` : ''}
                </Text>
                <TouchableOpacity
                  onPress={() => handleRemoveTeam(team.name)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <Icon name="close-circle" size={18} color="#666" />
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* Weather Locations */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Weather Locations</Text>
        <View style={styles.card}>
          <Text style={styles.exclusionHint}>
            Add cities for weather forecasts (e.g., "San Francisco", "London", "Tokyo")
          </Text>
          <View style={styles.exclusionInputRow}>
            <TextInput
              style={styles.exclusionInput}
              value={newLocationName}
              onChangeText={setNewLocationName}
              placeholder="Enter city name..."
              onSubmitEditing={handleAddLocation}
              returnKeyType="done"
            />
            <TouchableOpacity
              style={[styles.addExclusionButton, { backgroundColor: '#0ea5e9' }]}
              onPress={handleAddLocation}
            >
              <Icon name="add" size={24} color="#fff" />
            </TouchableOpacity>
          </View>
          <View style={styles.exclusionTags}>
            {(settings?.weather_locations || []).length === 0 && (
              <Text style={styles.emptyTagsText}>No weather locations added yet</Text>
            )}
            {(settings?.weather_locations || []).map((location, index) => (
              <View key={index} style={[styles.exclusionTag, styles.locationTag]}>
                <Icon name="location" size={14} color="#0ea5e9" />
                <Text style={styles.exclusionTagText} numberOfLines={1}>{location.name}</Text>
                <TouchableOpacity
                  onPress={() => handleRemoveLocation(location.name)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <Icon name="close-circle" size={18} color="#666" />
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* Fun Segments */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Fun Segments</Text>
        <View style={styles.card}>
          {FUN_SEGMENTS.map((segment) => (
            <TouchableOpacity
              key={segment.id}
              style={styles.toggleRow}
              onPress={() => handleToggleFunSegment(segment.id)}
            >
              <Text style={styles.toggleLabel}>{segment.label}</Text>
              <Switch
                value={settings?.fun_segments.includes(segment.id)}
                onValueChange={() => handleToggleFunSegment(segment.id)}
                trackColor={{ false: '#e0e0e0', true: '#4f46e5' }}
              />
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Schedule */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Auto-Generate Schedule</Text>
        <View style={styles.card}>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Enable Schedule</Text>
            <Switch
              value={schedule?.enabled}
              onValueChange={(enabled) =>
                updateScheduleMutation.mutate({ enabled })
              }
              trackColor={{ false: '#e0e0e0', true: '#4f46e5' }}
            />
          </View>
          {schedule?.enabled && (
            <>
              <View style={styles.daysRow}>
                {DAYS_OF_WEEK.map((day) => (
                  <TouchableOpacity
                    key={day.id}
                    style={[
                      styles.dayButton,
                      schedule?.days_of_week.includes(day.id) &&
                        styles.dayButtonSelected,
                    ]}
                    onPress={() => handleToggleScheduleDay(day.id)}
                  >
                    <Text
                      style={[
                        styles.dayText,
                        schedule?.days_of_week.includes(day.id) &&
                          styles.dayTextSelected,
                      ]}
                    >
                      {day.short}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Time Picker */}
              <View style={styles.timePickerContainer}>
                <Text style={styles.timePickerLabel}>Time</Text>
                <View style={styles.timePicker}>
                  <View style={styles.timePickerColumn}>
                    <TouchableOpacity
                      style={styles.timePickerButton}
                      onPress={() => {
                        const newHour = ((schedule?.time_hour || 0) + 1) % 24;
                        updateScheduleMutation.mutate({ time_hour: newHour });
                      }}
                    >
                      <Icon name="chevron-up" size={20} color="#4f46e5" />
                    </TouchableOpacity>
                    <Text style={styles.timePickerValue}>
                      {(schedule?.time_hour || 0).toString().padStart(2, '0')}
                    </Text>
                    <TouchableOpacity
                      style={styles.timePickerButton}
                      onPress={() => {
                        const newHour = ((schedule?.time_hour || 0) - 1 + 24) % 24;
                        updateScheduleMutation.mutate({ time_hour: newHour });
                      }}
                    >
                      <Icon name="chevron-down" size={20} color="#4f46e5" />
                    </TouchableOpacity>
                  </View>
                  <Text style={styles.timePickerColon}>:</Text>
                  <View style={styles.timePickerColumn}>
                    <TouchableOpacity
                      style={styles.timePickerButton}
                      onPress={() => {
                        const newMinute = ((schedule?.time_minute || 0) + 5) % 60;
                        updateScheduleMutation.mutate({ time_minute: newMinute });
                      }}
                    >
                      <Icon name="chevron-up" size={20} color="#4f46e5" />
                    </TouchableOpacity>
                    <Text style={styles.timePickerValue}>
                      {(schedule?.time_minute || 0).toString().padStart(2, '0')}
                    </Text>
                    <TouchableOpacity
                      style={styles.timePickerButton}
                      onPress={() => {
                        const newMinute = ((schedule?.time_minute || 0) - 5 + 60) % 60;
                        updateScheduleMutation.mutate({ time_minute: newMinute });
                      }}
                    >
                      <Icon name="chevron-down" size={20} color="#4f46e5" />
                    </TouchableOpacity>
                  </View>
                </View>
              </View>

              {/* Timezone Picker */}
              <View style={styles.timezoneContainer}>
                <Text style={styles.timePickerLabel}>Timezone</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.timezoneScroll}>
                  {[
                    { id: 'America/New_York', label: 'Eastern' },
                    { id: 'America/Chicago', label: 'Central' },
                    { id: 'America/Denver', label: 'Mountain' },
                    { id: 'America/Los_Angeles', label: 'Pacific' },
                    { id: 'America/Phoenix', label: 'Arizona' },
                    { id: 'Pacific/Honolulu', label: 'Hawaii' },
                    { id: 'America/Anchorage', label: 'Alaska' },
                    { id: 'Europe/London', label: 'London' },
                    { id: 'Europe/Paris', label: 'Paris' },
                    { id: 'Asia/Tokyo', label: 'Tokyo' },
                  ].map((tz) => (
                    <TouchableOpacity
                      key={tz.id}
                      style={[
                        styles.timezoneOption,
                        schedule?.timezone === tz.id && styles.timezoneOptionSelected,
                      ]}
                      onPress={() => updateScheduleMutation.mutate({ timezone: tz.id })}
                    >
                      <Text
                        style={[
                          styles.timezoneOptionText,
                          schedule?.timezone === tz.id && styles.timezoneOptionTextSelected,
                        ]}
                      >
                        {tz.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>
            </>
          )}
        </View>
      </View>

      {/* Audio Settings */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Audio Settings</Text>
        <View style={styles.card}>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Include Intro Music</Text>
            <Switch
              value={settings?.include_intro_music}
              onValueChange={(include_intro_music) =>
                updateSettingsMutation.mutate({ include_intro_music })
              }
              trackColor={{ false: '#e0e0e0', true: '#4f46e5' }}
            />
          </View>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Include Transitions</Text>
            <Switch
              value={settings?.include_transitions}
              onValueChange={(include_transitions) =>
                updateSettingsMutation.mutate({ include_transitions })
              }
              trackColor={{ false: '#e0e0e0', true: '#4f46e5' }}
            />
          </View>
          <View style={styles.toggleRow}>
            <View style={styles.toggleLabelContainer}>
              <Text style={styles.toggleLabel}>Classical Music Corner</Text>
              <Text style={styles.toggleHint}>Include a classical piece with introduction</Text>
            </View>
            <Switch
              value={settings?.include_music}
              onValueChange={(include_music) =>
                updateSettingsMutation.mutate({ include_music })
              }
              trackColor={{ false: '#e0e0e0', true: '#4f46e5' }}
            />
          </View>
        </View>
      </View>

      {/* Writing Style */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Writing Style</Text>
        <View style={styles.card}>
          <Text style={styles.exclusionHint}>
            Choose a style for how your briefing is written
          </Text>
          <View style={styles.writingStyleOptions}>
            {WRITING_STYLES.map((style) => {
              const isSelected = (settings?.writing_style || 'good_morning_america') === style.id;
              return (
                <TouchableOpacity
                  key={style.id}
                  style={[
                    styles.writingStyleOption,
                    isSelected && styles.writingStyleOptionSelected,
                  ]}
                  onPress={() => updateSettingsMutation.mutate({ writing_style: style.id })}
                >
                  <Text
                    style={[
                      styles.writingStyleOptionText,
                      isSelected && styles.writingStyleOptionTextSelected,
                    ]}
                  >
                    {style.label}
                  </Text>
                  <Text style={[
                    styles.writingStyleOptionDesc,
                    isSelected && styles.writingStyleOptionDescSelected,
                  ]}>
                    {style.description}
                  </Text>
                  {isSelected && (
                    <Icon name="checkmark-circle" size={18} color="#fff" style={{ marginTop: 8 }} />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      </View>

      {/* Voice Settings */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Voice Settings</Text>
        <View style={styles.card}>
          {/* TTS Provider Selection */}
          <Text style={styles.voiceLabel}>TTS Provider</Text>
          <View style={styles.ttsProviderOptions}>
            {[
              { id: 'edge', label: 'Edge TTS', description: 'Free - Microsoft' },
              { id: 'elevenlabs', label: 'ElevenLabs', description: 'Paid - Premium' },
            ].map((provider) => {
              const isSelected = (settings?.tts_provider || 'elevenlabs') === provider.id;
              return (
                <TouchableOpacity
                  key={provider.id}
                  style={[
                    styles.ttsProviderOption,
                    isSelected && styles.ttsProviderOptionSelected,
                  ]}
                  onPress={() => updateSettingsMutation.mutate({ tts_provider: provider.id })}
                >
                  <Text
                    style={[
                      styles.ttsProviderText,
                      isSelected && styles.ttsProviderTextSelected,
                    ]}
                  >
                    {provider.label}
                  </Text>
                  <Text style={[
                    styles.ttsProviderDesc,
                    isSelected && styles.ttsProviderDescSelected,
                  ]}>
                    {provider.description}
                  </Text>
                  {isSelected && (
                    <Icon name="checkmark-circle" size={18} color="#fff" style={{ marginTop: 6 }} />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={styles.voiceLabel}>Host Voice</Text>
          <Text style={styles.voiceHint}>Tap the play button to preview each voice</Text>
          {voicesQuery.isLoading && (
            <View style={styles.voiceLoadingContainer}>
              <ActivityIndicator size="small" color="#4f46e5" />
              <Text style={styles.voiceLoadingText}>Loading voices...</Text>
            </View>
          )}
          <View style={styles.voiceOptions}>
            {allVoices.map((voice) => {
              const isSelected = settings?.voice_id === voice.id;
              const isPreviewing = previewingVoice === voice.id;
              const isLoading = previewLoading === voice.id;
              return (
                <View
                  key={voice.id}
                  style={[
                    styles.voiceOption,
                    isSelected && styles.voiceOptionSelected,
                    voice.isCustom && styles.voiceOptionCustom,
                  ]}
                >
                  <View style={styles.voiceOptionRow}>
                    <TouchableOpacity
                      style={[
                        styles.previewButton,
                        isSelected && styles.previewButtonSelected,
                        isPreviewing && styles.previewButtonPlaying,
                      ]}
                      onPress={() => handlePlayPreview(voice.id)}
                      activeOpacity={0.5}
                      hitSlop={{ top: 15, bottom: 15, left: 15, right: 15 }}
                    >
                      {isLoading ? (
                        <ActivityIndicator size="small" color={isSelected ? '#fff' : '#4f46e5'} />
                      ) : (
                        <Icon
                          name={isPreviewing ? 'stop' : 'play'}
                          size={18}
                          color={isPreviewing ? '#fff' : (isSelected ? '#fff' : '#4f46e5')}
                        />
                      )}
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.voiceOptionInfo}
                      onPress={() => updateSettingsMutation.mutate({ voice_id: voice.id })}
                      activeOpacity={0.7}
                    >
                      <View style={styles.voiceOptionNameRow}>
                        <Text
                          style={[
                            styles.voiceOptionText,
                            isSelected && styles.voiceOptionTextSelected,
                          ]}
                        >
                          {voice.label}
                        </Text>
                        {voice.isCustom && (
                          <View style={[styles.customBadge, isSelected && styles.customBadgeSelected]}>
                            <Text style={[styles.customBadgeText, isSelected && styles.customBadgeTextSelected]}>Custom</Text>
                          </View>
                        )}
                      </View>
                      <Text style={[
                        styles.voiceOptionDesc,
                        isSelected && styles.voiceOptionDescSelected,
                      ]}>
                        {voice.description}
                      </Text>
                    </TouchableOpacity>
                    {isSelected && (
                      <Icon name="checkmark-circle" size={24} color="#fff" />
                    )}
                  </View>
                </View>
              );
            })}
          </View>

          <Text style={[styles.voiceLabel, { marginTop: 16 }]}>Delivery Style</Text>
          <View style={styles.styleOptions}>
            {VOICE_STYLES.map((style) => {
              const isSelected = settings?.voice_style === style.id;
              return (
                <TouchableOpacity
                  key={style.id}
                  style={[
                    styles.styleOption,
                    isSelected && styles.styleOptionSelected,
                  ]}
                  onPress={() => updateSettingsMutation.mutate({ voice_style: style.id })}
                >
                  <Text
                    style={[
                      styles.styleOptionText,
                      isSelected && styles.styleOptionTextSelected,
                    ]}
                  >
                    {style.label}
                  </Text>
                  <Text style={[
                    styles.styleOptionDesc,
                    isSelected && styles.styleOptionDescSelected,
                  ]}>
                    {style.description}
                  </Text>
                  {isSelected && (
                    <Icon name="checkmark-circle" size={18} color="#fff" style={{ marginTop: 6 }} />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>

        </View>
      </View>

        </>
      )}

      {/* Advanced Settings - Server Connection (always visible, even during errors) */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Advanced Settings</Text>
        <View style={styles.card}>
          <View style={styles.connectionStatus}>
            <Icon
              name={isConnected ? 'checkmark-circle' : 'close-circle'}
              size={20}
              color={isConnected ? '#22c55e' : '#ef4444'}
            />
            <Text style={styles.connectionText}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </Text>
          </View>
          <TextInput
            style={styles.input}
            value={localServerUrl}
            onChangeText={setLocalServerUrl}
            placeholder="https://your-server.com"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity
            style={[styles.saveButton, isConnecting && { opacity: 0.7 }]}
            onPress={handleSaveServerUrl}
            disabled={isConnecting}
          >
            {isConnecting ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <ActivityIndicator size="small" color="#fff" />
                <Text style={styles.saveButtonText}>Connecting...</Text>
              </View>
            ) : (
              <Text style={styles.saveButtonText}>Save & Connect</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

    </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f7',
  },
  scrollView: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 60,
    paddingBottom: 20,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1a1a2e',
  },
  section: {
    marginTop: 24,
    paddingHorizontal: 16,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#666',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 4,
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 12,
  },
  toggleLabel: {
    fontSize: 16,
    color: '#1a1a2e',
  },
  toggleLabelContainer: {
    flex: 1,
  },
  toggleHint: {
    fontSize: 12,
    color: '#666',
    marginTop: 2,
  },
  connectionStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    padding: 12,
  },
  connectionText: {
    fontSize: 14,
    color: '#666',
  },
  input: {
    backgroundColor: '#f5f5f7',
    borderRadius: 8,
    padding: 12,
    margin: 12,
    fontSize: 16,
  },
  saveButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 8,
    padding: 12,
    margin: 12,
    alignItems: 'center',
  },
  saveButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  durationOptions: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    padding: 12,
  },
  durationOption: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: '#f5f5f7',
  },
  durationOptionSelected: {
    backgroundColor: '#4f46e5',
  },
  durationText: {
    fontSize: 14,
    color: '#666',
  },
  durationTextSelected: {
    color: '#fff',
    fontWeight: '600',
  },
  daysRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    padding: 12,
  },
  dayButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f5f5f7',
    justifyContent: 'center',
    alignItems: 'center',
  },
  dayButtonSelected: {
    backgroundColor: '#4f46e5',
  },
  dayText: {
    fontSize: 12,
    color: '#666',
  },
  dayTextSelected: {
    color: '#fff',
    fontWeight: '600',
  },
  timeLabel: {
    fontSize: 14,
    color: '#666',
    padding: 12,
    textAlign: 'center',
  },
  exclusionHint: {
    fontSize: 13,
    color: '#888',
    padding: 12,
    paddingBottom: 8,
  },
  exclusionInputRow: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    gap: 8,
  },
  exclusionInput: {
    flex: 1,
    backgroundColor: '#f5f5f7',
    borderRadius: 8,
    padding: 12,
    fontSize: 15,
  },
  addExclusionButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 8,
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  exclusionTags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 12,
    gap: 8,
  },
  exclusionTag: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f0f0f2',
    borderRadius: 16,
    paddingVertical: 6,
    paddingLeft: 12,
    paddingRight: 8,
    gap: 6,
    maxWidth: '100%',
  },
  exclusionTagText: {
    fontSize: 14,
    color: '#333',
    flexShrink: 1,
    maxWidth: 200,
  },
  emptyTagsText: {
    fontSize: 13,
    color: '#999',
    fontStyle: 'italic',
    paddingVertical: 4,
  },
  priorityTag: {
    backgroundColor: '#dcfce7',
    borderColor: '#22c55e',
    borderWidth: 1,
  },
  excludeTag: {
    backgroundColor: '#fef2f2',
    borderColor: '#ef4444',
    borderWidth: 1,
  },
  teamTag: {
    backgroundColor: '#eef2ff',
    borderColor: '#4f46e5',
    borderWidth: 1,
  },
  locationTag: {
    backgroundColor: '#e0f2fe',
    borderColor: '#0ea5e9',
    borderWidth: 1,
  },
  voiceLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#666',
    paddingHorizontal: 12,
    paddingTop: 12,
    paddingBottom: 8,
  },
  voiceHint: {
    fontSize: 12,
    color: '#999',
    paddingHorizontal: 12,
    paddingBottom: 8,
    fontStyle: 'italic',
  },
  voiceOptions: {
    paddingHorizontal: 8,
  },
  previewButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#e8e8ef',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  previewButtonSelected: {
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
  previewButtonPlaying: {
    backgroundColor: '#22c55e',
  },
  voiceOption: {
    padding: 12,
    borderRadius: 8,
    marginHorizontal: 4,
    marginVertical: 4,
    backgroundColor: '#f5f5f7',
  },
  voiceOptionSelected: {
    backgroundColor: '#4f46e5',
  },
  voiceOptionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  voiceOptionInfo: {
    flex: 1,
  },
  voiceOptionText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
  },
  voiceOptionTextSelected: {
    color: '#fff',
  },
  voiceOptionDesc: {
    fontSize: 12,
    color: '#888',
    marginTop: 2,
  },
  voiceOptionDescSelected: {
    color: 'rgba(255,255,255,0.8)',
  },
  voiceOptionCustom: {
    borderWidth: 2,
    borderColor: '#22c55e',
    borderStyle: 'dashed',
  },
  voiceOptionNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  customBadge: {
    backgroundColor: '#dcfce7',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  customBadgeSelected: {
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
  customBadgeText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#22c55e',
  },
  customBadgeTextSelected: {
    color: '#fff',
  },
  voiceLoadingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 12,
    gap: 8,
  },
  voiceLoadingText: {
    fontSize: 14,
    color: '#888',
  },
  styleOptions: {
    flexDirection: 'row',
    paddingHorizontal: 8,
    gap: 8,
  },
  styleOption: {
    flex: 1,
    padding: 12,
    borderRadius: 8,
    backgroundColor: '#f5f5f7',
    alignItems: 'center',
  },
  styleOptionSelected: {
    backgroundColor: '#4f46e5',
  },
  styleOptionText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
  },
  styleOptionTextSelected: {
    color: '#fff',
  },
  styleOptionDesc: {
    fontSize: 10,
    color: '#888',
    marginTop: 4,
    textAlign: 'center',
  },
  styleOptionDescSelected: {
    color: 'rgba(255,255,255,0.8)',
  },
  ttsProviderOptions: {
    flexDirection: 'row',
    paddingHorizontal: 8,
    gap: 8,
    marginBottom: 16,
  },
  ttsProviderOption: {
    flex: 1,
    padding: 12,
    borderRadius: 8,
    backgroundColor: '#f5f5f7',
    alignItems: 'center',
  },
  ttsProviderOptionSelected: {
    backgroundColor: '#4f46e5',
  },
  ttsProviderText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
  },
  ttsProviderTextSelected: {
    color: '#fff',
  },
  ttsProviderDesc: {
    fontSize: 10,
    color: '#888',
    marginTop: 4,
    textAlign: 'center',
  },
  ttsProviderDescSelected: {
    color: 'rgba(255,255,255,0.8)',
  },
  segmentOrderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f2',
  },
  segmentOrderInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  segmentOrderLabel: {
    fontSize: 16,
    fontWeight: '500',
    color: '#333',
  },
  segmentOrderButtons: {
    flexDirection: 'row',
    gap: 4,
  },
  segmentOrderButton: {
    width: 36,
    height: 36,
    borderRadius: 8,
    backgroundColor: '#f0f0f2',
    justifyContent: 'center',
    alignItems: 'center',
  },
  segmentOrderButtonDisabled: {
    backgroundColor: '#f8f8f8',
  },
  timePickerContainer: {
    padding: 12,
    alignItems: 'center',
  },
  timePickerLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#666',
    marginBottom: 12,
  },
  timePicker: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f5f5f7',
    borderRadius: 12,
    padding: 8,
  },
  timePickerColumn: {
    alignItems: 'center',
    width: 50,
  },
  timePickerButton: {
    padding: 8,
  },
  timePickerValue: {
    fontSize: 28,
    fontWeight: '600',
    color: '#1a1a2e',
  },
  timePickerColon: {
    fontSize: 28,
    fontWeight: '600',
    color: '#1a1a2e',
    marginHorizontal: 4,
  },
  timezoneContainer: {
    padding: 12,
    paddingTop: 0,
  },
  timezoneScroll: {
    marginTop: 8,
  },
  timezoneOption: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 20,
    backgroundColor: '#f5f5f7',
    marginRight: 8,
  },
  timezoneOptionSelected: {
    backgroundColor: '#4f46e5',
  },
  timezoneOptionText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#333',
  },
  timezoneOptionTextSelected: {
    color: '#fff',
  },
  writingStyleOptions: {
    paddingHorizontal: 8,
    paddingBottom: 8,
  },
  writingStyleOption: {
    padding: 14,
    borderRadius: 10,
    backgroundColor: '#f5f5f7',
    marginVertical: 4,
  },
  writingStyleOptionSelected: {
    backgroundColor: '#4f46e5',
  },
  writingStyleOptionText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
  },
  writingStyleOptionTextSelected: {
    color: '#fff',
  },
  writingStyleOptionDesc: {
    fontSize: 13,
    color: '#666',
    marginTop: 4,
  },
  writingStyleOptionDescSelected: {
    color: 'rgba(255,255,255,0.8)',
  },
});
