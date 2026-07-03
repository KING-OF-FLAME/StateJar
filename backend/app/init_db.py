"""Initialize database schema on startup."""

from sqlalchemy import text
from app.database import engine
from app.config import get_settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 email VARCHAR(255) NOT NULL UNIQUE,
 password_hash VARCHAR(255) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS memory_states (
 handle VARCHAR(80) NOT NULL PRIMARY KEY,
 parent_handle VARCHAR(80) NULL,
 state_json JSON NOT NULL,
 schema_version VARCHAR(20) NOT NULL,
 norm_version VARCHAR(20) NOT NULL,
 user_id BIGINT UNSIGNED NOT NULL,
 session_tag VARCHAR(100) NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_memory_states_user
 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
 CONSTRAINT fk_memory_states_parent
 FOREIGN KEY (parent_handle) REFERENCES memory_states (handle) ON DELETE SET NULL,
 INDEX idx_memory_states_user (user_id),
 INDEX idx_memory_states_session (session_tag)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_logs (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 request_id VARCHAR(64) NOT NULL,
 user_id BIGINT UNSIGNED NOT NULL,
 handle_used VARCHAR(80) NULL,
 subset_keys JSON NULL,
 provider VARCHAR(50) NULL,
 model VARCHAR(100) NULL,
 schema_version VARCHAR(20) NULL,
 norm_version VARCHAR(20) NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_audit_logs_user
 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
 INDEX idx_audit_logs_request (request_id),
 INDEX idx_audit_logs_user (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS api_keys (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT UNSIGNED NOT NULL,
 key_hash VARCHAR(255) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 revoked TINYINT(1) NOT NULL DEFAULT 0,
 CONSTRAINT fk_api_keys_user
 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
 INDEX idx_api_keys_user (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS provider_keys (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT UNSIGNED NOT NULL,
 provider VARCHAR(50) NOT NULL,
 encrypted_key BLOB NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_provider_keys_user
 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
 INDEX idx_provider_keys_user (user_id)
) ENGINE=InnoDB;
"""


def init_db():
    """Create all tables if they don't exist."""
    try:
        with engine.connect() as conn:
            # Split by semicolon and execute each statement
            for statement in SCHEMA_SQL.split(';'):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))
            conn.commit()
        print("✅ Database schema initialized successfully")
    except Exception as e:
        print(f"⚠️ Database initialization error: {e}")
        # Don't fail startup if tables already exist
        pass


if __name__ == "__main__":
    init_db()

