/**
 * CarPlay integration service
 */

import CarPlay, {
  ListTemplate,
  NowPlayingTemplate,
} from 'react-native-carplay';
import { NativeModules } from 'react-native';
import { format } from 'date-fns';
import { Briefing } from '../types';
import { loadBriefing, play, pause, skipForward, skipBackward } from './audio';

// Get native module for polling
const { RNCarPlay } = NativeModules;

let isConnected = false;
let nowPlayingTemplate: NowPlayingTemplate | null = null;
let listTemplate: ListTemplate | null = null;
let isCarPlayAvailable = false;
let pendingBriefings: Briefing[] = [];
let pendingOnSelect: ((briefing: Briefing) => void) | null = null;
let connectionCheckInterval: ReturnType<typeof setInterval> | null = null;

export function setupCarPlay(
  briefings: Briefing[],
  onSelectBriefing: (briefing: Briefing) => void
) {
  console.log('[CarPlay] Setting up CarPlay...');

  // Store for later use
  pendingBriefings = briefings;
  pendingOnSelect = onSelectBriefing;

  // Check if CarPlay module is available
  if (!CarPlay || typeof CarPlay.registerOnConnect !== 'function') {
    console.log('[CarPlay] CarPlay not available');
    isCarPlayAvailable = false;
    return;
  }

  isCarPlayAvailable = true;

  // Handle CarPlay connection (events may not work in new architecture)
  CarPlay.registerOnConnect((window) => {
    console.log('[CarPlay] CarPlay connected event received!', window);
    isConnected = true;
    stopConnectionCheck();
    setupTemplates(pendingBriefings, pendingOnSelect!);
  });

  CarPlay.registerOnDisconnect(() => {
    console.log('[CarPlay] CarPlay disconnected');
    isConnected = false;
    nowPlayingTemplate = null;
    listTemplate = null;
  });

  // WORKAROUND: Events don't work in new architecture, so poll for connection.
  // CarPlay connects when user taps app icon, which could be minutes after app launch.
  // Poll indefinitely every 2 seconds until connected.
  let pollCount = 0;

  const pollInterval = setInterval(() => {
    pollCount++;

    // Only log every 10th poll to reduce noise
    if (pollCount % 10 === 1) {
      RNCarPlay?.checkForConnection?.(); // This logs isConnected status
    }

    // Try to set up templates if not yet connected
    if (!isConnected && pendingOnSelect) {
      // Log before attempting (this calls native so we can see it)
      RNCarPlay?.checkForConnection?.();

      try {
        console.log('[CarPlay] About to call setupTemplates...');
        isConnected = true;
        setupTemplates(pendingBriefings, pendingOnSelect);
        console.log('[CarPlay] Template setup succeeded on poll #' + pollCount);
        // Log after success
        RNCarPlay?.checkForConnection?.();
        clearInterval(pollInterval);
      } catch (error: any) {
        console.log('[CarPlay] Template setup error:', error?.message || error);
        // Log after failure
        RNCarPlay?.checkForConnection?.();
        isConnected = false;
      }
    }

    // Stop polling once connected
    if (isConnected) {
      console.log('[CarPlay] Connected! Stopping poll.');
      clearInterval(pollInterval);
    }
  }, 2000); // Poll every 2 seconds
}

function checkAndSetupIfConnected() {
  if ((CarPlay as any).connected && !isConnected) {
    console.log('[CarPlay] Already connected, setting up templates...');
    isConnected = true;
    stopConnectionCheck();
    if (pendingOnSelect) {
      setupTemplates(pendingBriefings, pendingOnSelect);
    }
  }
}

function checkConnectionWithCallback(): Promise<{connected: boolean; window?: any}> {
  return new Promise((resolve) => {
    if (!RNCarPlay?.isCarPlayConnected) {
      console.log('[CarPlay] isCarPlayConnected not available, trying checkForConnection');
      // Fall back to checkForConnection which will try to emit event
      RNCarPlay?.checkForConnection?.();
      resolve({ connected: false });
      return;
    }

    RNCarPlay.isCarPlayConnected((connected: boolean, windowInfo: any) => {
      console.log('[CarPlay] Callback received:', connected, windowInfo);
      resolve({ connected, window: windowInfo });
    });
  });
}

function startConnectionCheck() {
  if (connectionCheckInterval) return;

  let checkCount = 0;
  const maxChecks = 30; // Check for 15 seconds (every 500ms)

  connectionCheckInterval = setInterval(async () => {
    checkCount++;

    // Try callback-based method
    const status = await checkConnectionWithCallback();

    if (status?.connected && !isConnected) {
      console.log('[CarPlay] Connection detected via callback!');
      isConnected = true;
      stopConnectionCheck();
      if (pendingOnSelect) {
        setupTemplates(pendingBriefings, pendingOnSelect);
      }
    }

    if (checkCount >= maxChecks || isConnected) {
      stopConnectionCheck();
    }
  }, 500);
}

function stopConnectionCheck() {
  if (connectionCheckInterval) {
    clearInterval(connectionCheckInterval);
    connectionCheckInterval = null;
  }
}

function setupTemplates(
  briefings: Briefing[],
  onSelectBriefing: (briefing: Briefing) => void
) {
  console.log('[CarPlay] Setting up templates with', briefings.length, 'briefings');

  try {
    // Create now playing template
    nowPlayingTemplate = new NowPlayingTemplate({
      albumArtistButtonEnabled: false,
      upNextButtonEnabled: false,
    });
    console.log('[CarPlay] Created NowPlayingTemplate');

    // Store briefings for lookup by index
    const displayedBriefings = briefings.slice(0, 10);

    // Create briefings list items (without onSelect - that's handled at template level)
    const briefingItems = displayedBriefings.map((briefing) => ({
      text: format(new Date(briefing.created_at), 'EEEE, MMM d'),
      detailText: formatDuration(briefing.duration_seconds),
    }));

    // If no briefings, show a message
    const items = briefingItems.length > 0 ? briefingItems : [
      {
        text: 'No briefings available',
        detailText: 'Generate a briefing from the app',
      },
    ];

    listTemplate = new ListTemplate({
      title: 'Morning Drive',
      sections: [
        {
          header: 'Recent Briefings',
          items: items,
        },
      ],
      tabTitle: 'Briefings',
      tabSystemItem: 'mostRecent',
      // Handle item selection at template level
      onItemSelect: async ({ index }: { index: number }) => {
        console.log('[CarPlay] Item selected at index:', index);
        const selectedBriefing = displayedBriefings[index];
        if (selectedBriefing) {
          try {
            console.log('[CarPlay] Playing briefing:', selectedBriefing.id);
            onSelectBriefing(selectedBriefing);
            await loadBriefing(selectedBriefing);
            await play();
            // Show now playing
            if (nowPlayingTemplate) {
              CarPlay.pushTemplate(nowPlayingTemplate, true);
            }
          } catch (error) {
            console.error('[CarPlay] Failed to play briefing:', error);
          }
        }
      },
    });
    console.log('[CarPlay] Created ListTemplate');

    // Set root template
    console.log('[CarPlay] Setting root template...');
    CarPlay.setRootTemplate(listTemplate, false);
    console.log('[CarPlay] Root template set successfully');
  } catch (error) {
    console.error('[CarPlay] Error setting up templates:', error);
  }
}

export function updateBriefingsList(
  briefings: Briefing[],
  onSelectBriefing: (briefing: Briefing) => void
) {
  // Always update pending data
  pendingBriefings = briefings;
  pendingOnSelect = onSelectBriefing;

  console.log('[CarPlay] updateBriefingsList called, isConnected:', isConnected);
  if (isConnected) {
    setupTemplates(briefings, onSelectBriefing);
  }
}

export function showNowPlaying() {
  if (isConnected && nowPlayingTemplate) {
    CarPlay.pushTemplate(nowPlayingTemplate, true);
  }
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}
