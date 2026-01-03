/**
 * Morning Drive - Entry Point
 * @format
 */

import { AppRegistry } from 'react-native';
import TrackPlayer from 'react-native-track-player';
import App from './src/App';
import { name as appName } from './app.json';
import { playbackService } from './src/services/audio';

// Register the app
AppRegistry.registerComponent(appName, () => App);

// Register the playback service for background audio
TrackPlayer.registerPlaybackService(() => playbackService);
