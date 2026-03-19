import pytest
from unittest.mock import MagicMock
from analytics.app.commands.embedding import GenerateEmbeddingCommand

def test_generate_embedding_logic():
    """Verify that the embedding generation logic calls the model and returns a vector."""
    # Mock the embedding model/client
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.1] * 1536
    
    text = "This is a test transcript."
    vector = GenerateEmbeddingCommand.generate(text, model=mock_model)
    
    assert len(vector) == 1536
    assert vector[0] == 0.1
    mock_model.encode.assert_called_once_with(text)

def test_generate_embedding_empty_text():
    """Verify that empty text returns an empty or null vector."""
    vector = GenerateEmbeddingCommand.generate("", model=None)
    assert vector is None
