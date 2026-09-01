/**
 * The account layer's security properties, pinned.
 *
 * Everything here is a claim the sign-in page or the privacy copy makes out loud. If one of
 * these fails, the site is telling somebody something untrue about their data, which is
 * worse than a broken feature.
 */

import { describe, expect, it } from "vitest";
import {
  LOGIN_TOKEN_TTL_MINUTES,
  accountForSession,
  clearedCookie,
  deleteAccount,
  endSession,
  hashToken,
  issueLoginToken,
  looksLikeEmail,
  newToken,
  normalizeEmail,
  redeemLoginToken,
  sessionCookie,
} from "../src/auth";
import { type TestD1, testDb } from "./d1";

type Db = TestD1 & D1Database;

async function signedIn(db: Db, email = "a@example.org", name = "Ada") {
  const token = await issueLoginToken(db, email, name);
  const result = await redeemLoginToken(db, token);
  if (!result) throw new Error("redeem failed");
  return result;
}

describe("tokens", () => {
  it("are unguessable and unique", () => {
    const tokens = new Set(Array.from({ length: 500 }, () => newToken()));
    expect(tokens.size).toBe(500);
    for (const t of tokens) expect(t).toMatch(/^[0-9a-f]{64}$/);
  });

  it("hash deterministically", async () => {
    expect(await hashToken("abc")).toBe(await hashToken("abc"));
    expect(await hashToken("abc")).not.toBe(await hashToken("abd"));
  });
});

describe("what the database holds", () => {
  it("never stores a login token in plaintext", async () => {
    const db = testDb();
    const token = await issueLoginToken(db, "a@example.org", "Ada");

    const rows = db.raw<{ token_hash: string }>("SELECT * FROM login_token");
    expect(rows).toHaveLength(1);
    expect(db.one<{ token_hash: string }>("SELECT * FROM login_token").token_hash).toBe(
      await hashToken(token),
    );

    // The strong form: the raw token appears nowhere in the entire table, in any column.
    expect(JSON.stringify(rows)).not.toContain(token);
  });

  it("never stores a session token in plaintext", async () => {
    const db = testDb();
    const { sessionToken } = await signedIn(db);
    const rows = db.raw("SELECT * FROM session");
    expect(JSON.stringify(rows)).not.toContain(sessionToken);
  });

  it("creates no account until the address is proved", async () => {
    const db = testDb();
    await issueLoginToken(db, "stranger@example.org", "Somebody Else");
    // The sign-in email promises exactly this: requesting a link creates nothing.
    expect(db.raw("SELECT * FROM account")).toHaveLength(0);
  });

  it("creates the account on redemption", async () => {
    const db = testDb();
    const { account } = await signedIn(db, "ada@example.org", "Ada Lovelace");
    const row = db.one<{ email: string; name: string; verified_at: string }>(
      "SELECT * FROM account",
    );
    expect(row.email).toBe("ada@example.org");
    expect(row.name).toBe("Ada Lovelace");
    expect(row.verified_at).toBeTruthy();
    expect(account.id).toBeTruthy();
  });

  it("reuses the account on a second sign-in rather than duplicating it", async () => {
    const db = testDb();
    const first = await signedIn(db, "ada@example.org", "Ada");
    const second = await signedIn(db, "ada@example.org", "A Different Name");
    expect(second.account.id).toBe(first.account.id);
    expect(db.raw("SELECT * FROM account")).toHaveLength(1);
    // The original name stands; a later sign-in must not silently rewrite it.
    expect(second.account.name).toBe("Ada");
  });
});

describe("login tokens", () => {
  it("cannot be redeemed twice", async () => {
    const db = testDb();
    const token = await issueLoginToken(db, "a@example.org", "Ada");
    expect(await redeemLoginToken(db, token)).not.toBeNull();
    // A link in a forwarded thread, a mail scanner log, or browser history is inert.
    expect(await redeemLoginToken(db, token)).toBeNull();
  });

  it("cannot be redeemed after expiry", async () => {
    const db = testDb();
    const token = await issueLoginToken(db, "a@example.org", "Ada");
    const past = new Date(Date.now() - 60_000).toISOString();
    db.exec(`UPDATE login_token SET expires_at = '${past}'`);
    expect(await redeemLoginToken(db, token)).toBeNull();
  });

  it("expire within the window the email promises", async () => {
    const db = testDb();
    await issueLoginToken(db, "a@example.org", "Ada");
    const row = db.one<{ created_at: string; expires_at: string }>("SELECT * FROM login_token");
    const minutes = (Date.parse(row.expires_at) - Date.parse(row.created_at)) / 60_000;
    expect(Math.round(minutes)).toBe(LOGIN_TOKEN_TTL_MINUTES);
  });

  it("reject a token that was never issued", async () => {
    const db = testDb();
    expect(await redeemLoginToken(db, newToken())).toBeNull();
    expect(await redeemLoginToken(db, "")).toBeNull();
    expect(await redeemLoginToken(db, "' OR 1=1 --")).toBeNull();
  });

  it("do not let one address redeem another's token", async () => {
    const db = testDb();
    const mine = await issueLoginToken(db, "ada@example.org", "Ada");
    await issueLoginToken(db, "eve@example.org", "Eve");
    const result = await redeemLoginToken(db, mine);
    expect(result?.account.email).toBe("ada@example.org");
  });
});

describe("sessions", () => {
  it("resolve to the right account", async () => {
    const db = testDb();
    const { sessionToken, account } = await signedIn(db, "ada@example.org", "Ada");
    const resolved = await accountForSession(db, sessionToken);
    expect(resolved?.id).toBe(account.id);
    expect(resolved?.email).toBe("ada@example.org");
  });

  it("resolve to null when absent, empty, or forged", async () => {
    const db = testDb();
    await signedIn(db);
    expect(await accountForSession(db, undefined)).toBeNull();
    expect(await accountForSession(db, "")).toBeNull();
    expect(await accountForSession(db, newToken())).toBeNull();
  });

  it("resolve to null once expired", async () => {
    const db = testDb();
    const { sessionToken } = await signedIn(db);
    const past = new Date(Date.now() - 1000).toISOString();
    db.exec(`UPDATE session SET expires_at = '${past}'`);
    expect(await accountForSession(db, sessionToken)).toBeNull();
  });

  it("end on sign out", async () => {
    const db = testDb();
    const { sessionToken } = await signedIn(db);
    await endSession(db, sessionToken);
    expect(await accountForSession(db, sessionToken)).toBeNull();
    expect(db.raw("SELECT * FROM session")).toHaveLength(0);
  });

  it("signing out ends only that session, not every device", async () => {
    const db = testDb();
    const laptop = await signedIn(db, "ada@example.org", "Ada");
    const phone = await signedIn(db, "ada@example.org", "Ada");
    await endSession(db, laptop.sessionToken);
    expect(await accountForSession(db, laptop.sessionToken)).toBeNull();
    expect(await accountForSession(db, phone.sessionToken)).not.toBeNull();
  });
});

describe("the session cookie", () => {
  it("carries the flags that keep it out of reach of script and cross-site posts", () => {
    const cookie = sessionCookie("abc", true);
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=Lax");
    expect(cookie).toContain("Secure");
    expect(cookie).toContain("Path=/");
  });

  it("drops Secure only for local http development", () => {
    expect(sessionCookie("abc", false)).not.toContain("Secure");
    // Still HttpOnly locally: the flag that matters against script is not a deploy detail.
    expect(sessionCookie("abc", false)).toContain("HttpOnly");
  });

  it("clears with an immediate expiry", () => {
    expect(clearedCookie(true)).toContain("Max-Age=0");
  });
});

describe("deleting an account", () => {
  it("removes the account, its roster, its sessions and its pending links", async () => {
    const db = testDb();
    const { account, sessionToken } = await signedIn(db, "ada@example.org", "Ada");
    await db
      .prepare("INSERT INTO roster_entry (account_id, ein, label, added_at) VALUES (?, ?, ?, ?)")
      .bind(account.id, "271067272", null, new Date().toISOString())
      .run();
    // A link requested but never used must go too, or it would still create an account.
    await issueLoginToken(db, "ada@example.org", "Ada");

    await deleteAccount(db, account.id);

    expect(db.raw("SELECT * FROM account")).toHaveLength(0);
    expect(db.raw("SELECT * FROM roster_entry")).toHaveLength(0);
    expect(db.raw("SELECT * FROM session")).toHaveLength(0);
    expect(db.raw("SELECT * FROM login_token")).toHaveLength(0);
    expect(await accountForSession(db, sessionToken)).toBeNull();
  });

  it("leaves other accounts untouched", async () => {
    const db = testDb();
    const ada = await signedIn(db, "ada@example.org", "Ada");
    const eve = await signedIn(db, "eve@example.org", "Eve");
    await db
      .prepare("INSERT INTO roster_entry (account_id, ein, label, added_at) VALUES (?, ?, ?, ?)")
      .bind(eve.account.id, "271067272", null, new Date().toISOString())
      .run();

    await deleteAccount(db, ada.account.id);

    expect(db.raw("SELECT * FROM account")).toHaveLength(1);
    expect(db.raw("SELECT * FROM roster_entry")).toHaveLength(1);
    expect(await accountForSession(db, eve.sessionToken)).not.toBeNull();
  });
});

describe("email handling", () => {
  it("normalizes case and surrounding space", () => {
    expect(normalizeEmail("  Ada@Example.ORG ")).toBe("ada@example.org");
  });

  it("keeps dots and plus tags distinct", () => {
    // Gmail conventions are not standards. Collapsing them merges two real, different
    // addresses into one account, silently, with no way for the user to undo it.
    expect(normalizeEmail("a.b+grants@example.org")).toBe("a.b+grants@example.org");
  });

  it("accepts unusual but valid addresses", () => {
    for (const value of [
      "a@b.co",
      "first.last+tag@sub.domain.example.org",
      "user_name@example-host.com",
      "271067272@nonprofit.org",
    ]) {
      expect(looksLikeEmail(value), value).toBe(true);
    }
  });

  it("rejects what cannot receive mail", () => {
    for (const value of ["", "a", "no-at-sign.org", "two@@example.org", "a@b", "a b@example.org"]) {
      expect(looksLikeEmail(value), value).toBe(false);
    }
  });
});
