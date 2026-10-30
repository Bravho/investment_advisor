-- 2026-10-30: ThaiESG purchases reported by Tho (LINE 17:36 ICT; allotment confirmed for 2 Nov 2026).
-- Local investor_db only, additive, no deletes. Backup first: ~/backups/investor_db/investor_db.full.20261030-173920.dump
-- holdings is owned by another role (investor_app can INSERT/UPDATE but not ALTER), so wrapper/lock/pending fields live in a
-- side table keyed by ticker instead of new holdings columns.
CREATE TABLE IF NOT EXISTS holding_attributes (
    ticker              VARCHAR(30) PRIMARY KEY,
    tax_wrapper         VARCHAR(20),          -- e.g. 'ThaiESG'
    order_date          DATE,
    purchase_date       DATE,                 -- allotment / effective date
    lock_until          DATE,                 -- no sell/switch/trim suggestions before this date
    amount_invested_thb NUMERIC(18,2),
    units_status        VARCHAR(20) NOT NULL DEFAULT 'confirmed' CHECK (units_status IN ('pending','confirmed')),
    allotment_nav       NUMERIC(18,6),        -- filled from Tho's confirmation
    fund_house          VARCHAR(80),
    look_through        VARCHAR(40),          -- risk bucket for funds, e.g. 'thai_esg_equity'
    risk_proxy          VARCHAR(30),          -- daily-return proxy for risk/forecast models, e.g. 'TDEX.BK'
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO holdings (ticker, name, asset_class, exchange, quantity, avg_cost_price, currency)
SELECT v.ticker, v.name, 'mutual_fund', 'FUND', 0, NULL, 'THB' FROM (VALUES
  ('K-TNZ-ThaiESG', 'K Thai Net Zero ThaiESG Fund (KAsset)'),
  ('ES-SETESG-ThaiESG-A', 'Eastspring SET ESG Index ThaiESG Fund, class A (accumulating)'),
  ('TDSThaiESG-A', 'TISCO Dividend Select Equity Thailand ESG Fund, class A (accumulating)')
) AS v(ticker, name)
WHERE NOT EXISTS (SELECT 1 FROM holdings h WHERE h.ticker = v.ticker);

INSERT INTO holding_attributes (ticker, tax_wrapper, order_date, purchase_date, lock_until, amount_invested_thb, units_status,
                                fund_house, look_through, risk_proxy, notes)
VALUES
  ('K-TNZ-ThaiESG', 'ThaiESG', DATE '2026-10-30', DATE '2026-11-02', DATE '2031-11-02', 100000, 'pending',
   'KAsset (Kasikorn Asset Management)', 'thai_esg_equity', 'TDEX.BK',
   'Bought by Tho himself (ordered 30 Oct, effective/allotted 2 Nov 2026). Units = 100,000 / allotment NAV of 2 Nov - pending his confirmation. ThaiESG: hold >= 5 years counted day-to-day from purchase.'),
  ('ES-SETESG-ThaiESG-A', 'ThaiESG', DATE '2026-10-30', DATE '2026-11-02', DATE '2031-11-02', 100000, 'pending',
   'Eastspring Asset Management (Thailand)', 'thai_esg_equity', 'TDEX.BK',
   'Bought by Tho himself (ordered 30 Oct, effective/allotted 2 Nov 2026). Units = 100,000 / allotment NAV of 2 Nov - pending his confirmation. ThaiESG: hold >= 5 years counted day-to-day from purchase.'),
  ('TDSThaiESG-A', 'ThaiESG', DATE '2026-10-30', DATE '2026-11-02', DATE '2031-11-02', 100000, 'pending',
   'TISCO Asset Management', 'thai_esg_equity', 'TDEX.BK',
   'Bought by Tho himself (ordered 30 Oct, effective/allotted 2 Nov 2026). Units = 100,000 / allotment NAV of 2 Nov - pending his confirmation. ThaiESG: hold >= 5 years counted day-to-day from purchase.')
ON CONFLICT (ticker) DO NOTHING;
