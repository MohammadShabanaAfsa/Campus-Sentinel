"""Daily, camera-scoped crossing ledger and atomic totals (no per-frame I/O)."""
from functools import lru_cache
import json
from collections import defaultdict
from sqlalchemy import create_engine, text


async def ensure_vehicle_schema():
    from pathlib import Path
    from app.db.database import engine
    sql=(Path(__file__).resolve().parents[2] / 'migrations/001_vehicle_daily_counts.sql').read_text()
    async with engine.begin() as connection:
        for statement in sql.split(';'):
            if statement.strip():await connection.execute(text(statement))


class VehicleCountStore:
    def __init__(self, engine, outbox=None):
        self.engine = engine
        self.outbox = outbox

    @staticmethod
    def _key(camera_id):return f'vehicle_crossing_outbox:{camera_id}'

    def load(self, camera_id, day):
        if self.outbox is not None:
            groups=defaultdict(list)
            for eid,value in self.outbox.hgetall(self._key(camera_id)).items():
                stored_day,direction=json.loads(value)
                groups[stored_day].append((eid.decode() if isinstance(eid,bytes) else eid,direction))
            for stored_day,events in groups.items():self.record(camera_id,stored_day,events)
        with self.engine.connect() as connection:
            return self._load(connection, camera_id, day)

    @staticmethod
    def _load(connection, camera_id, day):
        row = connection.execute(text('SELECT in_count,out_count FROM vehicle_daily_counts '
                                      'WHERE camera_id=:camera AND count_date=:day'),
                                 {'camera': str(camera_id), 'day': day}).first()
        return (row[0], row[1]) if row else (0, 0)

    def record(self, camera_id, day, events):
        if self.outbox is not None and events:
            self.outbox.hset(self._key(camera_id),mapping={eid:json.dumps([str(day),direction]) for eid,direction in events})
        result=self._record_database(camera_id,day,events)
        if self.outbox is not None and events:self.outbox.hdel(self._key(camera_id),*[eid for eid,_ in events])
        return result

    def _record_database(self, camera_id, day, events):
        with self.engine.begin() as connection:
            for event_id, direction in events:
                params = {'camera': str(camera_id), 'day': day, 'id': event_id,
                          'direction': direction, 'inc': int(direction == 'in'),
                          'out': int(direction == 'out')}
                inserted = connection.execute(text('INSERT INTO vehicle_crossings '
                    '(event_id,camera_id,count_date,direction) VALUES (:id,:camera,:day,:direction) '
                    'ON CONFLICT (event_id) DO NOTHING RETURNING event_id'), params).first()
                if inserted:
                    connection.execute(text('INSERT INTO vehicle_daily_counts '
                        '(camera_id,count_date,in_count,out_count,total_count,updated_at) '
                        'VALUES (:camera,:day,:inc,:out,1,CURRENT_TIMESTAMP) '
                        'ON CONFLICT (camera_id,count_date) DO UPDATE SET '
                        'in_count=vehicle_daily_counts.in_count+:inc, '
                        'out_count=vehicle_daily_counts.out_count+:out, '
                        'total_count=vehicle_daily_counts.total_count+1, updated_at=CURRENT_TIMESTAMP'), params)
            return self._load(connection, camera_id, day)


@lru_cache(maxsize=1)
def get_vehicle_count_store():
    from app.core.config import settings
    import redis
    return VehicleCountStore(create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True),redis.Redis.from_url(settings.REDIS_URL))
