from sqlalchemy import text

class CallerIntelligenceQuery:
    def __init__(self, session):
        self.session = session

    def get_by_phone(self, phone_number):
        """Get analytics summary for a specific phone number."""
        query = text("""
            SELECT 
                phone_number,
                total_calls,
                avg_duration,
                last_call_at
            FROM caller_intelligence_mv
            WHERE phone_number = :phone_number
        """)
        
        result = self.session.execute(query, {"phone_number": phone_number})
        row = result.first()
        
        if not row:
            return None
            
        # Handle both tuple-like and dict-like rows from SQLAlchemy
        if hasattr(row, "_mapping"):
            return dict(row._mapping)
        return dict(row)
