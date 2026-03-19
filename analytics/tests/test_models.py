from sqlalchemy import inspect
from app.db.models import Enrichment

def test_enrichment_has_fingerprint_json():
    """Verify that the Enrichment model has the fingerprint_json column."""
    mapper = inspect(Enrichment)
    assert "fingerprint_json" in mapper.attrs
    
    # Check if it's JSONB
    column = mapper.attrs["fingerprint_json"].columns[0]
    from sqlalchemy.dialects.postgresql import JSONB
    assert isinstance(column.type, JSONB)

def test_transcript_has_embedding():
    """Verify that the Transcript model has the embedding column (PGVector)."""
    from app.db.models import Transcript
    mapper = inspect(Transcript)
    assert "embedding" in mapper.attrs
    
    # Check if it's Vector type
    column = mapper.attrs["embedding"].columns[0]
    # We expect Vector from pgvector.sqlalchemy
    assert column.type.__class__.__name__.lower() == "vector"
