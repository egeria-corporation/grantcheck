/**
 * Everything behind a session: sign-in, roster, bulk check, export, deletion.
 *
 * Mounted as one router so the boundary is legible — anything in this file may require an
 * account, and nothing outside it does. Report pages, explainers and the JSON API live in
 * `index.tsx` and stay open, which is the whole point of the split.
 */

import { Hono } from "hono";
import { getCookie } from "hono/cookie";
import { createMiddleware } from "hono/factory";
import type { Account } from "../auth";
import {
  LOGIN_TOKEN_TTL_MINUTES,
  SESSION_COOKIE,
  accountForSession,
  clearedCookie,
  deleteAccount,
  endSession,
  issueLoginToken,
  looksLikeEmail,
  normalizeEmail,
  redeemLoginToken,
  sessionCookie,
} from "../auth";
import { mailerFor, signInEmail } from "../mailer";
import type { OrgRow, Vintage } from "../report";
// One definition, imported rather than copied: two EIN validators drift, and this one
// decides what a roster is allowed to hold.
import { buildReport, formatEin, normalizeEin } from "../report";
import type { RosterRow } from "../views/account";
import { AccountPage, Bulk, Join, LinkExpired, LinkSent, Roster, headline } from "../views/account";

export type Bindings = {
  DB: D1Database;
  RESEND_API_KEY?: string;
  MAIL_FROM?: string;
};

type Vars = { account: Account };

export const accountRoutes = new Hono<{ Bindings: Bindings; Variables: Vars }>();

/** At most this many organizations per bulk paste. */
const BULK_LIMIT = 200;

/** Sign-in links per address per window, before we stop sending. */
const LINK_RATE_LIMIT = 3;

const MAX_ROSTER = 500;

/**
 * Only same-site, absolute-path redirects.
 *
 * `next` arrives from a query string and a hidden form field, so it is attacker-controlled.
 * Without this, `/join?next=https://evil.example` turns our sign-in flow into a credible
 * redirect to somebody else's page — and `//evil.example` is protocol-relative, so checking
 * only the leading slash is not enough.
 */
function safeNext(value: string | undefined, fallback: string): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return fallback;
  return value;
}

/** True on real deployments, false on `wrangler dev` over plain http. */
function isSecure(url: string): boolean {
  return new URL(url).protocol === "https:";
}

async function vintages(db: D1Database): Promise<Record<string, Vintage>> {
  const { results } = await db
    .prepare("SELECT dataset, published, source_url FROM dataset_vintage")
    .all<Vintage>();
  return Object.fromEntries((results ?? []).map((v) => [v.dataset, v]));
}

/**
 * The gate. Signed out, this bounces to sign-in remembering where you were headed, so
 * following a bookmark to /roster does not silently dump you on a marketing page.
 *
 * Attached to an explicit list of paths rather than `*`. Hono applies a middleware to every
 * route registered after it, so a wildcard here reaches out of this file and gates whatever
 * happens to be declared later in `index.tsx` — which is exactly how /robots.txt started
 * redirecting to sign-in. Naming the guarded paths keeps the gate somewhere it can be read,
 * and makes adding a public route to the app impossible to get wrong by accident.
 */
const requireAccount = createMiddleware<{ Bindings: Bindings; Variables: Vars }>(
  async (c, next) => {
    const account = await accountForSession(c.env.DB, getCookie(c, SESSION_COOKIE));
    if (!account) {
      const path = new URL(c.req.url).pathname;
      return c.redirect(`/join?next=${encodeURIComponent(path)}`, 302);
    }
    c.set("account", account);
    // Never cached, never indexed. These pages are per-account by definition.
    c.header("Cache-Control", "private, no-store");
    return next();
  },
);

const GATED = ["/roster", "/roster/*", "/bulk", "/account", "/account/*", "/logout"];
for (const path of GATED) accountRoutes.use(path, requireAccount);

// ---------------------------------------------------------------------------------------
// Sign in
// ---------------------------------------------------------------------------------------

accountRoutes.get("/join", async (c) => {
  // Already signed in? Go where you were headed rather than filling in the form again.
  if (await accountForSession(c.env.DB, getCookie(c, SESSION_COOKIE))) {
    return c.redirect(safeNext(c.req.query("next"), "/roster"), 302);
  }
  c.header("Cache-Control", "private, no-store");
  return c.html(<Join next={c.req.query("next")} />);
});

accountRoutes.post("/join", async (c) => {
  const body = await c.req.parseBody();
  const email = String(body.email ?? "");
  const name = String(body.name ?? "");
  const next = safeNext(String(body.next ?? ""), "/roster");

  if (!looksLikeEmail(email)) {
    return c.html(
      <Join next={next} email={email} error="That does not look like an email address." />,
    );
  }
  if (name.trim().length === 0) {
    return c.html(<Join next={next} email={email} error="Please give a name." />);
  }

  const normalized = normalizeEmail(email);

  // Rate limit per address. Without this the form is a free, authenticated-looking mail
  // relay: anyone can point it at somebody else's inbox and hold down the button.
  const since = new Date(Date.now() - LOGIN_TOKEN_TTL_MINUTES * 60_000).toISOString();
  const recent = await c.env.DB.prepare(
    "SELECT COUNT(*) AS n FROM login_token WHERE email = ? AND created_at > ?",
  )
    .bind(normalized, since)
    .first<{ n: number }>();

  if ((recent?.n ?? 0) >= LINK_RATE_LIMIT) {
    // Same page as success. Saying "too many" would confirm the address is being targeted.
    return c.html(<LinkSent email={normalized} />);
  }

  const token = await issueLoginToken(c.env.DB, normalized, name);
  const url = new URL(c.req.url);
  const link = `${url.origin}/auth/verify?token=${token}&next=${encodeURIComponent(next)}`;
  const mail = signInEmail(link, LOGIN_TOKEN_TTL_MINUTES);
  await mailerFor(c.env).send({ to: normalized, subject: mail.subject, text: mail.text });

  c.header("Cache-Control", "private, no-store");
  return c.html(<LinkSent email={normalized} />);
});

accountRoutes.get("/auth/verify", async (c) => {
  const token = c.req.query("token");
  if (!token) return c.html(<LinkExpired />, 400);

  const result = await redeemLoginToken(c.env.DB, token);
  if (!result) return c.html(<LinkExpired />, 400);

  c.header("Set-Cookie", sessionCookie(result.sessionToken, isSecure(c.req.url)));
  return c.redirect(safeNext(c.req.query("next"), "/roster"), 302);
});

accountRoutes.post("/logout", async (c) => {
  await endSession(c.env.DB, getCookie(c, SESSION_COOKIE));
  c.header("Set-Cookie", clearedCookie(isSecure(c.req.url)));
  return c.redirect("/", 302);
});

// ---------------------------------------------------------------------------------------
// Roster
// ---------------------------------------------------------------------------------------

async function rosterRows(db: D1Database, accountId: string): Promise<RosterRow[]> {
  const v = await vintages(db);
  const { results } = await db
    .prepare(
      // Aliased, not "r.ein, ..., o.*": duplicate column names collapse to the LAST one, so
      // an unaliased r.ein is silently replaced by o.ein - which is NULL for exactly the
      // rows this LEFT JOIN exists to keep.
      "SELECT o.*, r.ein AS roster_ein, r.label AS roster_label, r.added_at AS roster_added " +
        "FROM roster_entry r LEFT JOIN organization o ON o.ein = r.ein " +
        "WHERE r.account_id = ? ORDER BY r.added_at",
    )
    .bind(accountId)
    .all<OrgRow & { roster_ein: string; roster_label: string | null; roster_added: string }>();

  return (results ?? []).map((row) => {
    // A LEFT JOIN with no match still yields the roster columns, with every organization
    // column null. `name` is the tell: an EIN saved before it appeared in the index, or one
    // dropped by a later ingest, is a legitimate state and must render, not throw.
    const org = row.name === null ? null : ({ ...row, ein: row.roster_ein } as OrgRow);
    const report = buildReport(org, row.roster_ein, v, new Date());
    return {
      ein: row.roster_ein,
      label: row.roster_label,
      added_at: row.roster_added,
      name: row.name,
      city: row.city,
      state: row.state,
      readiness: report.readiness,
      headline: headline(report),
    };
  });
}

accountRoutes.get("/roster", async (c) => {
  const account = c.get("account");
  const rows = await rosterRows(c.env.DB, account.id);
  return c.html(
    <Roster
      name={account.name}
      rows={rows}
      added={c.req.query("added")}
      notice={c.req.query("notice")}
    />,
  );
});

accountRoutes.post("/roster/add", async (c) => {
  const account = c.get("account");
  const body = await c.req.parseBody();
  const ein = normalizeEin(String(body.ein ?? ""));
  const label = String(body.label ?? "")
    .trim()
    .slice(0, 80);
  const back = safeNext(String(body.next ?? ""), "/roster");

  if (!ein) {
    return c.redirect(`${back}?notice=${encodeURIComponent("That is not a nine-digit EIN.")}`, 302);
  }

  const count = await c.env.DB.prepare(
    "SELECT COUNT(*) AS n FROM roster_entry WHERE account_id = ?",
  )
    .bind(account.id)
    .first<{ n: number }>();
  if ((count?.n ?? 0) >= MAX_ROSTER) {
    const message = `A roster holds ${MAX_ROSTER} organizations. Remove one, or use the CLI, which has no limit.`;
    return c.redirect(`${back}?notice=${encodeURIComponent(message)}`, 302);
  }

  await c.env.DB.prepare(
    "INSERT OR IGNORE INTO roster_entry (account_id, ein, label, added_at) VALUES (?, ?, ?, ?)",
  )
    .bind(account.id, ein, label || null, new Date().toISOString())
    .run();

  return c.redirect(`${back}?added=${encodeURIComponent(formatEin(ein))}`, 302);
});

accountRoutes.post("/roster/remove", async (c) => {
  const account = c.get("account");
  const body = await c.req.parseBody();
  const ein = normalizeEin(String(body.ein ?? ""));
  if (ein) {
    // Scoped to the account in the WHERE clause, not checked beforehand: there is no window
    // in which one account can delete another's row.
    await c.env.DB.prepare("DELETE FROM roster_entry WHERE account_id = ? AND ein = ?")
      .bind(account.id, ein)
      .run();
  }
  return c.redirect("/roster", 302);
});

/** RFC 4180. Quote everything and double any internal quote — names carry commas. */
function csvCell(value: string | null | undefined): string {
  const s = value ?? "";
  return `"${s.replace(/"/g, '""')}"`;
}

accountRoutes.get("/roster/export.csv", async (c) => {
  const account = c.get("account");
  const rows = await rosterRows(c.env.DB, account.id);
  const header = ["ein", "name", "city", "state", "label", "readiness", "finding", "added"];
  const lines = [
    header.join(","),
    ...rows.map((r) =>
      [
        csvCell(formatEin(r.ein)),
        csvCell(r.name),
        csvCell(r.city),
        csvCell(r.state),
        csvCell(r.label),
        csvCell(r.readiness),
        csvCell(r.headline),
        csvCell(r.added_at.slice(0, 10)),
      ].join(","),
    ),
  ];
  const today = new Date().toISOString().slice(0, 10);
  // The BOM is for Excel, which otherwise reads UTF-8 as the local codepage and mangles
  // every accented organization name in the file. Written as an escape, not a literal
  // character: a bare U+FEFF in source is invisible and does not survive every editor.
  return c.body(`\uFEFF${lines.join("\r\n")}\r\n`, 200, {
    "Content-Type": "text/csv; charset=utf-8",
    "Content-Disposition": `attachment; filename="grantcheck-roster-${today}.csv"`,
  });
});

// ---------------------------------------------------------------------------------------
// Bulk check
// ---------------------------------------------------------------------------------------

/** Split a paste on any plausible separator; report what could not be read as an EIN. */
export function parseEinList(raw: string): { eins: string[]; unparsed: string[]; extra: number } {
  const tokens = raw
    .split(/[,;\r\n\t]+/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0);

  const eins: string[] = [];
  const unparsed: string[] = [];
  const seen = new Set<string>();
  for (const token of tokens) {
    const ein = normalizeEin(token);
    if (!ein) {
      unparsed.push(token.slice(0, 24));
    } else if (!seen.has(ein)) {
      seen.add(ein);
      eins.push(ein);
    }
  }
  return {
    eins: eins.slice(0, BULK_LIMIT),
    unparsed,
    extra: Math.max(0, eins.length - BULK_LIMIT),
  };
}

accountRoutes.get("/bulk", (c) => c.html(<Bulk />));

accountRoutes.post("/bulk", async (c) => {
  const body = await c.req.parseBody();
  const raw = String(body.eins ?? "");
  const { eins, unparsed, extra } = parseEinList(raw);

  if (eins.length === 0) {
    return c.html(<Bulk raw={raw} unparsed={unparsed} />);
  }

  const v = await vintages(c.env.DB);
  // One query for the whole list rather than one per EIN. At 200 rows the difference is
  // 200 D1 round trips against one, which is the difference between usable and not.
  const placeholders = eins.map(() => "?").join(",");
  const { results } = await c.env.DB.prepare(
    `SELECT * FROM organization WHERE ein IN (${placeholders})`,
  )
    .bind(...eins)
    .all<OrgRow>();
  const byEin = new Map((results ?? []).map((r) => [r.ein, r]));

  const reports = eins.map((ein) => ({
    ein,
    report: buildReport(byEin.get(ein) ?? null, ein, v, new Date()),
  }));

  return c.html(<Bulk raw={raw} reports={reports} unparsed={unparsed} truncated={extra} />);
});

// ---------------------------------------------------------------------------------------
// Account
// ---------------------------------------------------------------------------------------

accountRoutes.get("/account", async (c) => {
  const account = c.get("account");
  const count = await c.env.DB.prepare(
    "SELECT COUNT(*) AS n FROM roster_entry WHERE account_id = ?",
  )
    .bind(account.id)
    .first<{ n: number }>();
  return c.html(
    <AccountPage
      name={account.name}
      email={account.email}
      created={account.created_at}
      rosterCount={count?.n ?? 0}
    />,
  );
});

accountRoutes.post("/account/delete", async (c) => {
  const account = c.get("account");
  const body = await c.req.parseBody();
  if (
    String(body.confirm ?? "")
      .trim()
      .toUpperCase() !== "DELETE"
  ) {
    const count = await c.env.DB.prepare(
      "SELECT COUNT(*) AS n FROM roster_entry WHERE account_id = ?",
    )
      .bind(account.id)
      .first<{ n: number }>();
    return c.html(
      <AccountPage
        name={account.name}
        email={account.email}
        created={account.created_at}
        rosterCount={count?.n ?? 0}
        error="Type DELETE exactly to confirm. Nothing was deleted."
      />,
      400,
    );
  }
  await deleteAccount(c.env.DB, account.id);
  c.header("Set-Cookie", clearedCookie(isSecure(c.req.url)));
  return c.redirect("/", 302);
});
