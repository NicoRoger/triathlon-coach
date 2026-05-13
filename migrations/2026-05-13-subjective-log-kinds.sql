-- Add missing kind values to subjective_log check constraint.
-- The bot uses: proactive_response, brief_response, video_analysis
-- which were not included in the original constraint.

ALTER TABLE subjective_log DROP CONSTRAINT IF EXISTS subjective_log_kind_check;

ALTER TABLE subjective_log ADD CONSTRAINT subjective_log_kind_check CHECK (kind IN (
    'post_session',
    'morning',
    'evening_debrief',
    'illness',
    'injury',
    'free_note',
    'proactive_response',
    'brief_response',
    'video_analysis'
));
