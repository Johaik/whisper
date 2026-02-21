"""Unit tests for the filename parser."""

from datetime import datetime

import pytest

from app.processors.filename_parser import (
    CallerMetadata,
    extract_datetime_from_filename,
    extract_phone_from_filename,
    normalize_phone_number,
    parse_recording_filename,
)


class TestParseRecordingFilename:
    """Tests for parse_recording_filename function."""

    def test_international_phone_format(self) -> None:
        """Parse international phone number with +."""
        filename = "Call recording +15551234567_200605_114902.m4a"
        result = parse_recording_filename(filename)

        assert result.phone_number == "+15551234567"
        assert result.raw_phone == "+15551234567"
        assert result.call_datetime == datetime(2020, 6, 5, 11, 49, 2)

    def test_local_phone_format(self) -> None:
        """Parse local phone number without country code."""
        filename = "Call recording 037111121_200827_141229.m4a"
        result = parse_recording_filename(filename)

        assert result.phone_number == "037111121"
        assert result.call_datetime == datetime(2020, 8, 27, 14, 12, 29)

    def test_extension_format(self) -> None:
        """Parse short extension/internal number."""
        filename = "Call recording _6900_190317_190817.m4a"
        result = parse_recording_filename(filename)

        assert result.phone_number == "6900"
        assert result.raw_phone == "_6900"
        assert result.call_datetime == datetime(2019, 3, 17, 19, 8, 17)

    def test_israeli_mobile_format(self) -> None:
        """Parse Israeli mobile number with country code."""
        filename = "Call recording +15559876543_211010_115919.m4a"
        result = parse_recording_filename(filename)

        assert result.phone_number == "+15559876543"
        assert result.call_datetime == datetime(2021, 10, 10, 11, 59, 19)

    def test_uppercase_extension(self) -> None:
        """Handle uppercase file extension."""
        filename = "Call recording +15551234567_200605_114902.M4A"
        result = parse_recording_filename(filename)

        assert result.phone_number == "+15551234567"

    def test_wav_extension(self) -> None:
        """Handle .wav extension."""
        filename = "Call recording 12345678_220101_120000.wav"
        result = parse_recording_filename(filename)

        assert result.phone_number == "12345678"
        assert result.call_datetime == datetime(2022, 1, 1, 12, 0, 0)

    def test_invalid_format_returns_empty(self) -> None:
        """Invalid filename format returns empty metadata."""
        filename = "random_audio_file.m4a"
        result = parse_recording_filename(filename)

        assert result.phone_number is None
        assert result.call_datetime is None

    def test_missing_date_returns_empty(self) -> None:
        """Filename without date returns empty metadata."""
        filename = "Call recording +15551234567.m4a"
        result = parse_recording_filename(filename)

        assert result.phone_number is None

    def test_only_phone_no_full_datetime(self) -> None:
        """Filename with incomplete datetime."""
        filename = "Call recording +15551234567_200605.m4a"
        result = parse_recording_filename(filename)

        # Pattern requires both date and time
        assert result.phone_number is None


class TestContactNameExtraction:
    """Tests for contact name extraction from filename."""

    def test_simple_contact_name(self) -> None:
        """Parse simple contact name."""
        filename = "Call recording John Doe_200605_114902.m4a"
        result = parse_recording_filename(filename)

        assert result.caller_name == "John Doe"
        assert result.phone_number is None
        assert result.raw_phone is None
        assert result.call_datetime == datetime(2020, 6, 5, 11, 49, 2)

    def test_hebrew_contact_name(self) -> None:
        """Parse Hebrew contact name."""
        filename = "Call recording ישראל ישראלי_200605_114902.m4a"
        result = parse_recording_filename(filename)

        assert result.caller_name == "ישראל ישראלי"
        assert result.phone_number is None
        assert result.call_datetime == datetime(2020, 6, 5, 11, 49, 2)

    def test_mixed_name_with_digits(self) -> None:
        """Parse name containing digits but not a phone number."""
        filename = "Call recording Mom 2_200605_114902.m4a"
        result = parse_recording_filename(filename)

        assert result.caller_name == "Mom 2"
        assert result.phone_number is None
        assert result.call_datetime == datetime(2020, 6, 5, 11, 49, 2)

    def test_mixed_identifier_looks_like_phone(self) -> None:
        """Identifier looking like phone is treated as phone."""
        # This confirms current behavior where dense digits override letters
        filename = "Call recording A1 5551234_200605_114902.m4a"
        result = parse_recording_filename(filename)

        # "A1 5551234" has 8 digits and 2 letters. 8/10 = 0.8 > 0.5.
        # It is treated as a phone number.
        assert result.phone_number == "15551234"
        assert result.caller_name is None

    def test_mixed_identifier_looks_like_name(self) -> None:
        """Identifier with many letters is treated as name."""
        filename = "Call recording Office 5551234_200605_114902.m4a"
        result = parse_recording_filename(filename)

        # "Office 5551234" has 7 digits and 6 letters + space. 7/14 = 0.5.
        # Not > 0.5, so it checks for letters -> True. Treated as name.
        assert result.caller_name == "Office 5551234"
        assert result.phone_number is None


class TestNormalizePhoneNumber:
    """Tests for phone number normalization."""

    def test_international_format(self) -> None:
        """Keep + for international numbers."""
        assert normalize_phone_number("+15551234567") == "+15551234567"

    def test_local_format(self) -> None:
        """Keep local format as-is."""
        assert normalize_phone_number("037111121") == "037111121"

    def test_underscore_prefix(self) -> None:
        """Remove underscore prefix."""
        assert normalize_phone_number("_6900") == "6900"

    def test_removes_non_digits(self) -> None:
        """Remove spaces and dashes."""
        assert normalize_phone_number("+1 (555) 123-4567") == "+15551234567"

    def test_too_short_returns_none(self) -> None:
        """Very short numbers return None."""
        assert normalize_phone_number("12") is None

    def test_empty_returns_none(self) -> None:
        """Empty string returns None."""
        assert normalize_phone_number("") is None

    def test_minimum_length(self) -> None:
        """3 digits is minimum."""
        assert normalize_phone_number("123") == "123"


class TestHelperFunctions:
    """Tests for convenience helper functions."""

    def test_extract_phone_from_filename(self) -> None:
        """Test phone extraction helper."""
        phone = extract_phone_from_filename(
            "Call recording +15551234567_200605_114902.m4a"
        )
        assert phone == "+15551234567"

    def test_extract_datetime_from_filename(self) -> None:
        """Test datetime extraction helper."""
        dt = extract_datetime_from_filename(
            "Call recording +15551234567_200605_114902.m4a"
        )
        assert dt == datetime(2020, 6, 5, 11, 49, 2)

    def test_extract_phone_invalid_filename(self) -> None:
        """Invalid filename returns None."""
        phone = extract_phone_from_filename("random.m4a")
        assert phone is None

    def test_extract_datetime_invalid_filename(self) -> None:
        """Invalid filename returns None."""
        dt = extract_datetime_from_filename("random.m4a")
        assert dt is None


class TestCallerMetadataDataclass:
    """Tests for CallerMetadata dataclass."""

    def test_default_values(self) -> None:
        """Default values are None."""
        metadata = CallerMetadata()
        assert metadata.phone_number is None
        assert metadata.call_datetime is None
        assert metadata.raw_phone is None

    def test_with_values(self) -> None:
        """Values can be set."""
        dt = datetime(2020, 1, 1, 12, 0, 0)
        metadata = CallerMetadata(
            phone_number="+1234567890",
            call_datetime=dt,
            raw_phone="+1 234 567 890",
        )
        assert metadata.phone_number == "+1234567890"
        assert metadata.call_datetime == dt
        assert metadata.raw_phone == "+1 234 567 890"
