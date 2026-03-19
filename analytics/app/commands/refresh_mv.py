from sqlalchemy import text

class MaterializedViewRefreshCommand:
    @staticmethod
    def refresh_caller_intelligence(session):
        # First, ensure the MV exists
        session.execute(text("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS caller_intelligence_mv AS
            SELECT 
                phone_number,
                COUNT(*) as total_calls,
                AVG(duration_sec) as avg_duration,
                MAX(created_at) as last_call_at
            FROM recordings
            WHERE phone_number IS NOT NULL
            GROUP BY phone_number
        """))
        session.execute(text("REFRESH MATERIALIZED VIEW caller_intelligence_mv"))
        session.commit()

    @staticmethod
    def refresh_system_bottlenecks(session):
        session.execute(text("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS system_bottleneck_mv AS
            SELECT 
                model_name,
                AVG(duration_sec) as avg_duration,
                COUNT(*) as total_processed
            FROM recordings r
            JOIN transcripts t ON r.id = t.recording_id
            GROUP BY model_name
        """))
        session.execute(text("REFRESH MATERIALIZED VIEW system_bottleneck_mv"))
        session.commit()
