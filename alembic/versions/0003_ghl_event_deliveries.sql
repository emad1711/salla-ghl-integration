CREATE TABLE IF NOT EXISTS ghl_event_deliveries (
    id VARCHAR(36) PRIMARY KEY,
    event_name VARCHAR(120) NOT NULL,
    dedupe_key VARCHAR(255) NOT NULL UNIQUE,
    request_body JSON,
    response_status INTEGER,
    response_body TEXT,
    status VARCHAR(40) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_ghl_event_deliveries_event_name
    ON ghl_event_deliveries (event_name);

CREATE INDEX IF NOT EXISTS ix_ghl_event_deliveries_dedupe_key
    ON ghl_event_deliveries (dedupe_key);

CREATE INDEX IF NOT EXISTS ix_ghl_event_deliveries_status
    ON ghl_event_deliveries (status);
