from sqlalchemy import text

class GetSystemBottlenecksQuery:
    def __init__(self, session):
        self.session = session

    def get_all(self):
        """Get system bottleneck analytics from the materialized view."""
        query = text("""
            SELECT 
                model_name,
                avg_duration,
                total_processed
            FROM system_bottleneck_mv
        """)
        
        result = self.session.execute(query)
        rows = result.all()
        
        output = []
        for row in rows:
            if hasattr(row, "_mapping"):
                output.append(dict(row._mapping))
            else:
                output.append(dict(row))
                
        return output
