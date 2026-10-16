-- TITrack Ko-fi Donation Goal
-- Migration: 005_kofi_donations
-- Description: Records Ko-fi payments (via the kofi-webhook Edge Function) so
-- the app can show progress toward the monthly server-cost goal.
--
-- Rows are written only by the Edge Function using the service role. RLS is
-- enabled with no policies, so anon clients cannot read individual payments;
-- they only see the monthly aggregate from get_donation_progress(). No donor
-- details (name, email, message) are stored.

CREATE TABLE IF NOT EXISTS kofi_donations (
    kofi_transaction_id TEXT PRIMARY KEY,
    amount NUMERIC(10, 2) NOT NULL,
    currency TEXT NOT NULL,
    payment_type TEXT NOT NULL,                       -- Donation, Subscription, Commission, Shop Order
    is_subscription_payment BOOLEAN NOT NULL DEFAULT FALSE,
    is_test BOOLEAN NOT NULL DEFAULT FALSE,           -- Ko-fi dashboard "send test" payloads
    paid_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kofi_donations_paid_at
    ON kofi_donations(paid_at);

ALTER TABLE kofi_donations ENABLE ROW LEVEL SECURITY;

-- Monthly progress toward the goal. The month is the current UTC calendar
-- month. Change the goal here (CREATE OR REPLACE) without an app release.
CREATE OR REPLACE FUNCTION get_donation_progress()
RETURNS TABLE (
    month_total NUMERIC,
    goal NUMERIC,
    currency TEXT,
    month_start TIMESTAMPTZ
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    WITH bounds AS (
        SELECT date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS start_ts
    )
    SELECT
        COALESCE(SUM(d.amount), 0) AS month_total,
        100::NUMERIC AS goal,
        'USD'::TEXT AS currency,
        b.start_ts AS month_start
    FROM bounds b
    LEFT JOIN kofi_donations d
        ON d.paid_at >= b.start_ts AND NOT d.is_test
    GROUP BY b.start_ts;
$$;

REVOKE ALL ON FUNCTION get_donation_progress() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION get_donation_progress() TO anon, authenticated;
