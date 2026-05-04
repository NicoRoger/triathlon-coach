"""Diagnostica completa payload Garmin: trova dove vivono sleep, vo2max, training_status."""
from coach.utils.supabase_client import get_supabase
import json

sb = get_supabase()
r = sb.table('daily_wellness').select('date,raw_payload').not_.is_('raw_payload','null').order('date',desc=True).limit(1).execute()

if not r.data or not r.data[0]['raw_payload']:
    print('No raw_payload found')
    exit()

payload = r.data[0]['raw_payload']
print(f"Date: {r.data[0]['date']}")
print(f"Top-level keys in raw_payload: {list(payload.keys())}")
print()

# Cerca pattern multipli
keywords = ['sleep', 'vo2', 'training', 'fitnessage', 'recovery', 'intensity']

def walk(obj, path='', max_depth=5, depth=0):
    if depth >= max_depth:
        return []
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f'{path}.{k}' if path else k
            kl = k.lower()
            for kw in keywords:
                if kw in kl:
                    val_repr = repr(v)[:150] if not isinstance(v, (dict, list)) else f'<{type(v).__name__} len={len(v)}>'
                    results.append((kw, new_path, val_repr))
            if isinstance(v, (dict, list)):
                results.extend(walk(v, new_path, max_depth, depth+1))
    elif isinstance(obj, list) and obj and depth < max_depth:
        results.extend(walk(obj[0], f'{path}[0]', max_depth, depth+1))
    return results

hits = walk(payload)
by_kw = {}
for kw, path, val in hits:
    by_kw.setdefault(kw, []).append((path, val))

for kw in keywords:
    if kw in by_kw:
        print(f'=== {kw.upper()} ===')
        for path, val in by_kw[kw][:15]:
            print(f'  {path}: {val}')
        print()
