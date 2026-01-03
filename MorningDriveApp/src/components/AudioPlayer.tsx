/**
 * Audio player component with playback controls
 */

import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import Icon from 'react-native-vector-icons/Ionicons';
import { Briefing, BriefingSegment } from '../types';
import {
  usePlayerState,
  play,
  pause,
  skipForward,
  skipBackward,
  seekTo,
  getCurrentSegment,
  skipToSegment,
} from '../services/audio';

interface AudioPlayerProps {
  briefing: Briefing;
  onClose?: () => void;
}

export function AudioPlayer({ briefing, onClose }: AudioPlayerProps) {
  const { isPlaying, isLoading, position, duration } = usePlayerState();

  const currentSegment = getCurrentSegment(briefing.segments, position);

  const handlePlayPause = async () => {
    if (isPlaying) {
      await pause();
    } else {
      await play();
    }
  };

  const handleSeek = async (value: number) => {
    await seekTo(value);
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const progress = duration > 0 ? (position / duration) * 100 : 0;

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        {onClose && (
          <TouchableOpacity onPress={onClose} style={styles.closeButton}>
            <Icon name="chevron-down" size={28} color="#fff" />
          </TouchableOpacity>
        )}
        <Text style={styles.title} numberOfLines={1}>
          {briefing.title}
        </Text>
      </View>

      {/* Current Segment */}
      {currentSegment && (
        <View style={styles.segmentInfo}>
          <Text style={styles.segmentLabel}>NOW PLAYING</Text>
          <Text style={styles.segmentTitle}>{currentSegment.title}</Text>
        </View>
      )}

      {/* Progress Bar */}
      <View style={styles.progressContainer}>
        <View style={styles.progressBar}>
          <View style={[styles.progressFill, { width: `${progress}%` }]} />
        </View>
        <View style={styles.timeContainer}>
          <Text style={styles.timeText}>{formatTime(position)}</Text>
          <Text style={styles.timeText}>{formatTime(duration)}</Text>
        </View>
      </View>

      {/* Segment Markers */}
      <View style={styles.segmentMarkers}>
        {briefing.segments.map((seg, index) => {
          const markerPosition = (seg.start_time / duration) * 100;
          const isActive = currentSegment?.type === seg.type;
          return (
            <TouchableOpacity
              key={index}
              style={[
                styles.segmentMarker,
                { left: `${markerPosition}%` },
                isActive && styles.segmentMarkerActive,
              ]}
              onPress={() => skipToSegment(seg)}
            >
              <Text style={styles.segmentMarkerText}>
                {seg.title.substring(0, 3)}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Controls */}
      <View style={styles.controls}>
        <TouchableOpacity
          onPress={() => skipBackward(15)}
          style={styles.controlButton}
        >
          <Icon name="play-back" size={32} color="#fff" />
          <Text style={styles.skipText}>15</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={handlePlayPause}
          style={styles.playButton}
          disabled={isLoading}
        >
          {isLoading ? (
            <ActivityIndicator size="large" color="#fff" />
          ) : (
            <Icon
              name={isPlaying ? 'pause' : 'play'}
              size={48}
              color="#fff"
            />
          )}
        </TouchableOpacity>

        <TouchableOpacity
          onPress={() => skipForward(15)}
          style={styles.controlButton}
        >
          <Icon name="play-forward" size={32} color="#fff" />
          <Text style={styles.skipText}>15</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a2e',
    padding: 20,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 40,
  },
  closeButton: {
    marginRight: 16,
  },
  title: {
    flex: 1,
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
  },
  segmentInfo: {
    alignItems: 'center',
    marginBottom: 40,
  },
  segmentLabel: {
    fontSize: 12,
    color: '#888',
    letterSpacing: 2,
    marginBottom: 8,
  },
  segmentTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#fff',
  },
  progressContainer: {
    marginBottom: 20,
  },
  progressBar: {
    height: 4,
    backgroundColor: '#333',
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#4f46e5',
  },
  timeContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 8,
  },
  timeText: {
    fontSize: 12,
    color: '#888',
  },
  segmentMarkers: {
    height: 30,
    position: 'relative',
    marginBottom: 40,
  },
  segmentMarker: {
    position: 'absolute',
    padding: 4,
    backgroundColor: '#333',
    borderRadius: 4,
    transform: [{ translateX: -15 }],
  },
  segmentMarkerActive: {
    backgroundColor: '#4f46e5',
  },
  segmentMarkerText: {
    fontSize: 10,
    color: '#fff',
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 40,
  },
  controlButton: {
    alignItems: 'center',
  },
  playButton: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#4f46e5',
    justifyContent: 'center',
    alignItems: 'center',
  },
  skipText: {
    fontSize: 10,
    color: '#888',
    marginTop: 2,
  },
});
