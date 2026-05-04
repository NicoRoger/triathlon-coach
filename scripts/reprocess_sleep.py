"""Reprocessing daily_wellness con nuovo mapping (sleep score + duration)."""
from coach.utils.supabase_client import get_supabase


def main() -> None:
    sb = get_supabase()

    r = sb.table('daily_wellness').select('id,date,raw_payload').not_.is_('raw_payload', 'null').execute()
    total = len(r.data)
    updated = 0
    errs = 0

    for i, row in enumerate(r.data):
        if i % 50 == 0:
            print(f'  ...{i}/{total}')
        try:
            payload = row.get('raw_payload') or {}
            sleep = payload.get('sleep') or {}
            sleep_dto = sleep.get('dailySleepDTO') or {}
            scores = sleep_dto.get('sleepScores') or {}

            overall = (scores.get('overall') or {}).get('value')
            sleep_total = sleep_dto.get('sleepTimeSeconds')
            awake = sleep_dto.get('awakeSleepSeconds')
            sleep_eff = None
            if sleep_total and awake is not None:
                tib = sleep_total + awake
                sleep_eff = round(sleep_total / tib, 4) if tib > 0 else None

            update_data = {
                'sleep_score': overall,
                'sleep_total_s': sleep_total,
                'sleep_deep_s': sleep_dto.get('deepSleepSeconds'),
                'sleep_rem_s': sleep_dto.get('remSleepSeconds'),
                'sleep_efficiency': sleep_eff,
            }
            if any(v is not None for v in update_data.values()):
                sb.table('daily_wellness').update(update_data).eq('id', row['id']).execute()
                updated += 1
        except Exception as e:
            errs += 1
            if errs < 5:
                date_str = row.get('date', '?')
                print(f'  FAIL {date_str}: {e}')

    print(f'\nProcessed {total}, updated {updated}, errors {errs}')

    r2 = sb.table('daily_wellness').select('id', count='exact').not_.is_('sleep_score', 'null').execute()
    print(f'Now total rows with sleep_score: {r2.count}')


if __name__ == '__main__':
    main()