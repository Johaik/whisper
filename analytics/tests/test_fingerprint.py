import pytest
from analytics.app.commands.fingerprint import GenerateFingerprintCommand

def test_calculate_wpm():
    """Verify WPM calculation logic."""
    # 100 words in 60 seconds = 100 WPM
    segments = [{"text": "word " * 100, "start": 0, "end": 60}]
    wpm = GenerateFingerprintCommand.calculate_wpm(segments)
    assert wpm == 100.0

def test_calculate_turn_velocity():
    """Verify turn velocity calculation (turns per minute)."""
    # 10 turns in 2 minutes = 5 turns per minute
    # A turn is a change in speaker
    segments = [
        {"speaker": "A", "start": 0, "end": 10},
        {"speaker": "B", "start": 10, "end": 20},
        {"speaker": "A", "start": 20, "end": 30},
        {"speaker": "B", "start": 30, "end": 40},
        {"speaker": "A", "start": 40, "end": 50},
        {"speaker": "B", "start": 50, "end": 60},
        {"speaker": "A", "start": 60, "end": 70},
        {"speaker": "B", "start": 70, "end": 80},
        {"speaker": "A", "start": 80, "end": 90},
        {"speaker": "B", "start": 90, "end": 100},
    ]
    velocity = GenerateFingerprintCommand.calculate_turn_velocity(segments, duration=120)
    assert velocity == 5.0

def test_calculate_overlap_ratio():
    """Verify overlap ratio calculation."""
    # 20 seconds of overlap in 100 second call = 0.2 ratio
    segments = [
        {"start": 0, "end": 50},
        {"start": 40, "end": 60}, # 10s overlap with prev
    ]
    # Overlap is when two segments exist at the same time
    # This is a simplified test case
    ratio = GenerateFingerprintCommand.calculate_overlap_ratio(segments, duration=100)
    assert ratio == 0.1
