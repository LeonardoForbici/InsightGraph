CREATE TABLE IF NOT EXISTS metrics_timeseries (
    time TIMESTAMPTZ NOT NULL,
    metric_type TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    metadata JSONB DEFAULT '{}'::JSONB
);

SELECT create_hypertable(
    'metrics_timeseries',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);
