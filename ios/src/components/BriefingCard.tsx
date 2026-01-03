/**
 * Briefing card component for displaying briefing items
 */

import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import Icon from 'react-native-vector-icons/Ionicons';
import { format } from 'date-fns';
import { Briefing } from '../types';

interface BriefingCardProps {
  briefing: Briefing;
  onPress: () => void;
  onDelete?: () => void;
  isPlaying?: boolean;
}

export function BriefingCard({
  briefing,
  onPress,
  onDelete,
  isPlaying,
}: BriefingCardProps) {
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    return `${mins} min`;
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Today';
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday';
    }
    return format(date, 'EEEE, MMM d');
  };

  return (
    <TouchableOpacity
      style={[styles.container, isPlaying && styles.containerPlaying]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <View style={styles.iconContainer}>
        <Icon
          name={isPlaying ? 'radio' : 'radio-outline'}
          size={32}
          color={isPlaying ? '#4f46e5' : '#666'}
        />
        {isPlaying && (
          <View style={styles.playingIndicator}>
            <Icon name="volume-high" size={12} color="#4f46e5" />
          </View>
        )}
      </View>

      <View style={styles.content}>
        <Text style={styles.date}>{formatDate(briefing.created_at)}</Text>
        <Text style={styles.title} numberOfLines={1}>
          {briefing.title}
        </Text>
        <View style={styles.meta}>
          <Icon name="time-outline" size={14} color="#888" />
          <Text style={styles.duration}>
            {formatDuration(briefing.duration_seconds)}
          </Text>
          <Text style={styles.segments}>
            {briefing.segments.length} segments
          </Text>
        </View>
      </View>

      <View style={styles.actions}>
        {isPlaying ? (
          <Icon name="pause-circle" size={40} color="#4f46e5" />
        ) : (
          <Icon name="play-circle" size={40} color="#4f46e5" />
        )}
      </View>

      {onDelete && (
        <TouchableOpacity
          style={styles.deleteButton}
          onPress={onDelete}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Icon name="trash-outline" size={20} color="#ff4444" />
        </TouchableOpacity>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 16,
    marginVertical: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  containerPlaying: {
    borderWidth: 2,
    borderColor: '#4f46e5',
  },
  iconContainer: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: '#f0f0f5',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  playingIndicator: {
    position: 'absolute',
    bottom: -2,
    right: -2,
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 2,
  },
  content: {
    flex: 1,
  },
  date: {
    fontSize: 12,
    color: '#888',
    marginBottom: 2,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1a1a2e',
    marginBottom: 4,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  duration: {
    fontSize: 12,
    color: '#888',
    marginRight: 8,
  },
  segments: {
    fontSize: 12,
    color: '#888',
  },
  actions: {
    marginLeft: 8,
  },
  deleteButton: {
    position: 'absolute',
    top: 8,
    right: 8,
    padding: 4,
  },
});
