-- CycloneReady Day 8: LLM latency analysis
-- PostgreSQL percentile_cont calculates continuous percentiles.

-- Overall p50 and p95 latency for successful LLM calls.
SELECT
    COUNT(*) AS successful_calls,
    ROUND(AVG(latency_ms)::numeric, 2) AS average_latency_ms,
    ROUND(
        percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms)::numeric,
        2
    ) AS p50_latency_ms,
    ROUND(
        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)::numeric,
        2
    ) AS p95_latency_ms
FROM llm_calls
WHERE status = 'success';

-- Latency percentiles grouped by provider and model.
SELECT
    provider,
    model,
    COUNT(*) AS successful_calls,
    ROUND(AVG(latency_ms)::numeric, 2) AS average_latency_ms,
    ROUND(
        percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms)::numeric,
        2
    ) AS p50_latency_ms,
    ROUND(
        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)::numeric,
        2
    ) AS p95_latency_ms
FROM llm_calls
WHERE status = 'success'
GROUP BY provider, model
ORDER BY provider, model;
