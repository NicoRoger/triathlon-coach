-- Migration: Resilience Audit 2026-06-01
-- Additive e idempotente. Esegui una volta nel SQL editor di Supabase.
--
-- Copre:
--   O4 — races UNIQUE(name, race_date): impedisce il re-seed che duplica la gara A
--        (ON CONFLICT DO NOTHING del seed era un no-op senza target unique).
--   O5 — mesocycles.target_race_id FK → races(id) ON DELETE SET NULL (no orfani).
--   O6/D1 — plan_modulations.expires_at: consente la scadenza delle modulazioni
--        stantie (una proposta di lunedì non deve essere applicabile venerdì).
--        Default conservativo 48h; le righe esistenti restano NULL (mai scadono,
--        retro-compatibile). CONFERMARE la finestra di 48h con l'atleta.

-- ── O4: races UNIQUE(name, race_date) ───────────────────────────────────────
-- DEDUP PRELIMINARE: la tabella può già contenere duplicati (es. Lavarone
-- inserito due volte da seed/fix data). Prima ripuntiamo eventuali mesocicli al
-- record sopravvissuto, poi eliminiamo i duplicati, infine aggiungiamo il vincolo.

-- 1) ripunta mesocycles dai duplicati al sopravvissuto (min ctid per name+date)
WITH survivors AS (
    SELECT name, race_date, MIN(ctid) AS keep_ctid
    FROM races GROUP BY name, race_date
),
dups AS (
    SELECT r.id AS dup_id, keep.id AS keep_id
    FROM races r
    JOIN survivors sv ON r.name = sv.name AND r.race_date = sv.race_date AND r.ctid <> sv.keep_ctid
    JOIN races keep ON keep.ctid = sv.keep_ctid
)
UPDATE mesocycles m SET target_race_id = d.keep_id
FROM dups d WHERE m.target_race_id = d.dup_id;

-- 2) elimina i duplicati (tiene il record con ctid minimo)
DELETE FROM races r USING (
    SELECT name, race_date, MIN(ctid) AS keep_ctid
    FROM races GROUP BY name, race_date
) sv
WHERE r.name = sv.name AND r.race_date = sv.race_date AND r.ctid <> sv.keep_ctid;

-- 3) ora il vincolo unique può essere creato
DO $$
BEGIN
    ALTER TABLE races ADD CONSTRAINT races_name_date_unique UNIQUE (name, race_date);
EXCEPTION
    WHEN duplicate_table THEN NULL;
    WHEN duplicate_object THEN NULL;
END $$;

-- ── O5: mesocycles.target_race_id FK → races(id) ON DELETE SET NULL ──────────
-- Azzera eventuali target_race_id orfani (puntano a gare non più esistenti)
-- altrimenti l'aggiunta della FK fallirebbe.
UPDATE mesocycles SET target_race_id = NULL
WHERE target_race_id IS NOT NULL
  AND target_race_id NOT IN (SELECT id FROM races);

DO $$
BEGIN
    ALTER TABLE mesocycles
        ADD CONSTRAINT mesocycles_target_race_fk
        FOREIGN KEY (target_race_id) REFERENCES races(id) ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ── O6/D1: plan_modulations.expires_at ──────────────────────────────────────
ALTER TABLE plan_modulations
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- Default per le NUOVE proposte (48h dalla creazione). Le righe storiche
-- restano NULL → l'enforcement nel codice (apply_modulation) le tratta come
-- "mai scadute" per retro-compatibilità.
ALTER TABLE plan_modulations
    ALTER COLUMN expires_at SET DEFAULT (NOW() + INTERVAL '48 hours');

-- ════════════════════════════════════════════════════════════════════════════
-- PARTE 2 — Modifiche COORDINATE con il codice (audit O7/E4/O8/O9).
-- Eseguire INSIEME al deploy del codice corrispondente (commit stesso branch).
-- ════════════════════════════════════════════════════════════════════════════

-- ── E4: physiology_zones UNIQUE(discipline, valid_from, method) ──────────────
-- NB: non esisteva ALCUN vincolo unique → l'upsert on_conflict="discipline,
-- valid_from" del fitness_test_processor sarebbe FALLITO a runtime al primo
-- test. Aggiungerlo con 'method' permette inoltre test diversi lo stesso giorno
-- (es. threshold + LTHR dalla stessa corsa) senza sovrascriversi.
-- (la tabella è vuota finché non si esegue il primo test → nessun conflitto)
DO $$
BEGIN
    ALTER TABLE physiology_zones
        ADD CONSTRAINT physiology_zones_disc_validfrom_method_unique
        UNIQUE (discipline, valid_from, method);
EXCEPTION
    WHEN duplicate_table THEN NULL;
    WHEN duplicate_object THEN NULL;
END $$;

-- ── O7: planned_sessions UNIQUE(planned_date, sport, session_type) ───────────
-- Allarga la chiave per consentire doppie sessioni legittime lo stesso giorno/
-- sport (brick, AM/PM). Aggiungere session_type è MENO restrittivo → le righe
-- esistenti restano valide. Coordinato con modulation._apply_single_change
-- (on_conflict aggiornato a "planned_date,sport,session_type").
DO $$
BEGIN
    ALTER TABLE planned_sessions DROP CONSTRAINT IF EXISTS unique_planned_date_sport;
    ALTER TABLE planned_sessions
        ADD CONSTRAINT unique_planned_date_sport_type
        UNIQUE (planned_date, sport, session_type);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ── O8: FK ON DELETE SET NULL (evita delete bloccati / orfani) ───────────────
DO $$
BEGIN
    ALTER TABLE planned_sessions
        DROP CONSTRAINT IF EXISTS planned_sessions_completed_activity_id_fkey;
    ALTER TABLE planned_sessions
        ADD CONSTRAINT planned_sessions_completed_activity_id_fkey
        FOREIGN KEY (completed_activity_id) REFERENCES activities(id) ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE physiology_zones
        DROP CONSTRAINT IF EXISTS physiology_zones_test_activity_id_fkey;
    ALTER TABLE physiology_zones
        ADD CONSTRAINT physiology_zones_test_activity_id_fkey
        FOREIGN KEY (test_activity_id) REFERENCES activities(id) ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ── O9: CHECK su plan_modulations.status (previene stati corrotti da typo) ───
-- Include tutti i valori scritti da bot Telegram + Python: proposed/accepted/
-- applied/partial/failed/rejected/expired/discussing.
DO $$
BEGIN
    ALTER TABLE plan_modulations
        ADD CONSTRAINT plan_modulations_status_check
        CHECK (status IN ('proposed','accepted','applied','partial','failed',
                          'rejected','expired','discussing'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ── K3: subjective_log.kind — aggiunge 'pattern_correction' ──────────────────
-- Il bot Telegram inserisce kind='pattern_correction' (correzione pattern) ma
-- non era nel CHECK → insert falliva e la correzione andava persa.
ALTER TABLE subjective_log DROP CONSTRAINT IF EXISTS subjective_log_kind_check;
ALTER TABLE subjective_log ADD CONSTRAINT subjective_log_kind_check CHECK (kind IN (
    'post_session', 'morning', 'evening_debrief', 'illness', 'injury',
    'free_note', 'proactive_response', 'brief_response', 'video_analysis',
    'pattern_correction'
));
