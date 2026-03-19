import pytest
from unittest.mock import MagicMock
from analytics.app.queries.bottlenecks import GetSystemBottlenecksQuery

def test_system_bottlenecks_logic():
    """Verify the system bottlenecks query logic."""
    mock_session = MagicMock()
    
    # Mock the return value
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"model_name": "large-v3", "avg_duration": 45.0, "total_processed": 100}
    mock_result.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_result
    
    query = GetSystemBottlenecksQuery(mock_session)
    result = query.get_all()
    
    assert len(result) == 1
    assert result[0]["model_name"] == "large-v3"
    mock_session.execute.assert_called_once()
