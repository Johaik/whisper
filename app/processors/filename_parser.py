"""Parse caller metadata from recording filenames."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CallerMetadata:
    """Parsed caller metadata from filename."""

    phone_number: Optional[str] = None
    caller_name: Optional[str] = None  # Contact name if in filename
    call_datetime: Optional[datetime] = None
    raw_phone: Optional[str] = None  # Original phone string before normalization


def parse_recording_filename(filename: str) -> CallerMetadata:
    """
    Parse caller metadata from a recording filename.

    Expected formats:
    - 'Call recording +15551234567_200605_114902.m4a'
    - 'Call recording 037111121_200827_141229.m4a'
    - 'Call recording _6900_190317_190817.m4a'

    Pattern: 'Call recording <phone>_<YYMMDD>_<HHMMSS>.<ext>'

    Args:
        filename: The recording filename to parse

    Returns:
        CallerMetadata with extracted phone number and datetime
    """
    metadata = CallerMetadata()

    # Remove file extension
    name_without_ext = re.sub(r'\.[^.]+$', '', filename)

    # Pattern to match: Call recording <phone>_<date>_<time>
    # Phone can be: +international, local digits, or _shortcode
    pattern = r'Call recording\s+(.+?)_(\d{6})_(\d{6})$'
    match = re.match(pattern, name_without_ext, re.IGNORECASE)

    if not match:
        # Try alternative pattern without "Call recording" prefix
        alt_pattern = r'^(.+?)_(\d{6})_(\d{6})$'
        match = re.match(alt_pattern, name_without_ext)

    if match:
        identifier = match.group(1).strip()
        date_str = match.group(2)
        time_str = match.group(3)

        # Determine if identifier is a phone number or contact name
        # Phone numbers: start with +, _, or are mostly digits
        # Contact names: contain letters (any alphabet including Hebrew, emojis, etc.)
        if is_phone_number(identifier):
            metadata.raw_phone = identifier
            metadata.phone_number = normalize_phone_number(identifier)
        else:
            # It's a contact name from the phone's call log
            metadata.caller_name = identifier

        # Parse datetime (YYMMDD_HHMMSS)
        try:
            year = int(date_str[0:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            hour = int(time_str[0:2])
            minute = int(time_str[2:4])
            second = int(time_str[4:6])

            # Assume 2000s for 2-digit years
            full_year = 2000 + year if year < 100 else year

            metadata.call_datetime = datetime(
                year=full_year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=second,
            )
        except (ValueError, IndexError):
            # Invalid date/time format
            pass

    return metadata


def is_phone_number(identifier: str) -> bool:
    """
    Determine if an identifier looks like a phone number.

    Phone numbers:
    - Start with + (international)
    - Start with _ (extension)
    - Contain mostly digits (>50% digits)

    Contact names:
    - Contain letters (Latin, Hebrew, etc.)
    - Contain emojis or special characters

    Args:
        identifier: The string to check

    Returns:
        True if it looks like a phone number, False if it's a contact name
    """
    if not identifier:
        return False

    identifier = identifier.strip()

    # Phone indicators
    if identifier.startswith('+'):
        return True
    if identifier.startswith('_'):
        return True

    # Count digits vs total characters
    digits = sum(1 for c in identifier if c.isdigit())
    total = len(identifier)

    # If more than 50% digits and at least 3 digits, it's a phone number
    if total > 0 and digits >= 3 and (digits / total) > 0.5:
        return True

    # Check if it contains any letters (would indicate a name)
    # This includes Latin, Hebrew, Arabic, etc.
    has_letters = any(c.isalpha() for c in identifier)
    if has_letters:
        return False

    # Default: if it has digits, treat as phone
    return digits >= 3


def normalize_phone_number(raw_phone: str) -> Optional[str]:
    """
    Normalize a phone number string.

    Args:
        raw_phone: Raw phone string from filename

    Returns:
        Normalized phone number or None if invalid
    """
    if not raw_phone:
        return None

    # Remove common prefixes that might appear
    phone = raw_phone.strip()

    # Handle underscore prefix (e.g., "_6900" -> "6900")
    if phone.startswith('_'):
        phone = phone[1:]

    # Remove any non-digit characters except leading +
    if phone.startswith('+'):
        # International format: keep the +
        digits = '+' + re.sub(r'\D', '', phone[1:])
    else:
        digits = re.sub(r'\D', '', phone)

    # Validate: must have at least 3 digits
    digit_count = len(re.sub(r'\D', '', digits))
    if digit_count < 3:
        return None

    return digits if digits else None


def extract_phone_from_filename(filename: str) -> Optional[str]:
    """
    Quick helper to extract just the phone number from a filename.

    Args:
        filename: Recording filename

    Returns:
        Normalized phone number or None
    """
    metadata = parse_recording_filename(filename)
    return metadata.phone_number


def extract_datetime_from_filename(filename: str) -> Optional[datetime]:
    """
    Quick helper to extract just the datetime from a filename.

    Args:
        filename: Recording filename

    Returns:
        Parsed datetime or None
    """
    metadata = parse_recording_filename(filename)
    return metadata.call_datetime

