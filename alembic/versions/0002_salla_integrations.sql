CREATE TABLE IF NOT EXISTS salla_integrations (
    id VARCHAR(36) PRIMARY KEY,
    store_id VARCHAR(120) NOT NULL UNIQUE,
    store_name VARCHAR(255),
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_salla_integrations_store_id
    ON salla_integrations (store_id);
