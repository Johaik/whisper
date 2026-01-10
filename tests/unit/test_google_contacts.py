"""Unit tests for the Google Contacts service."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.google_contacts import (
    GoogleContactsService,
    get_contacts_service,
    lookup_caller_name,
)


class TestGoogleContactsService:
    """Tests for GoogleContactsService class."""

    def test_is_configured_false_when_missing_credentials(self) -> None:
        """Returns False when credentials are not configured."""
        with patch("app.services.google_contacts.get_settings") as mock_settings:
            mock_settings.return_value.google_client_id = None
            mock_settings.return_value.google_client_secret = None
            mock_settings.return_value.google_refresh_token = None

            service = GoogleContactsService()
            assert service.is_configured() is False

    def test_is_configured_true_when_all_credentials_present(self) -> None:
        """Returns True when all credentials are configured."""
        with patch("app.services.google_contacts.get_settings") as mock_settings:
            mock_settings.return_value.google_client_id = "client_id"
            mock_settings.return_value.google_client_secret = "client_secret"
            mock_settings.return_value.google_refresh_token = "refresh_token"

            service = GoogleContactsService()
            assert service.is_configured() is True

    def test_is_configured_false_when_partial_credentials(self) -> None:
        """Returns False when only some credentials are present."""
        with patch("app.services.google_contacts.get_settings") as mock_settings:
            mock_settings.return_value.google_client_id = "client_id"
            mock_settings.return_value.google_client_secret = None
            mock_settings.return_value.google_refresh_token = "refresh_token"

            service = GoogleContactsService()
            assert service.is_configured() is False


class TestNormalizePhoneForComparison:
    """Tests for phone normalization in lookups."""

    def test_normalize_international_format(self) -> None:
        """International format normalized to digits."""
        service = GoogleContactsService()
        result = service._normalize_phone_for_comparison("+15551234567")
        assert result == "551234567"  # Last 9 digits

    def test_normalize_with_spaces_and_dashes(self) -> None:
        """Removes formatting characters."""
        service = GoogleContactsService()
        result = service._normalize_phone_for_comparison("+1 (555) 123-4567")
        assert result == "551234567"  # Last 9 digits

    def test_normalize_short_number(self) -> None:
        """Short numbers kept as-is."""
        service = GoogleContactsService()
        result = service._normalize_phone_for_comparison("6900")
        assert result == "6900"

    def test_normalize_local_format(self) -> None:
        """Local format normalized."""
        service = GoogleContactsService()
        result = service._normalize_phone_for_comparison("037111121")
        assert result == "037111121"


class TestLookupContactName:
    """Tests for contact lookup functionality."""

    def test_lookup_returns_none_when_not_loaded(self) -> None:
        """Returns None when contacts not loaded."""
        service = GoogleContactsService()
        # Don't load contacts, just check cache
        result = service._contacts_cache.get("551234567")
        assert result is None

    def test_lookup_with_cached_contact(self) -> None:
        """Returns name when contact is in cache."""
        service = GoogleContactsService()
        service._contacts_cache = {
            "551234567": "John Doe",
            "037111121": "Jane Smith",
        }
        service._all_contacts_loaded = True

        result = service.lookup_contact_name("+15551234567")
        assert result == "John Doe"

    def test_lookup_empty_phone_returns_none(self) -> None:
        """Empty phone number returns None."""
        service = GoogleContactsService()
        service._all_contacts_loaded = True

        result = service.lookup_contact_name("")
        assert result is None

    def test_lookup_none_phone_returns_none(self) -> None:
        """None phone number returns None."""
        service = GoogleContactsService()
        service._all_contacts_loaded = True

        result = service.lookup_contact_name(None)
        assert result is None

    def test_lookup_partial_match(self) -> None:
        """Finds contact with partial number match."""
        service = GoogleContactsService()
        service._contacts_cache = {
            "551234567": "John Doe",  # Stored with different prefix
        }
        service._all_contacts_loaded = True

        # Looking up with full international format
        result = service.lookup_contact_name("+15551234567")
        assert result == "John Doe"


class TestGetContactsService:
    """Tests for singleton service getter."""

    def test_returns_service_instance(self) -> None:
        """Returns a GoogleContactsService instance."""
        with patch("app.services.google_contacts._contacts_service", None):
            service = get_contacts_service()
            assert isinstance(service, GoogleContactsService)

    def test_returns_same_instance(self) -> None:
        """Returns the same instance on multiple calls."""
        with patch("app.services.google_contacts._contacts_service", None):
            service1 = get_contacts_service()
            service2 = get_contacts_service()
            assert service1 is service2


class TestLookupCallerName:
    """Tests for lookup_caller_name convenience function."""

    def test_returns_none_when_not_configured(self) -> None:
        """Returns None when Google Contacts not configured."""
        with patch("app.services.google_contacts.get_contacts_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_configured.return_value = False
            mock_get.return_value = mock_service

            result = lookup_caller_name("+15551234567")
            assert result is None
            mock_service.lookup_contact_name.assert_not_called()

    def test_calls_service_when_configured(self) -> None:
        """Calls service lookup when configured."""
        with patch("app.services.google_contacts.get_contacts_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_configured.return_value = True
            mock_service.lookup_contact_name.return_value = "John Doe"
            mock_get.return_value = mock_service

            result = lookup_caller_name("+15551234567")
            assert result == "John Doe"
            mock_service.lookup_contact_name.assert_called_once_with("+15551234567")


class TestLoadAllContacts:
    """Tests for loading contacts from API."""

    @patch("app.services.google_contacts.GoogleContactsService._get_service")
    def test_loads_contacts_into_cache(self, mock_get_service: MagicMock) -> None:
        """Loads contacts into cache from API."""
        # Mock API response
        mock_service = MagicMock()
        mock_service.people.return_value.connections.return_value.list.return_value.execute.return_value = {
            "connections": [
                {
                    "names": [{"displayName": "John Doe"}],
                    "phoneNumbers": [{"value": "+15551234567"}],
                },
                {
                    "names": [{"displayName": "Jane Smith"}],
                    "phoneNumbers": [{"value": "037111121"}],
                },
            ],
        }
        mock_get_service.return_value = mock_service

        service = GoogleContactsService()
        service._load_all_contacts()

        assert service._all_contacts_loaded is True
        assert len(service._contacts_cache) == 2

    @patch("app.services.google_contacts.GoogleContactsService._get_service")
    def test_handles_contacts_without_phone(self, mock_get_service: MagicMock) -> None:
        """Skips contacts without phone numbers."""
        mock_service = MagicMock()
        mock_service.people.return_value.connections.return_value.list.return_value.execute.return_value = {
            "connections": [
                {
                    "names": [{"displayName": "No Phone"}],
                    "phoneNumbers": [],
                },
                {
                    "names": [{"displayName": "Has Phone"}],
                    "phoneNumbers": [{"value": "+1234567890"}],
                },
            ],
        }
        mock_get_service.return_value = mock_service

        service = GoogleContactsService()
        service._load_all_contacts()

        assert len(service._contacts_cache) == 1

    @patch("app.services.google_contacts.GoogleContactsService._get_service")
    def test_handles_contacts_without_name(self, mock_get_service: MagicMock) -> None:
        """Skips contacts without names."""
        mock_service = MagicMock()
        mock_service.people.return_value.connections.return_value.list.return_value.execute.return_value = {
            "connections": [
                {
                    "names": [],
                    "phoneNumbers": [{"value": "+1234567890"}],
                },
            ],
        }
        mock_get_service.return_value = mock_service

        service = GoogleContactsService()
        service._load_all_contacts()

        assert len(service._contacts_cache) == 0

