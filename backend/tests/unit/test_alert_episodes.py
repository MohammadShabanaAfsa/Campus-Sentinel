from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions
from ai_engine.vision.behavior_overlay import event,BehaviorOverlayCache

def test_new_episode_after_clear_has_new_id_and_same_episode_is_quiet():
 router=ConfirmedAlertTransitions();e=event('phone_use','low',1)
 first=router.update([e],[],now=0)[0]
 assert router.update([e],[],now=1)==[]
 router.update([],[],now=5)
 second=router.update([e],[],now=6)[0]
 assert first['metadata']['episode_id']!=second['metadata']['episode_id']

def test_people_pairs_and_bags_have_independent_episodes():
 router=ConfirmedAlertTransitions()
 events=[event('phone_use','low',1),event('phone_use','low',2),
         event('suspected_fight','high',track_ids=[1,2]),event('suspected_fight','high',track_ids=[3,4]),
         event('abandoned_bag','high',bag_track_ids=[10,11],owner_track_ids=[1,2])]
 alerts=router.update(events,[],now=0)
 assert len(alerts)==6 and len({a['metadata']['episode_id'] for a in alerts})==6
 assert not router.update(events,[],now=1)
 assert len(ConfirmedAlertTransitions().update(events,[],now=0))==6

def test_multiple_fight_pairs_survive_overlay_cache_for_alert_routing():
 cache=BehaviorOverlayCache('session')
 events=[event('suspected_fight','high',track_ids=pair) for pair in ([1,2],[3,4])]
 cache.update('campus',{'stream_session':'session','observed_at':10,'overlay_events':events},now=10)
 assert len(cache.confirmed_events([],now=10))==2

def test_stale_person_has_no_ghost_overlay():
 cache=BehaviorOverlayCache('session')
 cache.update('activity',{'stream_session':'session','observed_at':10,'overlay_events':[event('phone_use','low',1)]},now=10)
 tracks=[{'track_id':1,'class_name':'person','time_since_update':1}]
 assert not cache.attach(tracks,now=10)[0][0]['behaviors']
 assert not cache.confirmed_events(tracks,now=10)

def test_exit_zones_are_independent_episodes():
 router=ConfirmedAlertTransitions()
 events=[event('emergency_exit_blocked','high',zone_id='A'),event('emergency_exit_blocked','high',zone_id='B')]
 assert len(router.update(events,[],now=0))==2
 assert not router.update(events,[],now=1)
