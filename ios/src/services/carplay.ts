/**
 * CarPlay integration service
 */

import CarPlay, {
  ListTemplate,
  NowPlayingTemplate,
} from 'react-native-carplay';
import { format } from 'date-fns';
import { Briefing } from '../types';
import { loadBriefing, play, pause, skipForward, skipBackward } from './audio';

let isConnected = false;
let nowPlayingTemplate: NowPlayingTemplate | null = null;
let listTemplate: ListTemplate | null = null;

export function setupCarPlay(
  briefings: Briefing[],
  onSelectBriefing: (briefing: Briefing) => void
) {
  // Handle CarPlay connection
  CarPlay.registerOnConnect(() => {
    console.log('CarPlay connected');
    isConnected = true;
    setupTemplates(briefings, onSelectBriefing);
  });

  CarPlay.registerOnDisconnect(() => {
    console.log('CarPlay disconnected');
    isConnected = false;
    nowPlayingTemplate = null;
    listTemplate = null;
  });
}

function setupTemplates(
  briefings: Briefing[],
  onSelectBriefing: (briefing: Briefing) => void
) {
  // Create now playing template
  nowPlayingTemplate = new NowPlayingTemplate({
    albumArtistButtonEnabled: false,
    upNextButtonEnabled: false,
  });

  // Create briefings list template
  const briefingItems = briefings.slice(0, 10).map((briefing) => ({
    text: format(new Date(briefing.created_at), 'EEEE, MMM d'),
    detailText: formatDuration(briefing.duration_seconds),
    onSelect: async () => {
      onSelectBriefing(briefing);
      await loadBriefing(briefing);
      await play();
      // Show now playing
      if (nowPlayingTemplate) {
        CarPlay.pushTemplate(nowPlayingTemplate, true);
      }
    },
  }));

  listTemplate = new ListTemplate({
    title: 'Morning Drive',
    sections: [
      {
        header: 'Recent Briefings',
        items: briefingItems,
      },
    ],
    tabTitle: 'Briefings',
    tabSystemItem: 'mostRecent',
  });

  // Set root template
  CarPlay.setRootTemplate(listTemplate, false);
}

export function updateBriefingsList(
  briefings: Briefing[],
  onSelectBriefing: (briefing: Briefing) => void
) {
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
