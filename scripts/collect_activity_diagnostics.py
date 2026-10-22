"""Extract only structured activity diagnostics; never copy access-token logs."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect(log_path):
    groups = {}
    decoder = json.JSONDecoder()
    for line in log_path.read_text(encoding='utf-8', errors='replace').splitlines():
        if 'ACTIVITY_SAMPLE {' not in line:
            continue
        try:
            sample, _ = decoder.raw_decode(line.split('ACTIVITY_SAMPLE ', 1)[1])
        except (ValueError, TypeError):
            continue
        groups.setdefault((sample['camera_name'], sample['track_id']), []).append(sample)
    result = []
    for (camera, track), samples in groups.items():
        def values(section, key):
            return [s[section][key] for s in samples if isinstance(s[section].get(key), (int, float))]
        def span(section, key):
            found = values(section, key)
            return [min(found), max(found)] if found else None
        result.append({'camera_name':camera, 'track_id':track, 'samples':len(samples),
            'first_frame':samples[0]['frame_number'], 'last_frame':samples[-1]['frame_number'],
            'counter_first_last':[samples[0]['same_track_sample_count'],samples[-1]['same_track_sample_count']],
            'longest_continuous_sample_count':max(s['same_track_sample_count'] for s in samples),
            'state_counter_restarts':sum(samples[i]['same_track_sample_count']<=samples[i-1]['same_track_sample_count'] for i in range(1,len(samples))),
            'mouth_samples_first_last':[samples[0]['talking'].get('mouth_samples'),samples[-1]['talking'].get('mouth_samples')],
            'ear_range':span('sleeping','ear'),'mar_std_range':span('talking','mar_variability'),
            'sleep_duration_range':span('sleeping','duration_secs'),
            'talk_duration_range':span('talking','duration_secs'),
            'reset_reasons':{kind:sorted({s[kind]['reset_reason'] for s in samples if s[kind].get('reset_reason')})
                             for kind in ('sleeping','talking','phone_use','eating')},
            'last_face_sample':next((s for s in reversed(samples) if s['sleeping'].get('current_face_landmarks_available')),None),
            'last_sample':samples[-1]})
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--log',type=Path,default=ROOT/'logs/backend-activity-diagnostics-final.err.log')
    parser.add_argument('--output',type=Path,default=ROOT/'logs/activity-live-diagnostics.json')
    args=parser.parse_args()
    result=collect(args.log)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
