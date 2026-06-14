-- 2026-05-30 — Seed zone CORSA (PROVVISORIE) dal test soglia del 30/05/2026
--
-- CONTESTO
--   Il test "Threshold Run 30min" (planned_session 305a185a) e' stato eseguito ma
--   l'auto-processore non ha aggiornato le zone perche' la sessione aveva
--   structured=null (vedi BUG-010 in docs/OPEN_ISSUES.md). Recuperiamo il
--   risultato dagli split reali dell'attivita' garmin_23070999120 (lap 4-8 =
--   blocco all-out ~20').
--
--   Calcolo (lap 4-8: 4637m in 20'24"):
--     - pace media   = 263 s/km = 4:23/km  -> threshold_pace_s_per_km
--     - HR media     = 183 bpm             -> lthr
--     - HR max       = 194 bpm             -> hr_max
--
--   PROVVISORIO: test 20' (non 30') e pacing aggressivo (HR fino a 194/Z5, calo
--   finale 365->319W). Stima ragionevole ma leggermente ottimistica: un 30'
--   pulito dara' una soglia un filo piu' lenta. Riconfermare. method lo riflette.
--
-- IDEMPOTENTE: rieseguibile (DELETE + INSERT).

DELETE FROM physiology_zones WHERE discipline = 'run' AND valid_from = '2026-05-30';

INSERT INTO physiology_zones (
    discipline, valid_from, valid_to,
    threshold_pace_s_per_km, lthr, hr_max,
    test_activity_id, method, notes
) VALUES (
    'run', '2026-05-30', NULL,
    263, 183, 194,
    '9e0a5adf-08f7-46b9-9639-9153ce270004',
    'threshold_run_20min_provisional',
    '{"zone_system":"pace_5zone+lthr_5zone","provisional":true,'
    || '"caveat":"test 20min invece di 30, pacing aggressivo - riconfermare con 30 pulito",'
    || '"pace_zones":{"Z1_recovery":">5:29/km","Z2_endurance":"5:03-5:29/km",'
    || '"Z3_tempo":"4:36-5:03/km","Z4_threshold":"4:15-4:36/km","Z5_vo2max":"<4:15/km"},'
    || '"lthr_zones":{"Z1":"<148","Z2":"148-163","Z3":"165-174","Z4":"176-183","Z5":">183"}}'
);
