/**
 * Monitoring.
 *
 * The claim on the sign-in page is narrow and specific: *you get an email only when a
 * verdict actually changes*. A monitoring job that mails people every month regardless is
 * the ordinary way that promise gets broken, so the "sends nothing" cases matter more here
 * than the "sends something" ones.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { accountForSession, issueLoginToken, redeemLoginToken } from "../src/auth";
import { alertEmail, purgeExpired, runMonitoring } from "../src/monitor";
import { type TestD1, testDb } from "./d1";

let db: TestD1 & D1Database;
let sent: Array<{ to: string; subject: string; text: string }>;

/**
 * Capture outbound mail. With no provider configured the mailer logs to the console, so
 * spying on console.log is what makes the sends observable without wiring a fake provider
 * through the env.
 */
function captureMail() {
  sent = [];
  vi.spyOn(console, "log").mockImplementation((line: unknown) => {
    const text = String(line);
    const to = /^to: (.+)$/m.exec(text)?.[1] ?? "";
    const subject = /^subject: (.+)$/m.exec(text)?.[1] ?? "";
    sent.push({ to, subject, text });
  });
}

const ORG = {
  ein: "271067272",
  name: "CODE FOR AMERICA LABS INC",
  city: "SAN FRANCISCO",
  state: "CA",
  subsection: "03",
  classification: "1000",
  affiliation: "3",
  deductibility: "1",
  foundation: "15",
  organization_form: "1",
  exempt_status: "01",
  tax_period: "202412",
  filing_req_cd: "01",
  ntee_cd: "W20",
  pub78_deductibility_code: "PC",
};

async function seedOrg(overrides: Record<string, unknown> = {}) {
  const row = { ...ORG, ...overrides };
  const cols = Object.keys(row);
  await db
    .prepare(
      `INSERT OR REPLACE INTO organization (${cols.join(",")}, in_bmf, in_pub78) ` +
        `VALUES (${cols.map(() => "?").join(",")}, 1, 1)`,
    )
    .bind(...Object.values(row))
    .run();
}

async function account(email: string): Promise<string> {
  const token = await issueLoginToken(db, email, "Ada");
  const result = await redeemLoginToken(db, token);
  if (!result) throw new Error("redeem failed");
  return result.account.id;
}

async function save(accountId: string, ein: string, lastReadiness: string | null = null) {
  await db
    .prepare(
      "INSERT INTO roster_entry (account_id, ein, added_at, last_readiness) VALUES (?, ?, ?, ?)",
    )
    .bind(accountId, ein, new Date().toISOString(), lastReadiness)
    .run();
}

beforeEach(async () => {
  db = testDb();
  captureMail();
  await seedOrg();
  await db
    .prepare("INSERT INTO dataset_vintage (dataset, published, source_url) VALUES (?, ?, ?)")
    .bind("bmf", "2026-08-10", "https://www.irs.gov/")
    .run();
});

describe("when nothing changed", () => {
  it("sends nothing", async () => {
    const id = await account("ada@example.org");
    await save(id, "271067272", "ready");
    const result = await runMonitoring({ DB: db });
    expect(result.checked).toBe(1);
    expect(result.notified).toBe(0);
    expect(sent).toHaveLength(0);
  });

  it("sends nothing on the first pass over a new entry", async () => {
    const id = await account("ada@example.org");
    await save(id, "271067272", null);
    // Adding an organization must not immediately email a "change" that is only the first
    // reading of it.
    await runMonitoring({ DB: db });
    expect(sent).toHaveLength(0);
  });

  it("records the baseline on that first pass", async () => {
    const id = await account("ada@example.org");
    await save(id, "271067272", null);
    await runMonitoring({ DB: db });
    const row = db.one<{ last_readiness: string; last_checked_at: string }>(
      "SELECT * FROM roster_entry",
    );
    expect(row.last_readiness).toBe("ready");
    expect(row.last_checked_at).toBeTruthy();
  });

  it("sends nothing when there is no roster at all", async () => {
    const result = await runMonitoring({ DB: db });
    expect(result).toEqual({ checked: 0, notified: 0 });
  });
});

describe("when a verdict moves", () => {
  it("emails the account", async () => {
    const id = await account("ada@example.org");
    await save(id, "271067272", "ready");
    // Revoked since last month: a hard stop, and exactly what monitoring is for.
    await seedOrg({ revocation_date: "2026-07-15" });
    await db
      .prepare("UPDATE organization SET in_revocation = 1 WHERE ein = ?")
      .bind("271067272")
      .run();

    const result = await runMonitoring({ DB: db });

    expect(result.notified).toBe(1);
    expect(sent).toHaveLength(1);
    expect(sent[0]?.to).toBe("ada@example.org");
    expect(sent[0]?.text).toContain("CODE FOR AMERICA LABS INC");
  });

  it("stores the new verdict so the next run does not repeat the alert", async () => {
    const id = await account("ada@example.org");
    await save(id, "271067272", "blocked");

    await runMonitoring({ DB: db }); // blocked -> ready, one alert
    expect(sent).toHaveLength(1);

    await runMonitoring({ DB: db }); // nothing moved, silence
    expect(sent).toHaveLength(1);
  });

  it("sends one email per account, not one per organization", async () => {
    const id = await account("ada@example.org");
    await seedOrg({ ein: "131644147", name: "SECOND ORG" });
    await seedOrg({ ein: "530196605", name: "THIRD ORG" });
    await save(id, "271067272", "blocked");
    await save(id, "131644147", "blocked");
    await save(id, "530196605", "blocked");

    const result = await runMonitoring({ DB: db });

    expect(result.notified).toBe(1);
    expect(sent).toHaveLength(1);
    expect(sent[0]?.text).toContain("CODE FOR AMERICA LABS INC");
    expect(sent[0]?.text).toContain("SECOND ORG");
    expect(sent[0]?.text).toContain("THIRD ORG");
  });

  it("emails each affected account separately", async () => {
    const ada = await account("ada@example.org");
    const eve = await account("eve@example.org");
    await save(ada, "271067272", "blocked");
    await save(eve, "271067272", "blocked");

    await runMonitoring({ DB: db });

    expect(sent.map((m) => m.to).sort()).toEqual(["ada@example.org", "eve@example.org"]);
  });

  it("leaves an unaffected account alone", async () => {
    const ada = await account("ada@example.org");
    const eve = await account("eve@example.org");
    await save(ada, "271067272", "blocked"); // moves
    await save(eve, "271067272", "ready"); // does not

    await runMonitoring({ DB: db });

    expect(sent.map((m) => m.to)).toEqual(["ada@example.org"]);
  });

  it("handles an entry whose organization is not in the index", async () => {
    const id = await account("ada@example.org");
    await save(id, "131644147", "ready");
    // The LEFT JOIN yields nulls; the run must complete rather than throw.
    const result = await runMonitoring({ DB: db });
    expect(result.checked).toBe(1);
    expect(sent[0]?.text).toContain("13-1644147");
  });
});

describe("the alert email", () => {
  it("leads with the count of newly blocked organizations", () => {
    const mail = alertEmail(
      [{ ein: "271067272", name: "SOME ORG", from: "ready", to: "blocked", headline: "Revoked" }],
      "2026-08-10",
    );
    expect(mail.subject).toContain("1 organization");
    expect(mail.subject).toContain("blocked");
  });

  it("says what changed, in both directions, with a link", () => {
    const mail = alertEmail(
      [{ ein: "271067272", name: "SOME ORG", from: "blocked", to: "ready", headline: "Clear" }],
      "2026-08-10",
    );
    expect(mail.text).toContain("SOME ORG");
    expect(mail.text).toContain("27-1067272");
    expect(mail.text).toContain("https://check.opengrants.io/ein/27-1067272");
  });

  it("carries the disclosure and a way to stop", () => {
    const mail = alertEmail(
      [{ ein: "271067272", name: "X", from: "ready", to: "attention", headline: "y" }],
      "2026-08-10",
    );
    expect(mail.text).toContain("not an eligibility");
    expect(mail.text).toContain("/account");
  });

  it("names the vintage that triggered it", () => {
    const mail = alertEmail(
      [{ ein: "271067272", name: "X", from: "ready", to: "attention", headline: "y" }],
      "2026-08-10",
    );
    expect(mail.text).toContain("2026-08-10");
  });
});

describe("purging spent credentials", () => {
  it("deletes a login token the moment it has been used", async () => {
    const token = await issueLoginToken(db, "ada@example.org", "Ada");
    await redeemLoginToken(db, token);
    expect(db.raw("SELECT * FROM login_token")).toHaveLength(1);

    await purgeExpired({ DB: db });

    // A used token is a dead credential. Keeping it serves nothing.
    expect(db.raw("SELECT * FROM login_token")).toHaveLength(0);
  });

  it("deletes an expired but unused login token", async () => {
    await issueLoginToken(db, "ada@example.org", "Ada");
    const past = new Date(Date.now() - 60_000).toISOString();
    db.exec(`UPDATE login_token SET expires_at = '${past}'`);

    await purgeExpired({ DB: db });

    expect(db.raw("SELECT * FROM login_token")).toHaveLength(0);
  });

  it("leaves a live login token alone", async () => {
    await issueLoginToken(db, "ada@example.org", "Ada");
    await purgeExpired({ DB: db });
    // Purging must not log out somebody mid-sign-in.
    expect(db.raw("SELECT * FROM login_token")).toHaveLength(1);
  });

  it("leaves a live session alone", async () => {
    const token = await issueLoginToken(db, "ada@example.org", "Ada");
    const result = await redeemLoginToken(db, token);

    await purgeExpired({ DB: db });

    expect(await accountForSession(db, result?.sessionToken)).not.toBeNull();
  });

  it("deletes a session expired beyond the grace period", async () => {
    const token = await issueLoginToken(db, "ada@example.org", "Ada");
    await redeemLoginToken(db, token);
    const longAgo = new Date(Date.now() - 30 * 24 * 3600_000).toISOString();
    db.exec(`UPDATE session SET expires_at = '${longAgo}'`);

    await purgeExpired({ DB: db });

    expect(db.raw("SELECT * FROM session")).toHaveLength(0);
  });

  it("keeps a just-expired session through the grace period", async () => {
    const token = await issueLoginToken(db, "ada@example.org", "Ada");
    const result = await redeemLoginToken(db, token);
    const justNow = new Date(Date.now() - 1000).toISOString();
    db.exec(`UPDATE session SET expires_at = '${justNow}'`);

    await purgeExpired({ DB: db });

    // The row survives, but it still does not authenticate anyone - expiry is enforced on
    // read, not by deletion, so the grace period cannot extend a session by accident.
    expect(db.raw("SELECT * FROM session")).toHaveLength(1);
    expect(await accountForSession(db, result?.sessionToken)).toBeNull();
  });

  it("never touches accounts or rosters", async () => {
    const id = await account("ada@example.org");
    await save(id, "271067272", "ready");

    await purgeExpired({ DB: db });

    expect(db.raw("SELECT * FROM account")).toHaveLength(1);
    expect(db.raw("SELECT * FROM roster_entry")).toHaveLength(1);
  });
});
