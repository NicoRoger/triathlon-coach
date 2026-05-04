"""Rimappatura training_status: traduce i valori numerici '8', '9' nei nomi corretti.

I dati ingestiti prima del fix del dict map_status hanno valori come '8' al posto
di 'strained'. Questo script li rimappa applicando la versione aggiornata.
"""
from coach.utils.supabase_client import get_supabase

# Mapping completo, deve essere lo stesso di _extract_training_status
MAP = {
    '0': 'no_status',
    '1': 'peaking',
    '2': 'productive',
    '3': 'maintaining',
    '4': 'recovery',
    '5': 'unproductive',
    '6': 'detraining',
    '7': 'overreaching',
    '8': 'strained',
    '9': 'no_recent_load',
}


def main() -> None:
    sb = get_supabase()
    
    # daily_wellness
    r = sb.table('daily_wellness').select('id,date,training_status').not_.is_('training_status', 'null').execute()
    fixed_w = 0
    for row in r.data:
        old = row.get('training_status')
        if old in MAP:
            new = MAP[old]
            sb.table('daily_wellness').update({'training_status': new}).eq('id', row['id']).execute()
            fixed_w += 1
    print(f'daily_wellness: rimappati {fixed_w} record')
    
    # daily_metrics
    r = sb.table('daily_metrics').select('id,date,garmin_training_status').not_.is_('garmin_training_status', 'null').execute()
    fixed_m = 0
    for row in r.data:
        old = row.get('garmin_training_status')
        if old in MAP:
            new = MAP[old]
            sb.table('daily_metrics').update({'garmin_training_status': new}).eq('id', row['id']).execute()
            fixed_m += 1
    print(f'daily_metrics: rimappati {fixed_m} record')


if __name__ == '__main__':
    main()