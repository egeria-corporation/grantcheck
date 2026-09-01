-- D1 schema for check.opengrants.io.
--
-- The organization table mirrors the Python index shard schema exactly, because both are
-- produced by the same ingest. The two surfaces can therefore disagree only about
-- interpretation, never about the underlying data — and the JSON parity test in CI covers
-- interpretation.

CREATE TABLE IF NOT EXISTS organization (
  ein                      TEXT PRIMARY KEY,
  in_bmf                   INTEGER NOT NULL DEFAULT 0,
  in_pub78                 INTEGER NOT NULL DEFAULT 0,
  in_revocation            INTEGER NOT NULL DEFAULT 0,
  in_epostcard             INTEGER NOT NULL DEFAULT 0,
  name                     TEXT,
  sort_name                TEXT,
  city                     TEXT,
  state                    TEXT,
  zip                      TEXT,
  group_exemption          TEXT,
  affiliation              TEXT,
  subsection               TEXT,
  classification           TEXT,
  ruling                   TEXT,
  deductibility            TEXT,
  foundation               TEXT,
  organization_form        TEXT,
  exempt_status            TEXT,
  tax_period               TEXT,
  filing_req_cd            TEXT,
  pf_filing_req_cd         TEXT,
  acct_pd                  TEXT,
  ntee_cd                  TEXT,
  pub78_deductibility_code TEXT,
  revocation_date          TEXT,
  revocation_posting_date  TEXT,
  reinstatement_date       TEXT,
  epostcard_tax_year       TEXT,
  epostcard_period_end     TEXT,
  uei                      TEXT,
  sam_status               TEXT,
  sam_expiration           TEXT,
  sam_purpose              TEXT,
  sam_match_confidence     REAL,
  sam_match_method         TEXT
);

CREATE INDEX IF NOT EXISTS idx_org_state_name ON organization(state, name);
CREATE INDEX IF NOT EXISTS idx_org_name ON organization(name);

-- Updated last by the ingest, and it is the cache-invalidation key: every edge cache entry
-- carries these dates, so a new ingest invalidates the whole cache in one step.
CREATE TABLE IF NOT EXISTS dataset_vintage (
  dataset    TEXT PRIMARY KEY,
  published  TEXT NOT NULL,
  source_url TEXT NOT NULL,
  row_count  INTEGER
);

-- ---------------------------------------------------------------------------------------
-- Accounts. The public report pages need none of this: reports, explainers and the JSON API
-- are open and crawlable, which is what makes them worth indexing and citing. An account
-- unlocks the workflow — checking a roster in one go, being told when something changes,
-- and exporting. Those have no search value and genuinely need an address.
-- ---------------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS account (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  verified_at TEXT
);

-- Magic links: no passwords to store, hash, reset, or leak. The token column holds a hash
-- of the token, never the token itself, so a database disclosure does not hand out live
-- sessions.
CREATE TABLE IF NOT EXISTS login_token (
  token_hash TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES account(id),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at    TEXT
);

CREATE TABLE IF NOT EXISTS session (
  token_hash TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES account(id),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

-- A saved roster. This is the one place the site joins a person to a set of EINs, which the
-- architecture's privacy section otherwise forbids — a deliberate, scoped exception that
-- exists because monitoring cannot work without it. Deleting the account deletes the rows.
CREATE TABLE IF NOT EXISTS roster_entry (
  account_id TEXT NOT NULL REFERENCES account(id),
  ein        TEXT NOT NULL,
  label      TEXT,
  added_at   TEXT NOT NULL,
  PRIMARY KEY (account_id, ein)
);

CREATE INDEX IF NOT EXISTS idx_roster_account ON roster_entry(account_id);
