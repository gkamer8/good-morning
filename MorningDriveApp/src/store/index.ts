/**
 * Global state management using Zustand
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Briefing, BriefingSegment, UserSettings, Schedule } from '../types';

// === Auth Store ===

interface AuthState {
  isAuthenticated: boolean;
  isInitialized: boolean;
  userId: number | null;
  displayName: string | null;
  setAuthenticated: (authenticated: boolean) => void;
  setInitialized: (initialized: boolean) => void;
  setUser: (userId: number | null, displayName: string | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  isAuthenticated: false,
  isInitialized: false,
  userId: null,
  displayName: null,
  setAuthenticated: (isAuthenticated) => set({ isAuthenticated }),
  setInitialized: (isInitialized) => set({ isInitialized }),
  setUser: (userId, displayName) => set({ userId, displayName }),
  logout: () =>
    set({
      isAuthenticated: false,
      userId: null,
      displayName: null,
    }),
}));

// === Settings Store ===

interface SettingsState {
  settings: UserSettings | null;
  schedule: Schedule | null;
  isLoading: boolean;
  error: string | null;
  setSettings: (settings: UserSettings) => void;
  setSchedule: (schedule: Schedule) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      settings: null,
      schedule: null,
      isLoading: false,
      error: null,
      setSettings: (settings) => set({ settings }),
      setSchedule: (schedule) => set({ schedule }),
      setLoading: (isLoading) => set({ isLoading }),
      setError: (error) => set({ error }),
    }),
    {
      name: 'settings-storage',
      storage: createJSONStorage(() => AsyncStorage),
    }
  )
);

// === Briefings Store ===

interface BriefingsState {
  briefings: Briefing[];
  currentBriefing: Briefing | null;
  currentSegment: BriefingSegment | null;
  isGenerating: boolean;
  generatingBriefingId: number | null;  // Track WHICH briefing is generating
  generationProgress: number;
  generationStep: string | null;
  setBriefings: (briefings: Briefing[]) => void;
  addBriefing: (briefing: Briefing) => void;
  removeBriefing: (id: number) => void;
  setCurrentBriefing: (briefing: Briefing | null) => void;
  setCurrentSegment: (segment: BriefingSegment | null) => void;
  setGenerating: (isGenerating: boolean) => void;
  startGeneration: (briefingId: number) => void;  // Start generation with specific ID
  stopGeneration: () => void;  // Stop generation and clear ID
  setGenerationProgress: (progress: number, step: string | null) => void;
}

export const useBriefingsStore = create<BriefingsState>()(
  persist(
    (set) => ({
      briefings: [],
      currentBriefing: null,
      currentSegment: null,
      isGenerating: false,
      generatingBriefingId: null,
      generationProgress: 0,
      generationStep: null,
      setBriefings: (briefings) => set({ briefings }),
      addBriefing: (briefing) =>
        set((state) => ({
          briefings: [briefing, ...state.briefings],
        })),
      removeBriefing: (id) =>
        set((state) => ({
          briefings: state.briefings.filter((b) => b.id !== id),
        })),
      setCurrentBriefing: (currentBriefing) => set({ currentBriefing }),
      setCurrentSegment: (currentSegment) => set({ currentSegment }),
      setGenerating: (isGenerating) =>
        set({
          isGenerating,
          generationProgress: isGenerating ? 0 : 0,
          generationStep: isGenerating ? 'Starting...' : null,
        }),
      startGeneration: (briefingId) =>
        set({
          isGenerating: true,
          generatingBriefingId: briefingId,
          generationProgress: 0,
          generationStep: 'Starting...',
        }),
      stopGeneration: () =>
        set({
          isGenerating: false,
          generatingBriefingId: null,
          generationProgress: 0,
          generationStep: null,
        }),
      setGenerationProgress: (generationProgress, generationStep) =>
        set({ generationProgress, generationStep }),
    }),
    {
      name: 'briefings-storage',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        briefings: state.briefings.slice(0, 20), // Only cache last 20
        currentBriefing: state.currentBriefing,
      }),
    }
  )
);

// === App Config Store ===

interface AppConfigState {
  serverUrl: string;
  isConnected: boolean;
  lastSyncTime: string | null;
  _hasHydrated: boolean;
  setServerUrl: (url: string) => void;
  setConnected: (connected: boolean) => void;
  setLastSyncTime: (time: string | null) => void;
  setHasHydrated: (hasHydrated: boolean) => void;
}

export const useAppConfigStore = create<AppConfigState>()(
  persist(
    (set) => ({
      serverUrl: 'https://morning.g0rdon.com',
      isConnected: false,
      lastSyncTime: null,
      _hasHydrated: false,
      setServerUrl: (serverUrl) => set({ serverUrl }),
      setConnected: (isConnected) => set({ isConnected }),
      setLastSyncTime: (lastSyncTime) => set({ lastSyncTime }),
      setHasHydrated: (_hasHydrated) => set({ _hasHydrated }),
    }),
    {
      name: 'app-config-storage',
      storage: createJSONStorage(() => AsyncStorage),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);
