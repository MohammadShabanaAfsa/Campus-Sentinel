"""Apply the additive daily vehicle count migration. Run before starting backend."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DEBUG'] = 'false'
from app.core.config import settings
from sqlalchemy import create_engine

if __name__ == '__main__':
    engine = create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.begin() as connection:
            for statement in (ROOT / 'backend/migrations/001_vehicle_daily_counts.sql').read_text().split(';'):
                if statement.strip():
                    connection.exec_driver_sql(statement)
        print('Daily vehicle count migration applied.')
    finally:
        engine.dispose()
