-- 2026-11-07: shadow log table for the two-sided news-impact model (ai_engine/news_impact.py).
-- ADDITIVE ONLY: one new table, no existing table changed, no deletes.
-- NOT RUN BY THE ASSISTANT. The owner reviews and runs it.
-- Before running: back up investor_db, e.g.
--   pg_dump -Fc -d investor_db -f ~/backups/investor_db/investor_db.pre_news_impact.$(date +%Y%m%d-%H%M%S).dump
-- Until this table exists, shadow records are written to data/shadow/news_impact_shadow.jsonl.
-- Rollback (only if you choose): DROP TABLE news_impact_shadow;  (owner decision, not automatic)

CREATE TABLE IF NOT EXISTS news_impact_shadow (
    id              BIGSERIAL PRIMARY KEY,
    article_id      UUID REFERENCES news_articles(id) ON DELETE SET NULL,
    headline_date   DATE NOT NULL,
    sector          VARCHAR(40) NOT NULL,
    proxy           VARCHAR(20) NOT NULL,
    direction       SMALLINT NOT NULL CHECK (direction IN (1, -1)),   -- +1 UP, -1 DOWN
    status          VARCHAR(10) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'scored')),
    reaction_day    DATE,
    signed_return_d0   NUMERIC(10,6),   -- direction x proxy close-to-close return, reaction day
    signed_return_d1   NUMERIC(10,6),
    signed_return_d2   NUMERIC(10,6),
    decayed_score   NUMERIC(10,6),      -- weights from config/news_impact_rules.json
    rules_version   VARCHAR(40) NOT NULL DEFAULT 'v1_2026-11-07',
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (article_id, sector, direction, rules_version)
);

CREATE INDEX IF NOT EXISTS idx_news_impact_shadow_date ON news_impact_shadow (headline_date DESC);
