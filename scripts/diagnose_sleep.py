"""Esplora in dettaglio sleep.dailySleepDTO per trovare i campi giusti."""
from coach.utils.supabase_client import get_supabase
import json

sb = get_supabase()
r = sb.table('daily_wellness').select('date,raw_payload').not_.is_('raw_payload','null').order('date',desc=True).limit(1).execute()

payload = r.data[0]['raw_payload']
print(f"Date: {r.data[0]['date']}")
print()

dto = (payload.get('sleep') or {}).get('dailySleepDTO') or {}
print('=== sleep.dailySleepDTO keys ===')
print(list(dto.keys()))
print()

print('=== sleepScores ===')
scores = dto.get('sleepScores') or {}
print(json.dumps(scores, indent=2)[:2000])
print()

print('=== Campi numerici diretti in dailySleepDTO ===')
for k, v in dto.items():
    if isinstance(v, (int, float, str)) and v is not None:
        print(f'  {k}: {repr(v)[:80]}')
print()

# Top-level fields utili
top = payload
print('=== Top-level fields utili ===')
useful = ['totalSteps','restingHeartRate','averageStressLevel','maxStressLevel',
          'bodyBatteryHighestValue','bodyBatteryLowestValue','moderateIntensityMinutes',
          'vigorousIntensityMinutes','intensityMinutesGoal','sleepingSeconds',
          'lastSevenDaysAvgRestingHeartRate','avgWakingRespirationValue',
          'totalKilocalories','activeKilocalories']
for k in useful:
    print(f'  {k}: {top.get(k)}')
