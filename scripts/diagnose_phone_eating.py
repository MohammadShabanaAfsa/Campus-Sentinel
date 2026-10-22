"""Offline diagnosis of saved live frames; never writes detections or alerts."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('frames',nargs='+',type=Path)
parser.add_argument('--output',type=Path,default=ROOT/'logs/phone-eating-repair/saved-frame-analysis.json')
args=parser.parse_args();frames=[p.resolve() for p in args.frames];output=args.output.resolve()
os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'));os.environ['DEBUG']='false'
import cv2
from app.core.config import settings
from ai_engine.vision.detector import YOLODetector
from ai_engine.behavioral.person_activity import PersonActivityAnalyzer
detector=YOLODetector.get_instance(str(ROOT/'backend/yolov8n.pt'))
analyzer=PersonActivityAnalyzer('offline-phone-eating',settings)
reports=[]
for path in frames:
    frame=cv2.imread(str(path))
    if frame is None:raise ValueError('Unreadable frame: '+str(path))
    # Post-NMS model candidates, before Campus Sentinel class/confidence filtering.
    with detector._inference_lock:results=detector._model(frame,conf=.05,classes=None,imgsz=640,verbose=False)
    raw=[{'class_id':int(b.cls[0]),'class_name':r.names[int(b.cls[0])],
          'confidence':float(b.conf[0]),'bbox':b.xyxy[0].tolist()} for r in results for b in r.boxes]
    metadata=path.with_suffix('.json')
    tracks=json.loads(metadata.read_text()).get('tracks',[]) if metadata.exists() else []
    full=detector.detect(frame)
    if not tracks:
        tracks=[{**d,'track_id':i+1,'time_since_update':0} for i,d in enumerate(full) if d['class_name']=='person']
    roi=detector.detect_phone_rois(frame,tracks,settings.PHONE_ROI_MAX_PERSONS)
    signals=analyzer.sample(frame,tracks)
    association=analyzer.analyze(tracks,full+[d for d in roi if not any(x['class_name']=='cell phone' for x in full)],signals,frame.shape)
    report={'frame':str(path),'raw_candidates':raw,'full_frame_phones':[d for d in full if d['class_id']==67],
            'diagnostic_roi_phones':roi,'signals':signals,'association':analyzer.phone_observations,
            'confirmed_events':association,'phone_threshold':detector.phone_conf_threshold}
    reports.append(report)
    print(json.dumps({'frame':path.name,'raw_candidates':raw,'full_frame_phones':report['full_frame_phones'],
        'diagnostic_roi_phones':roi,'association':analyzer.phone_observations}),flush=True)
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(reports,indent=2),encoding='utf-8')
