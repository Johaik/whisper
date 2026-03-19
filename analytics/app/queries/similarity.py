from sqlalchemy import text

class SemanticSimilarityQuery:
    def __init__(self, session):
        self.session = session

    def search(self, embedding, limit=5):
        """Perform a semantic similarity search using PGVector cosine distance."""
        # PGVector cosine distance operator: <=>
        # Lower distance means higher similarity
        query = text("""
            SELECT 
                r.id,
                r.phone_number,
                t.text,
                t.embedding <=> :embedding as distance
            FROM transcripts t
            JOIN recordings r ON t.recording_id = r.id
            WHERE t.embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT :limit
        """)
        
        result = self.session.execute(query, {
            "embedding": str(embedding), # PGVector expects a string format or specific array type
            "limit": limit
        })
        
        rows = result.all()
        
        output = []
        for row in rows:
            if hasattr(row, "_mapping"):
                output.append(dict(row._mapping))
            else:
                output.append(dict(row))
                
        return output
