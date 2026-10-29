-- NEEDS DECISION: fill real avg_cost_price (THB per share). Do NOT run with invented numbers.
-- Current state (2026-10-07):
--   BAFS.BK fully sold — removed from holdings.
--   PTTEP.BK / SCB.BK still have NULL avg_cost_price (P&L unreliable).
--   SCBGOLDE RESOLVED: quantity=4608; avg_cost_price = ROUND(499730/4608, 6) = 108.448351
--     (Tho decision: 499730 THB is TOTAL cost, not per-unit.)
BEGIN;
-- UPDATE holdings SET avg_cost_price = <PTTEP_AVG_COST_THB>, updated_at = NOW() WHERE ticker = 'PTTEP.BK';
-- UPDATE holdings SET avg_cost_price = <SCB_AVG_COST_THB>, updated_at = NOW() WHERE ticker = 'SCB.BK';
-- SELECT ticker, quantity, avg_cost_price FROM holdings ORDER BY ticker;
ROLLBACK;
