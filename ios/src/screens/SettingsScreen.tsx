/**
 * Settings screen for configuring preferences
 */

import React, { useEffect, useState } from 'react';
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
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Icon from 'react-native-vector-icons/Ionicons';

import { api } from '../services/api';
import { useSettingsStore, useAppConfigStore } from '../store';
import {
  NEWS_TOPICS,
  NEWS_SOURCES,
  SPORTS_LEAGUES,
  FUN_SEGMENTS,
  DAYS_OF_WEEK,
} from '../types';

export function SettingsScreen() {
  const navigation = useNavigation();
  const queryClient = useQueryClient();

  const { settings, setSettings, schedule, setSchedule } = useSettingsStore();
  const { serverUrl, setServerUrl, isConnected, setConnected } =
    useAppConfigStore();

  const [localServerUrl, setLocalServerUrl] = useState(serverUrl);

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

  const handleToggleScheduleDay = (day: number) => {
    if (!schedule) return;
    const newDays = schedule.days_of_week.includes(day)
      ? schedule.days_of_week.filter((d) => d !== day)
      : [...schedule.days_of_week, day].sort();
    updateScheduleMutation.mutate({ days_of_week: newDays });
  };

  const handleSaveServerUrl = async () => {
    try {
      await api.setBaseUrl(localServerUrl);
      setServerUrl(localServerUrl);
      const healthy = await api.healthCheck();
      setConnected(healthy);
      if (healthy) {
        Alert.alert('Connected', 'Successfully connected to server');
        queryClient.invalidateQueries();
      } else {
        Alert.alert('Error', 'Could not connect to server');
      }
    } catch (error) {
      Alert.alert('Error', 'Invalid server URL');
    }
  };

  if (settingsQuery.isLoading || scheduleQuery.isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#4f46e5" />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Icon name="arrow-back" size={24} color="#1a1a2e" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Settings</Text>
        <View style={{ width: 24 }} />
      </View>

      {/* Server Connection */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Server Connection</Text>
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
            placeholder="http://your-server:8000"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity
            style={styles.saveButton}
            onPress={handleSaveServerUrl}
          >
            <Text style={styles.saveButtonText}>Save & Connect</Text>
          </TouchableOpacity>
        </View>
      </View>

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
              <Text style={styles.timeLabel}>
                Time: {schedule?.time_hour}:
                {schedule?.time_minute.toString().padStart(2, '0')} (
                {schedule?.timezone})
              </Text>
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
        </View>
      </View>

      <View style={{ height: 50 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f7',
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
});
