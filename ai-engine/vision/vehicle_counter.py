"""Finite normalized line crossing counts owned by a camera stream session."""
import math
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from loguru import logger

VEHICLES={'car','motorcycle','bicycle','bus','truck'}

class VehicleCounter:
    def __init__(self, camera_id=None, store=None, date_provider=None):
        self.line=None;self.positions={};self.counted=set();self.in_count=self.out_count=0
        self.camera_id=camera_id;self.store=store;self.day=None;self.pending=[];self.retry_at=0
        self.date_provider=date_provider or (lambda:datetime.now(ZoneInfo('Asia/Kolkata')).date())

    def _restore(self):
        day=self.date_provider()
        if day==self.day:return True
        if time.monotonic()<self.retry_at:return False
        if self.pending:self._flush(force=True)
        if self.pending:return False  # Preserve uncommitted previous-day crossings for retry.
        try:counts=self.store.load(self.camera_id,day) if self.store else (0,0)
        except Exception as error:
            self.retry_at=time.monotonic()+5
            logger.warning(f'Vehicle totals unavailable: camera={self.camera_id} {type(error).__name__}')
            return False
        self.day=day;self.in_count,self.out_count=counts
        self.positions.clear();self.counted.clear()
        return True

    def _flush(self,force=False):
        if not self.pending or (not force and time.monotonic()<self.retry_at):return
        try:
            self.in_count,self.out_count=self.store.record(self.camera_id,self.day,self.pending)
            self.pending.clear();self.retry_at=0
        except Exception as error:
            self.retry_at=time.monotonic()+5
            logger.warning(f'Vehicle count persistence retry pending: camera={self.camera_id} {type(error).__name__}')

    def configure(self,line):
        line=line if line and line.get('enabled',True) else None
        if line!=self.line:
            self.line=line;self.positions.clear();self.counted.clear()
            if not self.store:self.in_count=self.out_count=0

    def update(self,tracks,shape):
        if not self.line:return None
        if not self._restore():return None
        h,w=shape[:2];a,b=self.line['points'];ax,ay=a['x'],a['y'];bx,by=b['x'],b['y']
        if h<=0 or w<=0:return None
        length=math.hypot(bx-ax,by-ay)
        if length<=0:return None
        active=set()
        for t in tracks:
            if t.get('class_name') not in VEHICLES or t.get('time_since_update',0)>0:continue
            tid=t.get('track_id');x1,y1,x2,y2=t['bbox']
            if tid is None or not all(math.isfinite(v) for v in (x1,y1,x2,y2)) or x2<=x1 or y2<=y1:continue
            active.add(tid);p=((x1+x2)*.5/w,(y1+y2)*.5/h)
            distance=((bx-ax)*(p[1]-ay)-(by-ay)*(p[0]-ax))/length
            if abs(distance)<.01:continue # Deadband suppresses near-line jitter.
            side=1 if distance>0 else -1;previous=self.positions.get(tid)
            if previous and previous[1]!=side:
                q,oldside,old_distance=previous
                ratio=abs(old_distance)/(abs(old_distance)+abs(distance))
                cross=(q[0]+ratio*(p[0]-q[0]),q[1]+ratio*(p[1]-q[1]))
                projection=((cross[0]-ax)*(bx-ax)+(cross[1]-ay)*(by-ay))/(length*length)
                direction='in' if side>0 else 'out'
                if 0<=projection<=1 and (tid,direction) not in self.counted:
                    self.counted.add((tid,direction))
                    if self.store:self.pending.append((uuid.uuid4().hex,direction))
                    if direction=='in':self.in_count+=1
                    else:self.out_count+=1
            self.positions[tid]=(p,side,distance)
        # Keep crossing deduplication for the full session, even after disappearance.
        self.positions={tid:p for tid,p in self.positions.items() if tid in active}
        self._flush()
        return {'in':self.in_count,'out':self.out_count,'total':self.in_count+self.out_count}
