-- 003: audit logs record which session they belong to, so the Audit tab
-- can filter by the active session_tag. (MySQL / XAMPP-MariaDB compatible)
USE statejar;

ALTER TABLE audit_logs
  ADD COLUMN IF NOT EXISTS session_tag VARCHAR(100) NULL AFTER handle_used;

ALTER TABLE audit_logs
  ADD INDEX IF NOT EXISTS idx_audit_logs_session (user_id, session_tag);
