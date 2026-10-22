"""Bounded native health probe for the configured PostgreSQL and Redis services."""
import os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.chdir(root/'backend');sys.path.insert(0,str(root/'backend'));os.environ.pop('DEBUG',None)
from app.core.config import settings
from sqlalchemy import create_engine,text
import redis
try:
    engine=create_engine(settings.SYNC_DATABASE_URL,connect_args={'connect_timeout':3,'options':'-c statement_timeout=3000'})
    with engine.connect() as connection:
        assert connection.execute(text('SELECT 1')).scalar()==1
    engine.dispose()
    assert redis.from_url(settings.REDIS_URL,socket_connect_timeout=3,socket_timeout=3).ping()
except Exception:
    sys.exit(1)
