"""Check a generated QR and smaller webcam-like sizes, without live injection.

Run: backend/.venv/Scripts/python.exe scripts/diagnose_student_qr.py
"""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from ai_engine.identity.qr_identity import QRIdentityTracker,load_student_mapping


def main():
    roll='23VE1A6607'
    path=ROOT/'student_qr'/f'{roll}.png'
    image=cv2.imread(str(path))
    if image is None:
        raise SystemExit(f'Cannot read {path}')
    decoder=cv2.QRCodeDetector()
    found,multi,points,_=decoder.detectAndDecodeMulti(image)
    single,_,_=decoder.detectAndDecode(image)
    assert roll in multi or single.strip()==roll,'Raw generated QR failed to decode'
    mapping=load_student_mapping(ROOT/'student_face_list.xlsx')
    results=[]
    for width in (image.shape[1],160,120,100,80,64,48,40,32):
        height=round(image.shape[0]*width/image.shape[1])
        small=cv2.resize(image,(width,height),interpolation=cv2.INTER_NEAREST)
        frame=np.full((480,640,3),255,np.uint8)
        x,y=320-width//2,240-height//2
        frame[y:y+height,x:x+width]=small
        scanner=QRIdentityTracker(mapping,scan_interval=.25,association_margin_px=40)
        track=dict(track_id=24,class_name='person',bbox=[160,40,480,450],confidence=.87,time_since_update=0)
        started=time.perf_counter()
        output=scanner.update(frame,[track],now=100,frame_number=1)
        identity=output[0]['identity']
        results.append(dict(qr_width_px=width,qr_height_px=height,decoded=identity['roll_no'] if identity else '',
                            controlled_selected_track=identity['track_id'] if identity else None,
                            scan_ms=round((time.perf_counter()-started)*1000,2)))
    successful=[r['qr_width_px'] for r in results if r['decoded']==roll]
    report=dict(raw_qr_file=str(path),raw_multi_found=bool(found),raw_multi_decoded=list(multi),
                raw_single_decoded=single,student_mapping_count=len(mapping),sizes=results,
                smallest_successful_clean_fixture_px=min(successful) if successful else None,
                note='Controlled resize test, not a live webcam decode or universal minimum size.')
    destination=ROOT/'logs'/'student-qr-size-diagnostic.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
