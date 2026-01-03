/**
 * Audio playback service using react-native-track-player
 */

import TrackPlayer, {
  Capability,
  Event,
  RepeatMode,
  State,
  usePlaybackState,
  useProgress,
} from 'react-native-track-player';
import { Briefing, BriefingSegment } from '../types';
import { api } from './api';

let isSetup = false;

export async function setupPlayer() {
  if (isSetup) return;

  try {
    await TrackPlayer.setupPlayer({
      maxCacheSize: 1024 * 50, // 50 MB cache
    });

    await TrackPlayer.updateOptions({
      capabilities: [
        Capability.Play,
        Capability.Pause,
        Capability.Stop,
        Capability.SeekTo,
        Capability.SkipToNext,
        Capability.SkipToPrevious,
      ],
      compactCapabilities: [Capability.Play, Capability.Pause, Capability.SeekTo],
      notificationCapabilities: [
        Capability.Play,
        Capability.Pause,
        Capability.SeekTo,
      ],
    });

    await TrackPlayer.setRepeatMode(RepeatMode.Off);

    isSetup = true;
    console.log('setupPlayer: Successfully initialized');
  } catch (error: any) {
    // Player might already be initialized from a previous session
    if (error?.message?.includes('already been initialized')) {
      console.log('setupPlayer: Player was already initialized');
      isSetup = true;
      return;
    }
    console.error('Error setting up track player:', error);
    throw new Error(`Failed to initialize audio player: ${error?.message || error}`);
  }
}

export async function loadBriefing(briefing: Briefing) {
  await setupPlayer();

  // Clear current queue
  await TrackPlayer.reset();

  // Get the full audio URL
  const audioUrl = api.getAudioUrl(briefing.audio_url);

  // Add the track
  await TrackPlayer.add({
    id: briefing.id.toString(),
    url: audioUrl,
    title: briefing.title,
    artist: 'Morning Drive',
    artwork: undefined, // Could add app icon here
    duration: briefing.duration_seconds,
  });
}

export async function play() {
  await TrackPlayer.play();
}

export async function pause() {
  await TrackPlayer.pause();
}

export async function stop() {
  await TrackPlayer.stop();
}

export async function seekTo(position: number) {
  await TrackPlayer.seekTo(position);
}

export async function skipForward(seconds = 15) {
  const progress = await TrackPlayer.getProgress();
  await TrackPlayer.seekTo(progress.position + seconds);
}

export async function skipBackward(seconds = 15) {
  const progress = await TrackPlayer.getProgress();
  await TrackPlayer.seekTo(Math.max(0, progress.position - seconds));
}

export async function setPlaybackRate(rate: number) {
  await TrackPlayer.setRate(rate);
}

export function getCurrentSegment(
  segments: BriefingSegment[],
  position: number
): BriefingSegment | null {
  return (
    segments.find(
      (seg) => position >= seg.start_time && position < seg.end_time
    ) || null
  );
}

export async function skipToSegment(segment: BriefingSegment) {
  await TrackPlayer.seekTo(segment.start_time);
}

// Hook for getting playback state
export function usePlayerState() {
  const playbackState = usePlaybackState();
  const progress = useProgress();

  const isPlaying = playbackState.state === State.Playing;
  const isLoading =
    playbackState.state === State.Loading ||
    playbackState.state === State.Buffering;
  const isPaused = playbackState.state === State.Paused;
  const isStopped =
    playbackState.state === State.Stopped ||
    playbackState.state === State.None;

  return {
    isPlaying,
    isLoading,
    isPaused,
    isStopped,
    position: progress.position,
    duration: progress.duration,
    buffered: progress.buffered,
  };
}

// Playback service for background events
export async function playbackService() {
  TrackPlayer.addEventListener(Event.RemotePlay, () => TrackPlayer.play());
  TrackPlayer.addEventListener(Event.RemotePause, () => TrackPlayer.pause());
  TrackPlayer.addEventListener(Event.RemoteStop, () => TrackPlayer.stop());
  TrackPlayer.addEventListener(Event.RemoteSeek, (event) =>
    TrackPlayer.seekTo(event.position)
  );
  TrackPlayer.addEventListener(Event.RemoteJumpForward, () => skipForward(15));
  TrackPlayer.addEventListener(Event.RemoteJumpBackward, () =>
    skipBackward(15)
  );
}

// Voice preview state
let previewState: {
  wasPlaying: boolean;
  previousQueue: any[];
  previousPosition: number;
} | null = null;

let isPreviewPlaying = false;

export async function playVoicePreview(previewUrl: string): Promise<void> {
  console.log('playVoicePreview: Starting with URL:', previewUrl);

  try {
    await setupPlayer();
    console.log('playVoicePreview: Player setup complete');
  } catch (error: any) {
    throw new Error(`Player setup failed: ${error?.message || error}`);
  }

  // Save current state if not already in preview mode
  if (!isPreviewPlaying) {
    try {
      const queue = await TrackPlayer.getQueue();
      const progress = await TrackPlayer.getProgress();
      const playbackState = await TrackPlayer.getPlaybackState();

      previewState = {
        wasPlaying: playbackState.state === State.Playing,
        previousQueue: queue,
        previousPosition: progress.position,
      };

      // Pause current playback
      await TrackPlayer.pause();
    } catch (error) {
      console.log('playVoicePreview: Could not save current state (may be first use)');
    }
  }

  // Clear and add preview track
  console.log('playVoicePreview: Resetting player');
  try {
    await TrackPlayer.reset();
  } catch (error: any) {
    throw new Error(`Player reset failed: ${error?.message || error}`);
  }

  console.log('playVoicePreview: Adding track with URL:', previewUrl);
  try {
    await TrackPlayer.add({
      id: 'voice-preview',
      url: previewUrl,
      title: 'Voice Preview',
      artist: 'Morning Drive',
    });
  } catch (error: any) {
    throw new Error(`Failed to add track: ${error?.message || error}`);
  }

  isPreviewPlaying = true;
  console.log('playVoicePreview: Starting playback');
  try {
    await TrackPlayer.play();
  } catch (error: any) {
    isPreviewPlaying = false;
    throw new Error(`Failed to start playback: ${error?.message || error}`);
  }

  // Verify playback started
  const state = await TrackPlayer.getPlaybackState();
  console.log('playVoicePreview: Current state after play:', state.state);
}

export async function stopVoicePreview(): Promise<void> {
  if (!isPreviewPlaying) return;

  await TrackPlayer.reset();
  isPreviewPlaying = false;

  // Restore previous state if we have it
  if (previewState && previewState.previousQueue.length > 0) {
    for (const track of previewState.previousQueue) {
      await TrackPlayer.add(track);
    }
    await TrackPlayer.seekTo(previewState.previousPosition);

    if (previewState.wasPlaying) {
      await TrackPlayer.play();
    }
  }

  previewState = null;
}

export function getIsPreviewPlaying(): boolean {
  return isPreviewPlaying;
}
