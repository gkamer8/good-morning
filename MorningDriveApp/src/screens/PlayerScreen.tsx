/**
 * Full-screen audio player with scrubbing and segment navigation
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Dimensions,
  ScrollView,
} from 'react-native';
import TextTicker from 'react-native-text-ticker';
import { useNavigation } from '@react-navigation/native';
import Icon from 'react-native-vector-icons/Ionicons';
import Slider from '@react-native-community/slider';

import {
  usePlayerState,
  play,
  pause,
  seekTo,
  skipForward,
  skipBackward,
  getCurrentSegment,
  skipToSegment,
  setPlaybackRate,
} from '../services/audio';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useBriefingsStore } from '../store';
import { BriefingSegment } from '../types';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

// Segment type icons and colors
const SEGMENT_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  intro: { icon: 'sunny', color: '#FFB347', label: 'Intro' },
  news: { icon: 'newspaper', color: '#4A90D9', label: 'News' },
  sports: { icon: 'football', color: '#50C878', label: 'Sports' },
  weather: { icon: 'partly-sunny', color: '#87CEEB', label: 'Weather' },
  finance: { icon: 'trending-up', color: '#90EE90', label: 'Markets' },
  fun: { icon: 'happy', color: '#DDA0DD', label: 'Fun' },
  history: { icon: 'time', color: '#D2691E', label: 'History' },
  quote: { icon: 'chatbubble-ellipses', color: '#FFD700', label: 'Quote' },
  outro: { icon: 'moon', color: '#9370DB', label: 'Outro' },
  music: { icon: 'musical-notes', color: '#C9A0DC', label: 'Music' },
  classical: { icon: 'musical-notes', color: '#C9A0DC', label: 'Classical' },
};

export function PlayerScreen() {
  const navigation = useNavigation();
  const { currentBriefing } = useBriefingsStore();
  const { isPlaying, isLoading, position, duration } = usePlayerState();

  const [isSeeking, setIsSeeking] = useState(false);
  const [seekPosition, setSeekPosition] = useState(0);
  const [pendingSeekPosition, setPendingSeekPosition] = useState<number | null>(null);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  const SPEED_OPTIONS = [0.75, 1.0, 1.25, 1.5, 2.0];

  // Load saved playback speed on mount
  useEffect(() => {
    AsyncStorage.getItem('playbackSpeed').then((saved) => {
      if (saved) {
        const speed = parseFloat(saved);
        setPlaybackSpeed(speed);
        setPlaybackRate(speed);
      }
    });
  }, []);

  const handleSpeedChange = useCallback(async (speed: number) => {
    setPlaybackSpeed(speed);
    await setPlaybackRate(speed);
    await AsyncStorage.setItem('playbackSpeed', speed.toString());
  }, []);

  // Display position: use seek/pending position while sliding or waiting for seek
  const displayPosition = useMemo(() => {
    if (isSeeking) return seekPosition;
    if (pendingSeekPosition !== null) {
      // Check if player has caught up to where we seeked
      if (Math.abs(position - pendingSeekPosition) < 1) {
        // Player caught up, clear pending
        setTimeout(() => setPendingSeekPosition(null), 0);
        return position;
      }
      return pendingSeekPosition;
    }
    return position;
  }, [isSeeking, seekPosition, pendingSeekPosition, position]);

  // Memoize segment to prevent recalculation on every render
  const currentSegment = useMemo(() => {
    if (!currentBriefing) return null;
    return getCurrentSegment(currentBriefing.segments, displayPosition);
  }, [currentBriefing, Math.floor(displayPosition)]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handlePlayPause = async () => {
    if (isPlaying) {
      await pause();
    } else {
      await play();
    }
  };

  // Slider callbacks
  const handleSlidingStart = useCallback(() => {
    setIsSeeking(true);
    setPendingSeekPosition(null);
    setSeekPosition(position);
  }, [position]);

  const handleValueChange = useCallback((value: number) => {
    setSeekPosition(value);
  }, []);

  const handleSlidingComplete = useCallback(async (value: number) => {
    setPendingSeekPosition(value);
    setIsSeeking(false);
    await seekTo(value);
  }, []);

  const handleSegmentPress = async (segment: BriefingSegment) => {
    await skipToSegment(segment);
  };

  const getSegmentConfig = (type: string) => {
    return SEGMENT_CONFIG[type] || SEGMENT_CONFIG.news;
  };

  if (!currentBriefing) {
    return (
      <View style={styles.container}>
        <View style={styles.emptyState}>
          <Icon name="musical-notes" size={64} color="#666" />
          <Text style={styles.emptyText}>No briefing selected</Text>
          <TouchableOpacity
            style={styles.backButton}
            onPress={() => navigation.goBack()}
          >
            <Text style={styles.backButtonText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.headerButton}
        >
          <Icon name="chevron-down" size={28} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Now Playing</Text>
        <View style={styles.headerButton} />
      </View>

      {/* Album Art / Visualization */}
      <View style={styles.artContainer}>
        <View style={styles.artWrapper}>
          <View style={[
            styles.artInner,
            { backgroundColor: currentSegment ? getSegmentConfig(currentSegment.type).color : '#4f46e5' }
          ]}>
            <Icon
              name={currentSegment ? getSegmentConfig(currentSegment.type).icon : 'radio'}
              size={80}
              color="#fff"
            />
          </View>
          {isPlaying && (
            <View style={styles.playingIndicator}>
              <View style={[styles.soundBar, styles.soundBar1]} />
              <View style={[styles.soundBar, styles.soundBar2]} />
              <View style={[styles.soundBar, styles.soundBar3]} />
              <View style={[styles.soundBar, styles.soundBar4]} />
            </View>
          )}
        </View>
      </View>

      {/* Current Segment Info */}
      <View style={styles.segmentInfo}>
        <Text style={styles.segmentLabel} numberOfLines={1}>
          {currentSegment ? getSegmentConfig(currentSegment.type).label.toUpperCase() : 'MORNING DRIVE'}
        </Text>
        <TextTicker
          style={styles.segmentTitle}
          duration={10000}
          loop
          bounce={false}
          repeatSpacer={50}
          marqueeDelay={1000}
          scrollSpeed={50}
        >
          {currentSegment?.title || currentBriefing.title}
        </TextTicker>
      </View>

      {/* Progress Bar with Slider */}
      <View style={styles.progressSection}>
        {/* Segment markers background */}
        <View style={styles.segmentMarkersContainer}>
          {currentBriefing.segments.map((seg, index) => {
            const segStart = duration > 0 ? seg.start_time / duration : 0;
            const segWidth = duration > 0 ? (seg.end_time - seg.start_time) / duration : 0;
            const config = getSegmentConfig(seg.type);
            return (
              <View
                key={index}
                style={[
                  styles.segmentMarker,
                  {
                    left: `${segStart * 100}%`,
                    width: `${segWidth * 100}%`,
                    backgroundColor: config.color,
                    opacity: currentSegment?.type === seg.type ? 1 : 0.5,
                  },
                ]}
              />
            );
          })}
        </View>

        {/* Slider for scrubbing */}
        <Slider
          style={styles.slider}
          minimumValue={0}
          maximumValue={duration || 1}
          value={displayPosition}
          onSlidingStart={handleSlidingStart}
          onValueChange={handleValueChange}
          onSlidingComplete={handleSlidingComplete}
          minimumTrackTintColor="#ffffff"
          maximumTrackTintColor="rgba(255,255,255,0.3)"
          thumbTintColor="#ffffff"
        />

        {/* Time labels */}
        <View style={styles.timeContainer}>
          <Text style={styles.timeText}>{formatTime(displayPosition)}</Text>
          <Text style={styles.timeText}>-{formatTime(Math.max(0, duration - displayPosition))}</Text>
        </View>
      </View>

      {/* Main Controls */}
      <View style={styles.controls}>
        <TouchableOpacity
          onPress={() => skipBackward(10)}
          style={styles.skipButton}
        >
          <Icon name="play-back" size={28} color="#fff" />
          <Text style={styles.skipLabel}>10</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={handlePlayPause}
          style={styles.playButton}
        >
          <Icon
            name={isPlaying ? 'pause' : 'play'}
            size={40}
            color="#1a1a2e"
          />
        </TouchableOpacity>

        <TouchableOpacity
          onPress={() => skipForward(10)}
          style={styles.skipButton}
        >
          <Icon name="play-forward" size={28} color="#fff" />
          <Text style={styles.skipLabel}>10</Text>
        </TouchableOpacity>
      </View>

      {/* Speed Control */}
      <View style={styles.speedControl}>
        {SPEED_OPTIONS.map((speed) => (
          <TouchableOpacity
            key={speed}
            style={[
              styles.speedButton,
              playbackSpeed === speed && styles.speedButtonActive,
            ]}
            onPress={() => handleSpeedChange(speed)}
          >
            <Text
              style={[
                styles.speedButtonText,
                playbackSpeed === speed && styles.speedButtonTextActive,
              ]}
            >
              {speed}x
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Segment List */}
      <View style={styles.segmentList}>
          <Text style={styles.segmentListTitle}>Segments</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.segmentListContent}
          >
            {currentBriefing.segments.map((segment, index) => {
              const config = getSegmentConfig(segment.type);
              const isActive = currentSegment?.type === segment.type &&
                currentSegment?.start_time === segment.start_time;

              return (
                <TouchableOpacity
                  key={index}
                  style={[
                    styles.segmentChip,
                    { borderColor: config.color },
                    isActive && { backgroundColor: config.color },
                  ]}
                  onPress={() => handleSegmentPress(segment)}
                >
                  <Icon
                    name={config.icon}
                    size={16}
                    color={isActive ? '#fff' : config.color}
                  />
                  <Text style={[
                    styles.segmentChipText,
                    { color: isActive ? '#fff' : config.color },
                  ]}>
                    {config.label}
                  </Text>
                  <Text style={[
                    styles.segmentChipTime,
                    { color: isActive ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.5)' },
                  ]}>
                    {formatTime(segment.start_time)}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a2e',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 60,
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  headerButton: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    opacity: 0.8,
  },
  artContainer: {
    alignItems: 'center',
    paddingVertical: 20,
  },
  artWrapper: {
    position: 'relative',
  },
  artInner: {
    width: 200,
    height: 200,
    borderRadius: 100,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 10,
  },
  playingIndicator: {
    position: 'absolute',
    bottom: -30,
    left: '50%',
    marginLeft: -40,
    flexDirection: 'row',
    gap: 4,
    height: 20,
    alignItems: 'flex-end',
  },
  soundBar: {
    width: 4,
    backgroundColor: '#4f46e5',
    borderRadius: 2,
  },
  soundBar1: {
    height: 8,
  },
  soundBar2: {
    height: 16,
  },
  soundBar3: {
    height: 12,
  },
  soundBar4: {
    height: 20,
  },
  segmentInfo: {
    alignItems: 'center',
    paddingHorizontal: 40,
    marginTop: 20,
  },
  segmentLabel: {
    fontSize: 12,
    color: '#888',
    letterSpacing: 2,
    marginBottom: 8,
  },
  segmentTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#fff',
    textAlign: 'center',
  },
  progressSection: {
    paddingHorizontal: 20,
    marginTop: 24,
  },
  segmentMarkersContainer: {
    position: 'absolute',
    left: 20,
    right: 20,
    top: 17,
    height: 6,
    flexDirection: 'row',
    borderRadius: 3,
    overflow: 'hidden',
    zIndex: 0,
  },
  segmentMarker: {
    position: 'absolute',
    height: '100%',
  },
  slider: {
    width: '100%',
    height: 40,
    zIndex: 1,
  },
  timeContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  timeText: {
    fontSize: 12,
    color: '#888',
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 40,
    marginTop: 30,
  },
  speedControl: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
    marginTop: 16,
  },
  speedButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.1)',
  },
  speedButtonActive: {
    backgroundColor: '#4f46e5',
  },
  speedButtonText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#888',
  },
  speedButtonTextActive: {
    color: '#fff',
  },
  skipButton: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 60,
    height: 60,
  },
  skipLabel: {
    fontSize: 10,
    color: '#888',
    marginTop: 2,
  },
  playButton: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#fff',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#fff',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 10,
  },
  segmentList: {
    marginTop: 24,
    paddingBottom: 40,
  },
  segmentListTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#888',
    marginLeft: 20,
    marginBottom: 12,
  },
  segmentListContent: {
    paddingHorizontal: 20,
    gap: 10,
  },
  segmentChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    borderWidth: 1,
    backgroundColor: 'rgba(255,255,255,0.05)',
  },
  segmentChipText: {
    fontSize: 14,
    fontWeight: '600',
  },
  segmentChipTime: {
    fontSize: 12,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  emptyText: {
    fontSize: 18,
    color: '#666',
  },
  backButton: {
    marginTop: 20,
    paddingHorizontal: 24,
    paddingVertical: 12,
    backgroundColor: '#4f46e5',
    borderRadius: 20,
  },
  backButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
