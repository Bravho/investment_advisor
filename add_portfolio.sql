-- ============================================================
--  Portfolio Holdings — Tho's actual positions
--  Updated 2026-10-07: BAFS fully sold; SCBGOLDE qty=4608;
--  SCBGOLDE avg_cost_price = 499730/4608 (499730 is TOTAL cost THB)
--  Run with:
--    psql -U investor_app -d investor_db -f ~/Projects/investment_advisor/add_portfolio.sql
-- ============================================================

-- Show existing columns so we know the schema
\d holdings

-- Remove any existing rows for these tickers so re-running is safe
DELETE FROM holdings WHERE ticker IN ('BAFS.BK', 'PTTEP.BK', 'SCB.BK', 'SCBGOLDE');

-- Thai stocks (avg_cost_price unknown — set to NULL for now; do NOT invent)
INSERT INTO holdings (ticker, name, asset_class, quantity, avg_cost_price, currency)
VALUES
    ('PTTEP.BK', 'PTT Exploration and Production',   'stock',  1400, NULL, 'THB'),
    ('SCB.BK',   'Siam Commercial Bank',             'stock',  1400, NULL, 'THB');

-- SCB Gold Open End Fund
-- Tho decision 2026-10-07: 499730 THB is TOTAL cost; avg_cost_price = 499730/4608
INSERT INTO holdings (ticker, name, asset_class, quantity, avg_cost_price, currency)
VALUES
    ('SCBGOLDE', 'SCB Gold Open End Fund', 'mutual_fund', 4608, ROUND((499730::numeric / 4608::numeric), 6), 'THB');

-- Verify
SELECT ticker, name, asset_class, quantity, avg_cost_price, currency,
       (avg_cost_price * quantity) AS implied_total_cost
FROM holdings
ORDER BY asset_class, ticker;
