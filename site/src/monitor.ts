/**
 * Monthly roster monitoring.
 *
 * The promise made on the sign-in page is narrow and worth keeping narrow: *you get an
 * email only when a verdict actually changes*. So this compares each saved organization's
 * current readiness against the verdict stored when it was last looked at, and sends
 * nothing at all in a month where nothing moved — which will be most months, for most
 * rosters.
 *
 * A first pass over a newly added entry records the baseline and sends nothing. Otherwise
 * adding an organization would immediately email you a "change" that is just the initial
 * reading.
 */

import { mailerFor } from "./mailer";
import type { OrgRow, Vintage } from "./report";
import { buildReport, formatEin, verdictLabel } from "./report";

type Env = { DB: D1Database; RESEND_API_KEY?: string; MAIL_FROM?: string };

type Row = OrgRow & {
  account_id: string;
  roster_ein: string;
  roster_label: string | null;
  last_readiness: string | null;
  account_email: string;
  account_name: string;
};

export type Change = {
  ein: string;
  name: string | null;
  from: string;
  to: string;
  headline: string;
};

/** Only a move that changes what somebody would do is worth an email. */
function significant(before: string | null, after: string): boolean {
  if (before === null) return false; // first sighting: record the baseline, say nothing
  return before !== after;
}

function describe(change: Change): string {
  const who = change.name ?? `EIN ${formatEin(change.ein)}`;
  const from = verdictLabel(change.from);
  const to = verdictLabel(change.to);
  return `${who} (${formatEin(change.ein)})\n  ${from} -> ${to}\n  ${change.headline}\n  https://check.opengrants.io/ein/${formatEin(change.ein)}`;
}

export function alertEmail(changes: Change[], vintage: string): { subject: string; text: string } {
  const worsened = changes.filter((c) => c.to === "blocked").length;
  const subject =
    worsened > 0
      ? `grantcheck: ${worsened} organization${worsened === 1 ? "" : "s"} on your roster now blocked`
      : `grantcheck: ${changes.length} change${changes.length === 1 ? "" : "s"} on your roster`;

  return {
    subject,
    text: `The IRS published new data (${vintage}) and ${changes.length} organization${
      changes.length === 1 ? " on your roster changed" : "s on your roster changed"
    }:

${changes.map(describe).join("\n\n")}

Everything else on your roster is unchanged.

This is informational only, derived from public IRS data. It is not an eligibility
determination, and not legal, tax, or accounting advice. Verify against the official
source before relying on it.

Your roster: https://check.opengrants.io/roster

To stop these emails, remove organizations from your roster - monitoring only
reports on what you saved. To remove everything including your account, and have
it deleted immediately: https://check.opengrants.io/account

Replies to this message reach a person.
`,
  };
}

/**
 * Delete spent credentials.
 *
 * A login token is dead the moment it is used or expires, and a session is dead once it
 * expires, but nothing was removing either — so both tables grew without bound and every
 * row was a dead credential kept for no reason. Data that serves no purpose should not be
 * retained, and a retention statement in a privacy policy has to be true.
 *
 * Expired login tokens go immediately: fifteen minutes is the whole life of one, so there is
 * nothing to keep. Expired sessions get a short grace period, because a row that has just
 * expired is what distinguishes "your session ended" from "that session never existed" if
 * anyone ever has to look into a report of being logged out.
 */
export async function purgeExpired(env: Env, now = new Date()): Promise<number> {
  const cutoff = now.toISOString();
  const sessionCutoff = new Date(now.getTime() - 7 * 24 * 3600_000).toISOString();
  const results = await env.DB.batch([
    env.DB.prepare("DELETE FROM login_token WHERE expires_at < ? OR used_at IS NOT NULL").bind(
      cutoff,
    ),
    env.DB.prepare("DELETE FROM session WHERE expires_at < ?").bind(sessionCutoff),
  ]);
  return results.reduce((n, r) => n + ((r.meta as { changes?: number })?.changes ?? 0), 0);
}

/**
 * Re-check every saved organization and notify the accounts whose verdicts moved.
 *
 * One pass over the whole table, grouped by account, so a person with forty organizations
 * gets one email rather than forty.
 */
export async function runMonitoring(env: Env): Promise<{ checked: number; notified: number }> {
  const { results: vintageRows } = await env.DB.prepare(
    "SELECT dataset, published, source_url FROM dataset_vintage",
  ).all<Vintage>();
  const vintages = Object.fromEntries((vintageRows ?? []).map((v) => [v.dataset, v]));
  const published = Object.values(vintages)[0]?.published ?? new Date().toISOString().slice(0, 10);

  const { results } = await env.DB.prepare(
    // Every non-organization column is aliased: duplicate names collapse to the last one,
    // so an unaliased r.ein would be overwritten by o.ein, which is NULL on a join miss.
    "SELECT o.*, r.account_id, r.ein AS roster_ein, r.label AS roster_label, " +
      "r.last_readiness, a.email AS account_email, a.name AS account_name " +
      "FROM roster_entry r " +
      "JOIN account a ON a.id = r.account_id " +
      "LEFT JOIN organization o ON o.ein = r.ein " +
      "ORDER BY r.account_id",
  ).all<Row>();

  const rows = results ?? [];
  const byAccount = new Map<string, { email: string; changes: Change[] }>();
  const updates: D1PreparedStatement[] = [];
  const now = new Date();
  const checkedAt = now.toISOString();

  for (const row of rows) {
    // As in the roster view: a LEFT JOIN miss yields null organization columns, which is a
    // legitimate state (saved before the org appeared, or dropped by a later ingest).
    const org = row.name === null ? null : ({ ...row, ein: row.roster_ein } as OrgRow);
    const report = buildReport(org, row.roster_ein, vintages, now);

    if (significant(row.last_readiness, report.readiness)) {
      const blocking = report.checks.filter((c) => report.blocking_check_ids.includes(c.id));
      const attention = report.checks.filter(
        (c) => c.status === "warn" || (c.status === "fail" && !c.blocking),
      );
      const entry = byAccount.get(row.account_id) ?? { email: row.account_email, changes: [] };
      entry.changes.push({
        ein: row.roster_ein,
        name: row.name,
        // significant() has already ruled out null, but the type does not know that.
        from: row.last_readiness ?? "unknown",
        to: report.readiness,
        headline:
          blocking.length > 0
            ? blocking.map((c) => `${c.label}: ${c.value}`).join("; ")
            : attention.length > 0
              ? attention.map((c) => `${c.label}: ${c.value}`).join("; ")
              : "No mechanical barrier found.",
      });
      byAccount.set(row.account_id, entry);
    }

    updates.push(
      env.DB.prepare(
        "UPDATE roster_entry SET last_readiness = ?, last_checked_at = ? " +
          "WHERE account_id = ? AND ein = ?",
      ).bind(report.readiness, checkedAt, row.account_id, row.roster_ein),
    );
  }

  // D1 caps a batch; 50 at a time keeps well inside it and keeps one slow chunk from
  // holding up the rest.
  for (let i = 0; i < updates.length; i += 50) {
    await env.DB.batch(updates.slice(i, i + 50));
  }

  const mailer = mailerFor(env);
  let notified = 0;
  for (const { email, changes } of byAccount.values()) {
    const mail = alertEmail(changes, published);
    // Sequential, not Promise.all: a monitoring run is not latency-sensitive, and a burst
    // of parallel sends is exactly what gets a sending domain rate-limited.
    if (await mailer.send({ to: email, subject: mail.subject, text: mail.text })) notified += 1;
  }

  return { checked: rows.length, notified };
}
