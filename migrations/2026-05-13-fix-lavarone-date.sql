-- Fix Lavarone Cross Sprint date: 2026-09-06 → 2026-08-29
-- Confirmed on lavaronetriathlon.com

UPDATE races
SET race_date = '2026-08-29'
WHERE name = 'Lavarone Cross Sprint' AND race_date = '2026-09-06';
