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
  sam_match_method         TEXT,
  -- Which published index vintage last wrote this row. The monthly refresh stamps every
  -- row it writes and then deletes whatever it did not touch, which is how organizations
  -- the IRS has dropped stop being reported on. Without it a removed organization would
  -- linger in D1 forever, and the site would answer for a record the CLI no longer has.
  vintage                  TEXT
);

CREATE INDEX IF NOT EXISTS idx_org_state_name ON organization(state, name);
CREATE INDEX IF NOT EXISTS idx_org_name ON organization(name);

-- Full-text search over organization names.
--
-- The obvious query, `name LIKE '%red cross%'`, cannot use an index: a leading wildcard
-- forces a full table scan. Measured on the real data that is ~6.5M rows read per search,
-- which exhausts a month's included reads in a few thousand queries and takes seconds.
--
-- `content='organization'` makes this an external-content index: it stores the search
-- structure but not a second copy of every name, and it is repopulated from the base table
-- after each monthly load.
--
-- NOT with the documented one-liner. `INSERT INTO organization_fts(organization_fts)
-- VALUES('rebuild')` builds the whole index inside a single statement, and over 3.3M rows
-- D1 rejects it: "D1 DB exceeded its CPU time limit and was reset". build_d1_import.py
-- emits the same work sliced by EIN prefix, preceded by a 'delete-all' so a re-run is
-- idempotent rather than doubling every entry.
--
-- There are deliberately NO triggers keeping this in sync. Nothing at runtime writes to
-- `organization` - it is a derived table, written only by the loader - so a trigger would
-- add a subtle failure mode for no benefit. Worse, `INSERT OR REPLACE` fires DELETE triggers
-- only when recursive_triggers is enabled, so a trigger-based design would silently
-- accumulate duplicate index entries on every monthly load. The loader rebuilds instead.
CREATE VIRTUAL TABLE IF NOT EXISTS organization_fts USING fts5(
  name,
  content='organization',
  tokenize='unicode61 remove_diacritics 2'
);

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
-- The email and name live HERE rather than in an account row, so that requesting a link
-- for an address creates nothing. An account exists only once somebody has proved they can
-- read that inbox. Otherwise anyone could manufacture account rows for arbitrary addresses,
-- and the sign-in email could not honestly say nothing was created.
CREATE TABLE IF NOT EXISTS login_token (
  token_hash TEXT PRIMARY KEY,
  email      TEXT NOT NULL,
  name       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_login_token_email ON login_token(email, created_at);

CREATE TABLE IF NOT EXISTS session (
  token_hash TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES account(id),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

-- A saved roster. This is the one place the site joins a person to a set of EINs, which the
-- architecture's privacy section otherwise forbids — a deliberate, scoped exception that
-- exists because monitoring cannot work without it. Deleting the account deletes the rows.
-- last_readiness is what monitoring compares against. Storing the verdict rather than
-- recomputing "what did it say last month" means an alert fires on an actual change, and a
-- month where the ingest did not move anything sends nothing at all.
CREATE TABLE IF NOT EXISTS roster_entry (
  account_id      TEXT NOT NULL REFERENCES account(id),
  ein             TEXT NOT NULL,
  label           TEXT,
  added_at        TEXT NOT NULL,
  last_readiness  TEXT,
  last_checked_at TEXT,
  PRIMARY KEY (account_id, ein)
);

CREATE INDEX IF NOT EXISTS idx_roster_account ON roster_entry(account_id);
