CREATE TABLE IF NOT EXISTS webhook_events (
    id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(120),
    event_type VARCHAR(120) NOT NULL,
    source VARCHAR(40) NOT NULL DEFAULT 'salla',
    merchant_id VARCHAR(120),
    payload_hash VARCHAR(64) NOT NULL UNIQUE,
    raw_payload JSON NOT NULL,
    status VARCHAR(40) NOT NULL,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS customers (
    id VARCHAR(36) PRIMARY KEY,
    salla_customer_id VARCHAR(120),
    ghl_contact_id VARCHAR(120),
    email VARCHAR(255),
    phone VARCHAR(60),
    first_name VARCHAR(120),
    last_name VARCHAR(120),
    status VARCHAR(40) NOT NULL DEFAULT 'new',
    total_spent NUMERIC(12, 2) NOT NULL DEFAULT 0,
    purchase_count INTEGER NOT NULL DEFAULT 0,
    last_purchase_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id VARCHAR(36) PRIMARY KEY,
    salla_order_id VARCHAR(120) NOT NULL UNIQUE,
    reference_id VARCHAR(120),
    customer_id VARCHAR(36) REFERENCES customers(id),
    status VARCHAR(80),
    payment_status VARCHAR(80),
    fulfillment_status VARCHAR(80),
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    currency VARCHAR(10) NOT NULL DEFAULT 'SAR',
    admin_url TEXT,
    placed_at TIMESTAMP WITH TIME ZONE,
    paid_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL REFERENCES orders(id),
    salla_product_id VARCHAR(120),
    sku VARCHAR(120),
    name VARCHAR(255),
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_price NUMERIC(12, 2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS customer_tags (
    id VARCHAR(36) PRIMARY KEY,
    customer_id VARCHAR(36) NOT NULL REFERENCES customers(id),
    tag VARCHAR(120) NOT NULL,
    source VARCHAR(40) NOT NULL DEFAULT 'salla',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    removed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_customer_tag UNIQUE (customer_id, tag)
);

CREATE TABLE IF NOT EXISTS product_interests (
    id VARCHAR(36) PRIMARY KEY,
    customer_id VARCHAR(36) NOT NULL REFERENCES customers(id),
    salla_product_id VARCHAR(120),
    sku VARCHAR(120),
    product_name VARCHAR(255),
    source VARCHAR(40) NOT NULL DEFAULT 'salla',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    notified_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_customer_product_interest UNIQUE (customer_id, salla_product_id, sku)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id VARCHAR(36) PRIMARY KEY,
    customer_id VARCHAR(36) REFERENCES customers(id),
    order_id VARCHAR(36) REFERENCES orders(id),
    workflow_type VARCHAR(120) NOT NULL,
    stage VARCHAR(120) NOT NULL DEFAULT 'initial',
    status VARCHAR(40) NOT NULL,
    scheduled_for TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata_json JSON,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS outbound_requests (
    id VARCHAR(36) PRIMARY KEY,
    provider VARCHAR(60) NOT NULL DEFAULT 'ghl',
    method VARCHAR(20) NOT NULL DEFAULT 'POST',
    url TEXT NOT NULL,
    request_body JSON,
    response_status INTEGER,
    response_body TEXT,
    status VARCHAR(40) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    id VARCHAR(36) PRIMARY KEY,
    job_name VARCHAR(120) NOT NULL UNIQUE,
    cursor TEXT,
    last_run_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(80) NOT NULL DEFAULT 'idle',
    metadata_json JSON
);
