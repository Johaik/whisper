import pytest
from unittest.mock import MagicMock
from analytics.app.queries.similarity import SemanticSimilarityQuery

def test_semantic_similarity_logic():
    """Verify that the similarity query uses vector distance in SQL."""
    mock_session = MagicMock()
    
    # Mock result
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"id": 1, "text": "Similar transcript", "distance": 0.1}
    mock_result.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_result
    
    query = SemanticSimilarityQuery(mock_session)
    embedding = [0.1] * 1536
    result = query.search(embedding, limit=5)
    
    assert len(result) == 1
    assert result[0]["distance"] == 0.1
    
    # Check if the query contains the vector distance operator <=> (for cosine distance)
    # or <-> (for L2 distance). PGVector uses <=> for cosine similarity.
    call_args = mock_session.execute.call_args
    query_str = str(call_args[0][0])
    assert "<=>" in query_str or "<->" in query_str
