import pytest
from unittest.mock import MagicMock
from analytics.app.queries.caller_intel import CallerIntelligenceQuery

def test_caller_intelligence_logic():
    """Verify the caller intelligence query logic."""
    # Mock the database session
    mock_session = MagicMock()
    
    # Mock the return value of the query
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"phone_number": "123456789", "total_calls": 5, "avg_duration": 120.0, "last_call_at": "2026-03-19T10:00:00"}
    mock_result.first.return_value = mock_row
    mock_session.execute.return_value = mock_result
    
    query = CallerIntelligenceQuery(mock_session)
    result = query.get_by_phone("123456789")
    
    assert result["total_calls"] == 5
    assert result["avg_duration"] == 120.0
    mock_session.execute.assert_called_once()

def test_caller_intelligence_not_found():
    """Verify behavior when caller is not found."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    query = CallerIntelligenceQuery(mock_session)
    result = query.get_by_phone("non-existent")
    
    assert result is None
