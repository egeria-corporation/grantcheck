# check.opengrants.io

The hosted companion to [grantcheck](../README.md). One permanent, citable page per
organization, rendered at the edge from D1.

Same rules, same data, same code path as the CLI — `site/src/report.ts` reimplements the
eleven checks because the edge cannot run Python, and `test/parity.test.ts` asserts its
output is byte-identical to `grantcheck --format json`. When the two disagree, CI fails.

Why edge SSR rather than a static build: [ADR-001](docs/ADR-001-edge-ssr.md).

## What is open and what is not

Open to everyone, no account, fully crawlable:

- `/ein/:ein` — the report page for one organization
- `/api/check/:ein` — the same report as JSON, CORS open, no key
- `/checks/:id`, `/methodology`, `/data`, `/llms.txt`

Behind a sign-in:

- `/roster` — saved organizations, re-checked monthly
- `/bulk` — up to 200 EINs in one pass
- `/roster/export.csv`
- `/account`

The split is deliberate and narrow: **signing in must never be the price of an answer.** A
page a crawler cannot read is a page no model can cite, which is the entire reason this site
exists. What is gated is only what has to remember something between visits. See D-004 in
`_shared/DECISIONS.md`, including the privacy exception a saved roster creates and the limits
placed on it.

Sign-in is a magic link. There are no passwords, the database stores a SHA-256 of each token
and never the token itself, and links are single-use with a fifteen-minute expiry.

## Development

```bash
pnpm install
```

Create the local database and fill it with real organizations:

```bash
pnpm run db:seed:local
```

```bash
python scripts/seed_from_index.py && npx wrangler d1 execute grantcheck --local --file=./seed.sql
```

The seed script needs `zstandard`, which the library's own virtualenv already has — run it
with `../.venv/Scripts/python.exe` (Windows) or `../.venv/bin/python` if it is not on your
path. It samples a few thousand organizations from the published index and pins the EINs the
docs and demos reference, so a seeded site never 404s on its own examples.

```bash
pnpm dev
```

With no mail provider configured, sign-in links are printed to the dev server's output
instead of being sent. Copy the link from the log to complete a sign-in locally.

## Gates

```bash
pnpm run check && pnpm test
```

`check` is biome plus `tsc --noEmit`; `test` runs the parity suite and the account tests. The
account tests run against real SQLite through a small D1 adapter (`test/d1.ts`) rather than a
mock, so constraints, joins and scoping are exercised for real.

## Deploying

1. **Schema and data.**

   ```bash
   npx wrangler d1 execute grantcheck --remote --file=./schema.sql
   ```

   Then load the organization data. Confirm the current D1 size limit against the index's row
   count first — at the time of writing that is 3.27M organizations, and if it does not fit,
   the fallback is sharding by EIN prefix across several databases with the query layer
   routing between them.

2. **Custom domain.** `check.opengrants.io` is declared in `wrangler.jsonc` and must also be
   bound in the Cloudflare dashboard.

3. **Mail.** Set both, or sign-in links are logged and never delivered:

   ```bash
   npx wrangler secret put RESEND_API_KEY
   ```

   ```bash
   npx wrangler secret put MAIL_FROM
   ```

   Cloudflare Email Routing only receives mail, so it cannot be used for this. Any provider
   works — `src/mailer.ts` is a two-method interface and Resend is one `fetch`.

4. **Deploy.**

   ```bash
   pnpm run deploy
   ```

Monitoring runs from a cron trigger on the 8th at 14:00 UTC, after the monthly ingest has had
time to land. It re-checks every saved organization and emails only the accounts whose
verdicts actually changed — a month in which nothing moves sends nothing at all.

## Before real accounts exist

The privacy policy is written and served at `/privacy`, but **two placeholders in
`src/views/privacy.tsx` must be filled first** — they are together in `PRIVACY_CONTACT`:

- `email` — must be a real, monitored mailbox. It is where access, correction and deletion
  requests arrive, and several state privacy laws require a working channel.
- `postal` — the CCPA requires a postal address for a business serving California residents,
  which this one will.

The policy makes specific negative claims — no analytics, one cookie, two service providers,
no sale or sharing, no request logs. Each is true of the code today and each is checkable.
**Re-read it against the code before adding any dependency that talks to a third party**, and
before turning invocation logging back on in `wrangler.jsonc`.
