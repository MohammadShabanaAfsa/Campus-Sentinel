"""Conservative temporal fall candidates from already sampled MediaPipe Pose."""
import math
import time
from ai_engine.vision.behavior_overlay import event


class FallDetector:
    def __init__(self, settings):
        self.settings=settings
        self.states={}

    def analyze(self, tracks, signals, shape, now=None):
        now=time.monotonic() if now is None else now
        h,w=shape[:2];events=[];active=set()
        for track in tracks:
            if track.get('class_name')!='person' or track.get('time_since_update',0)>0:continue
            tid=track['track_id'];active.add(tid)
            state=self.states.setdefault(tid,{'phase':'NORMAL','last_seen':now})
            if now<state['last_seen'] or now-state['last_seen']>3:
                state.clear();state.update(phase='NORMAL',last_seen=now)
            state['last_seen']=now
            raw=signals.get(tid,{})
            pose=raw.get('fall_pose',{})
            if not all(key in pose for key in ('left_shoulder','right_shoulder','left_hip','right_hip')):
                state.pop('candidate_since',None)
                if state['phase']!='FALL CONFIRMED':state['phase']='NORMAL'
                if state['phase']=='FALL CONFIRMED':events.append(event('fall_detected','high',tid))
                continue
            a,b,c,d=raw.get('analysis_bbox',track['bbox'])
            def midpoint(left,right):
                p,q=pose[left],pose[right]
                return (a+(p[0]+q[0])*.5*(c-a),b+(p[1]+q[1])*.5*(d-b))
            shoulder=midpoint('left_shoulder','right_shoulder');hip=midpoint('left_hip','right_hip')
            dx,dy=hip[0]-shoulder[0],hip[1]-shoulder[1]
            if math.hypot(dx,dy)<10:continue
            angle=math.degrees(math.atan2(abs(dx),abs(dy)))
            x1,y1,x2,y2=track['bbox'];aspect=(x2-x1)/max(1,y2-y1);center=(y1+y2)*.5/h
            upright=angle<25 and aspect<.8
            horizontal=angle>=self.settings.FALL_ANGLE_THRESHOLD and aspect>=.9 and hip[1]/h>=.5
            knees=[(a+p[0]*(c-a),b+p[1]*(d-b)) for key,p in pose.items() if key.endswith('_knee')]
            # Visible downward legs support a crouch/bend rather than a collapsed body.
            supported=any(ky>hip[1] and abs(ky-hip[1])>abs(kx-hip[0]) for kx,ky in knees)
            horizontal=horizontal and not supported
            if upright:
                state['upright']=(now,angle,center)
                state.pop('candidate_since',None)
                if state['phase']=='FALL CONFIRMED':
                    state.setdefault('recovery_since',now)
                    if now-state['recovery_since']>=self.settings.FALL_RECOVERY_SECS:state['phase']='NORMAL'
                else:state['phase']='NORMAL'
            else:
                state.pop('recovery_since',None)
                if state['phase']!='FALL CONFIRMED':
                    previous=state.get('upright')
                    rapid=(previous is not None and 0<now-previous[0]<=2 and
                           (angle-previous[1])/(now-previous[0])>=30 and center-previous[2]>=.08)
                    if horizontal and (rapid or 'candidate_since' in state):
                        state.setdefault('candidate_since',now);state['phase']='FALL CANDIDATE'
                        if now-state['candidate_since']>=self.settings.FALL_PERSISTENCE_SECS:state['phase']='FALL CONFIRMED'
                    else:state.pop('candidate_since',None);state['phase']='NORMAL'
            if state['phase']=='FALL CONFIRMED':events.append(event('fall_detected','high',tid))
        self.states={tid:s for tid,s in self.states.items() if tid in active or now-s['last_seen']<=3}
        return events
