-- 2026-06-21 — Correzione manuale zone CORSA (caldo) + lock
--
-- CONTESTO
--   Le zone corsa erano state ricalcolate dal test prendendo l'HR grezza (183),
--   gonfiata dal caldo. Valore corretto atleta: LTHR 172, soglia 4:20/km (260 s/km).
--   Conseguenza del valore sbagliato: la compliance giudicava le corse Z2 con una
--   soglia falsata e generava target Z3 troppo intensi.
--
--   method='manual_heat_corrected' → la pipeline NON la sovrascrive (lock in
--   fitness_test_processor._upsert_physiology_zones: salta il ricalcolo se esiste
--   una zona attiva con method 'manual%').
--
--   Zone (contigue): pace da _compute_pace_5zone(260), HR da _compute_lthr_5zone(172).
--
-- IDEMPOTENTE: rieseguibile (chiude la provvisoria, re-inserisce la manuale).

-- 1) Chiudi la zona provvisoria (non più attiva)
UPDATE physiology_zones
SET valid_to = '2026-06-21'
WHERE discipline = 'run' AND method = 'threshold_run_20min_provisional' AND valid_to IS NULL;

-- 2) Inserisci la zona corretta, bloccata (attiva: valid_to NULL)
DELETE FROM physiology_zones WHERE discipline = 'run' AND method = 'manual_heat_corrected';

INSERT INTO physiology_zones (
    discipline, valid_from, valid_to,
    threshold_pace_s_per_km, lthr, hr_max,
    method, notes
) VALUES (
    'run', '2026-06-21', NULL,
    260, 172, 194,
    'manual_heat_corrected',
    '{"zone_system":"pace_5zone+lthr_5zone","manual":true,'
    || '"caveat":"LTHR corretta per il caldo (172, non 183); soglia 4:20/km",'
    || '"pace_zones":{"Z1_recovery":">5:25/km","Z2_endurance":"4:59-5:25/km",'
    || '"Z3_tempo":"4:33-4:59/km","Z4_threshold":"4:12-4:33/km","Z5_vo2max":"<4:12/km"},'
    || '"lthr_zones":{"Z1":"<139","Z2":"139-153","Z3":"153-163","Z4":"163-172","Z5":">172"}}'
);
