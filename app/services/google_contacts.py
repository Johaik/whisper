"""Google Contacts integration using People API."""

import logging
import re
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings

logger = logging.getLogger(__name__)

# Scopes required for reading contacts
SCOPES = ['https://www.googleapis.com/auth/contacts.readonly']


class GoogleContactsService:
    """Service for looking up contact names from phone numbers."""

    def __init__(self):
        """Initialize the Google Contacts service."""
        self._service = None
        self._contacts_cache: dict[str, Optional[str]] = {}
        self._all_contacts_loaded = False

    def _get_credentials(self) -> Optional[Credentials]:
        """Get valid OAuth credentials."""
        if not self.is_configured():
            logger.warning("Google API credentials not configured")
            return None

        settings = get_settings()

        try:
            creds = Credentials(
                token=None,
                refresh_token=settings.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=SCOPES,
            )

            # Refresh the token
            if not creds.valid:
                creds.refresh(Request())

            return creds

        except Exception as e:
            logger.error(f"Failed to get Google credentials: {e}")
            return None

    def _get_service(self):
        """Get or create the People API service."""
        if self._service is None:
            creds = self._get_credentials()
            if creds:
                self._service = build('people', 'v1', credentials=creds)
        return self._service

    def _normalize_phone_for_comparison(self, phone: str) -> str:
        """Normalize phone number for comparison."""
        # Remove all non-digits
        digits = re.sub(r'\D', '', phone)
        # Return last 9 digits for comparison (handles country code variations)
        return digits[-9:] if len(digits) >= 9 else digits

    def _load_all_contacts(self) -> None:
        """Load all contacts into cache for efficient lookups."""
        if self._all_contacts_loaded:
            return

        service = self._get_service()
        if not service:
            return

        try:
            logger.info("Loading all contacts from Google...")
            page_token = None

            while True:
                results = service.people().connections().list(
                    resourceName='people/me',
                    pageSize=1000,
                    personFields='names,phoneNumbers',
                    pageToken=page_token,
                ).execute()

                connections = results.get('connections', [])

                for person in connections:
                    names = person.get('names', [])
                    phones = person.get('phoneNumbers', [])

                    if names and phones:
                        display_name = names[0].get('displayName', '')
                        for phone_entry in phones:
                            phone_value = phone_entry.get('value', '')
                            if phone_value:
                                normalized = self._normalize_phone_for_comparison(phone_value)
                                if normalized:
                                    self._contacts_cache[normalized] = display_name

                page_token = results.get('nextPageToken')
                if not page_token:
                    break

            self._all_contacts_loaded = True
            logger.info(f"Loaded {len(self._contacts_cache)} phone numbers from contacts")

        except HttpError as e:
            logger.error(f"Failed to load contacts: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading contacts: {e}")

    def lookup_contact_name(self, phone_number: str) -> Optional[str]:
        """
        Look up a contact name by phone number.

        Args:
            phone_number: Phone number to look up

        Returns:
            Contact name if found, None otherwise
        """
        if not phone_number:
            return None

        # Load all contacts on first lookup
        self._load_all_contacts()

        # Normalize the input phone for comparison
        normalized = self._normalize_phone_for_comparison(phone_number)

        if not normalized:
            return None

        # Try exact match first
        if normalized in self._contacts_cache:
            return self._contacts_cache[normalized]

        # Try with fewer digits for shorter numbers
        for length in [8, 7, 6]:
            if len(normalized) >= length:
                short = normalized[-length:]
                for cached_phone, name in self._contacts_cache.items():
                    if cached_phone.endswith(short):
                        return name

        return None

    def is_configured(self) -> bool:
        """Check if Google Contacts is properly configured."""
        settings = get_settings()
        return all([
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_refresh_token,
        ])


# Singleton instance
_contacts_service: Optional[GoogleContactsService] = None


def get_contacts_service() -> GoogleContactsService:
    """Get the singleton contacts service instance."""
    global _contacts_service
    if _contacts_service is None:
        _contacts_service = GoogleContactsService()
    return _contacts_service


def lookup_caller_name(phone_number: str) -> Optional[str]:
    """
    Convenience function to look up a caller name.

    Args:
        phone_number: Phone number to look up

    Returns:
        Contact name if found and configured, None otherwise
    """
    service = get_contacts_service()
    if not service.is_configured():
        logger.debug("Google Contacts not configured, skipping lookup")
        return None

    return service.lookup_contact_name(phone_number)

