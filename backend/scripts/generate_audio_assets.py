#!/usr/bin/env python3
"""Generate audio assets for Morning Drive - jingles, transitions, etc."""

import numpy as np
from pydub import AudioSegment
from pydub.generators import Sine, Square
from pathlib import Path
import os

# Output directory
ASSETS_DIR = Path(__file__).parent.parent / "assets" / "audio"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def generate_tone(frequency: float, duration_ms: int, volume: float = 0.5) -> AudioSegment:
    """Generate a pure sine wave tone."""
    sine_wave = Sine(frequency)
    tone = sine_wave.to_audio_segment(duration=duration_ms)
    tone = tone - (20 * (1 - volume))  # Adjust volume
    return tone


def generate_chord(frequencies: list[float], duration_ms: int, volume: float = 0.5) -> AudioSegment:
    """Generate a chord by layering multiple frequencies."""
    tones = [generate_tone(f, duration_ms, volume / len(frequencies)) for f in frequencies]
    chord = tones[0]
    for tone in tones[1:]:
        chord = chord.overlay(tone)
    return chord


def apply_envelope(audio: AudioSegment, attack_ms: int = 50, release_ms: int = 100) -> AudioSegment:
    """Apply attack and release envelope."""
    audio = audio.fade_in(attack_ms).fade_out(release_ms)
    return audio


def generate_intro_jingle():
    """Generate an upbeat morning intro jingle."""
    print("Generating intro jingle...")

    # Musical notes (Hz) - C major scale ascending with energy
    C4, E4, G4 = 261.63, 329.63, 392.00
    C5, E5, G5 = 523.25, 659.25, 783.99
    A4 = 440.00

    # Create an energetic ascending pattern
    # Pattern: C-E-G (arpeggio up) then resolve to C5 chord
    notes = [
        (C4, 150),  # Quick notes
        (E4, 150),
        (G4, 150),
        (C5, 200),
        (E5, 150),
        (G5, 300),  # Longer high note
    ]

    jingle = AudioSegment.silent(duration=50)  # Small silence at start

    for freq, duration in notes:
        tone = generate_tone(freq, duration, 0.4)
        tone = apply_envelope(tone, 20, 40)
        jingle += tone
        jingle += AudioSegment.silent(duration=30)  # Gap between notes

    # Add a final chord
    final_chord = generate_chord([C5, E5, G5], 600, 0.3)
    final_chord = apply_envelope(final_chord, 50, 200)
    jingle += final_chord

    # Add subtle bass undertone
    bass = generate_tone(C4 / 2, len(jingle), 0.15)
    bass = bass.fade_in(100).fade_out(300)
    jingle = jingle.overlay(bass)

    # Normalize and export
    jingle = jingle.normalize()
    jingle.export(ASSETS_DIR / "intro_jingle.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'intro_jingle.mp3'} ({len(jingle)}ms)")


def generate_outro_jingle():
    """Generate a pleasant outro jingle."""
    print("Generating outro jingle...")

    # Descending pattern - wrapping up
    C5, G4, E4, C4 = 523.25, 392.00, 329.63, 261.63
    A4, F4 = 440.00, 349.23

    notes = [
        (C5, 200),
        (G4, 200),
        (E4, 200),
        (C4, 400),  # Longer final note
    ]

    jingle = AudioSegment.silent(duration=50)

    for freq, duration in notes:
        tone = generate_tone(freq, duration, 0.35)
        tone = apply_envelope(tone, 30, 80)
        jingle += tone
        jingle += AudioSegment.silent(duration=50)

    # Final resolution chord (C major)
    final_chord = generate_chord([C4, E4, G4], 800, 0.25)
    final_chord = apply_envelope(final_chord, 100, 400)
    jingle += final_chord

    jingle = jingle.normalize()
    jingle.export(ASSETS_DIR / "outro_jingle.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'outro_jingle.mp3'} ({len(jingle)}ms)")


def generate_transition_whoosh():
    """Generate a quick transition sound (whoosh/sweep)."""
    print("Generating transition whoosh...")

    duration_ms = 400
    sample_rate = 44100
    samples = int(duration_ms * sample_rate / 1000)

    # Create frequency sweep (low to high)
    t = np.linspace(0, duration_ms / 1000, samples)
    freq_start, freq_end = 200, 2000
    frequencies = np.exp(np.linspace(np.log(freq_start), np.log(freq_end), samples))

    # Generate the sweep
    phase = np.cumsum(2 * np.pi * frequencies / sample_rate)
    wave = np.sin(phase)

    # Apply envelope
    envelope = np.sin(np.linspace(0, np.pi, samples))  # Smooth in/out
    wave = wave * envelope * 0.3

    # Convert to audio
    wave_int = (wave * 32767).astype(np.int16)
    audio = AudioSegment(
        wave_int.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1
    )

    audio = audio.normalize()
    audio.export(ASSETS_DIR / "transition_whoosh.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'transition_whoosh.mp3'} ({len(audio)}ms)")


def generate_transition_chime():
    """Generate a subtle chime for section transitions."""
    print("Generating transition chime...")

    # Two-note chime
    G5, C6 = 783.99, 1046.50

    chime1 = generate_tone(G5, 200, 0.25)
    chime1 = apply_envelope(chime1, 10, 150)

    chime2 = generate_tone(C6, 350, 0.2)
    chime2 = apply_envelope(chime2, 10, 250)

    chime = chime1
    chime += AudioSegment.silent(duration=50)
    chime += chime2

    chime = chime.normalize()
    chime.export(ASSETS_DIR / "transition_chime.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'transition_chime.mp3'} ({len(chime)}ms)")


def generate_news_sting():
    """Generate a news segment intro sting."""
    print("Generating news sting...")

    # Urgent, attention-grabbing
    E5, G5, B5 = 659.25, 783.99, 987.77
    E4 = 329.63

    # Quick ascending triplet
    sting = AudioSegment.silent(duration=20)

    for freq in [E4, G5, B5]:
        tone = generate_tone(freq, 100, 0.35)
        tone = apply_envelope(tone, 10, 30)
        sting += tone

    # Final hit
    hit = generate_chord([E4, E5, B5], 300, 0.3)
    hit = apply_envelope(hit, 20, 150)
    sting += hit

    sting = sting.normalize()
    sting.export(ASSETS_DIR / "news_sting.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'news_sting.mp3'} ({len(sting)}ms)")


def generate_sports_sting():
    """Generate an energetic sports segment sting."""
    print("Generating sports sting...")

    # Energetic, triumphant
    C4, E4, G4 = 261.63, 329.63, 392.00
    C5 = 523.25

    sting = AudioSegment.silent(duration=20)

    # Power chord hits
    chord1 = generate_chord([C4, G4, C5], 150, 0.35)
    chord1 = apply_envelope(chord1, 10, 50)

    chord2 = generate_chord([E4, G4, C5], 150, 0.35)
    chord2 = apply_envelope(chord2, 10, 50)

    final = generate_chord([C4, E4, G4, C5], 400, 0.3)
    final = apply_envelope(final, 20, 200)

    sting += chord1
    sting += AudioSegment.silent(duration=50)
    sting += chord2
    sting += AudioSegment.silent(duration=50)
    sting += final

    sting = sting.normalize()
    sting.export(ASSETS_DIR / "sports_sting.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'sports_sting.mp3'} ({len(sting)}ms)")


def generate_weather_sting():
    """Generate a pleasant weather segment sting."""
    print("Generating weather sting...")

    # Light, airy
    C5, E5, G5 = 523.25, 659.25, 783.99
    A5 = 880.00

    sting = AudioSegment.silent(duration=20)

    # Gentle ascending
    for freq in [C5, E5, G5]:
        tone = generate_tone(freq, 150, 0.25)
        tone = apply_envelope(tone, 30, 80)
        sting += tone
        sting += AudioSegment.silent(duration=30)

    # Resolve
    resolve = generate_chord([C5, E5, G5], 350, 0.2)
    resolve = apply_envelope(resolve, 50, 200)
    sting += resolve

    sting = sting.normalize()
    sting.export(ASSETS_DIR / "weather_sting.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'weather_sting.mp3'} ({len(sting)}ms)")


def generate_fun_sting():
    """Generate a playful fun segment sting."""
    print("Generating fun sting...")

    # Playful, quirky
    C5, D5, E5, G5 = 523.25, 587.33, 659.25, 783.99

    sting = AudioSegment.silent(duration=20)

    # Bouncy pattern
    notes = [(C5, 80), (E5, 80), (G5, 80), (E5, 80), (G5, 200)]

    for freq, duration in notes:
        tone = generate_tone(freq, duration, 0.3)
        tone = apply_envelope(tone, 10, 30)
        sting += tone
        sting += AudioSegment.silent(duration=20)

    sting = sting.normalize()
    sting.export(ASSETS_DIR / "fun_sting.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'fun_sting.mp3'} ({len(sting)}ms)")


def generate_market_sting():
    """Generate a finance/market segment sting."""
    print("Generating market sting...")

    # Professional, subtle
    D4, F4, A4 = 293.66, 349.23, 440.00
    D5 = 587.33

    sting = AudioSegment.silent(duration=20)

    # Subtle two-chord progression
    chord1 = generate_chord([D4, A4, D5], 200, 0.25)
    chord1 = apply_envelope(chord1, 30, 100)

    chord2 = generate_chord([F4, A4, D5], 350, 0.2)
    chord2 = apply_envelope(chord2, 30, 200)

    sting += chord1
    sting += AudioSegment.silent(duration=50)
    sting += chord2

    sting = sting.normalize()
    sting.export(ASSETS_DIR / "market_sting.mp3", format="mp3")
    print(f"  Saved: {ASSETS_DIR / 'market_sting.mp3'} ({len(sting)}ms)")


def main():
    print("=" * 50)
    print("Morning Drive Audio Asset Generator")
    print("=" * 50)
    print(f"Output directory: {ASSETS_DIR}")
    print()

    generate_intro_jingle()
    generate_outro_jingle()
    generate_transition_whoosh()
    generate_transition_chime()
    generate_news_sting()
    generate_sports_sting()
    generate_weather_sting()
    generate_fun_sting()
    generate_market_sting()

    print()
    print("=" * 50)
    print("All audio assets generated successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
