/**
 * Magic-link authentication. No passwords, anywhere.
 *
 * There is no password to store, hash, rotate, reset, or leak, and no password-reset flow
 * to get wrong — which is the flow that most often is. What the database holds is a
 * **hash** of each token, never the token itself, so reading the database does not hand
 * anyone a live session.
 *
 * What an account is for, and what it is not for: reports, explainers and the JSON API are
 * open and uncredentialed, because that is what makes them worth indexing and citing. An
 * account unlocks the workflow — checking a roster in one pass, being told when something
 * changes, exporting. Signing in must never be the price of an answer.
 */

const TOKEN_BYTES = 32;

/** Magic links are short-lived. Long enough to walk to your inbox, not long enough to sit. */
export const LOGIN_TOKEN_TTL_MINUTES = 15;

/** Sessions last a month; a consultant should not be signing in every visit. */
export const SESSION_TTL_DAYS = 30;

export const SESSION_COOKIE = "gc_session";

/**
 * A URL-safe random token. `crypto.getRandomValues` is a CSPRNG; `Math.random` is not, and
 * a guessable login token is a full account takeover.
 */
export function newToken(): string {
  const bytes = new Uint8Array(TOKEN_BYTES);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** SHA-256 of a token. Only ever the hash is written to the database. */
export async function hashToken(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function newId(): string {
  return crypto.randomUUID();
}

/**
 * Normalize an email for storage and comparison.
 *
 * Lowercased and trimmed, and nothing more. Deliberately NOT stripping dots or `+tags`:
 * those are Gmail conventions, not standards, and applying them to every provider merges
 * two genuinely different addresses into one account. The failure is silent and the user
 * cannot fix it.
 */
export function normalizeEmail(raw: string): string {
  return raw.trim().toLowerCase();
}

/**
 * A deliberately permissive check. The address either receives the link or it does not,
 * and that is the real validation — a regex that rejects valid but unusual addresses is a
 * support ticket, not a security control.
 */
export function looksLikeEmail(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length < 3 || trimmed.length > 254) return false;
  if (/\s/.test(trimmed)) return false;
  const at = trimmed.indexOf("@");
  if (at < 1 || at !== trimmed.lastIndexOf("@")) return false;
  const domain = trimmed.slice(at + 1);
  return domain.includes(".") && !domain.startsWith(".") && !domain.endsWith(".");
}

export type Account = {
  id: string;
  email: string;
  name: string;
  created_at: string;
  verified_at: string | null;
};

function iso(offsetMs = 0): string {
  return new Date(Date.now() + offsetMs).toISOString();
}

/**
 * Issue a login token for an email address.
 *
 * **Creates no account.** The pending email and name are held on the token row, and the
 * account is created only when somebody proves they can read that inbox. Otherwise anybody
 * could manufacture account rows for arbitrary addresses, and the sign-in email could not
 * honestly tell an unintended recipient that nothing was created for them.
 *
 * Returns the raw token for the email body. The caller must not persist or log it: the
 * database holds only its hash, and this string is the only thing that grants access.
 */
export async function issueLoginToken(
  db: D1Database,
  email: string,
  name: string,
): Promise<string> {
  const normalized = normalizeEmail(email);
  const token = newToken();
  await db
    .prepare(
      "INSERT INTO login_token (token_hash, email, name, created_at, expires_at) " +
        "VALUES (?, ?, ?, ?, ?)",
    )
    .bind(
      await hashToken(token),
      normalized,
      name.trim().slice(0, 120),
      iso(),
      iso(LOGIN_TOKEN_TTL_MINUTES * 60_000),
    )
    .run();
  return token;
}

/**
 * Exchange a login token for a session. Returns the session token, or null.
 *
 * The token is single-use: it is marked used in the same step that reads it, so a link
 * forwarded, logged by a mail scanner, or sitting in browser history cannot be replayed.
 */
export async function redeemLoginToken(
  db: D1Database,
  token: string,
): Promise<{ sessionToken: string; account: Account } | null> {
  const hash = await hashToken(token);
  const row = await db
    .prepare("SELECT * FROM login_token WHERE token_hash = ?")
    .bind(hash)
    .first<{ email: string; name: string; expires_at: string; used_at: string | null }>();

  if (!row || row.used_at || row.expires_at < iso()) return null;

  // Create the account now, on proof of inbox control, rather than when the link was asked
  // for. An existing account keeps its original name.
  let account = await db
    .prepare("SELECT * FROM account WHERE email = ?")
    .bind(row.email)
    .first<Account>();

  if (!account) {
    const id = newId();
    await db
      .prepare(
        "INSERT INTO account (id, email, name, created_at, verified_at) VALUES (?, ?, ?, ?, ?)",
      )
      .bind(id, row.email, row.name || row.email, iso(), iso())
      .run();
    account = {
      id,
      email: row.email,
      name: row.name || row.email,
      created_at: iso(),
      verified_at: iso(),
    };
  }

  const sessionToken = newToken();
  await db.batch([
    db.prepare("UPDATE login_token SET used_at = ? WHERE token_hash = ?").bind(iso(), hash),
    db
      .prepare("UPDATE account SET verified_at = COALESCE(verified_at, ?) WHERE id = ?")
      .bind(iso(), account.id),
    db
      .prepare(
        "INSERT INTO session (token_hash, account_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
      )
      .bind(
        await hashToken(sessionToken),
        account.id,
        iso(),
        iso(SESSION_TTL_DAYS * 24 * 3600_000),
      ),
  ]);

  return { sessionToken, account };
}

/** Resolve a session cookie to an account, or null. Expired sessions resolve to null. */
export async function accountForSession(
  db: D1Database,
  token: string | undefined,
): Promise<Account | null> {
  if (!token) return null;
  const row = await db
    .prepare(
      "SELECT a.* FROM session s JOIN account a ON a.id = s.account_id " +
        "WHERE s.token_hash = ? AND s.expires_at > ?",
    )
    .bind(await hashToken(token), iso())
    .first<Account>();
  return row ?? null;
}

export async function endSession(db: D1Database, token: string | undefined): Promise<void> {
  if (!token) return;
  await db
    .prepare("DELETE FROM session WHERE token_hash = ?")
    .bind(await hashToken(token))
    .run();
}

/**
 * Delete an account and everything attached to it, for real.
 *
 * The roster is the one place this site joins a person to a set of EINs, which the privacy
 * policy otherwise rules out. Somebody who asks to be forgotten has to actually be, without
 * writing to us and waiting.
 */
export async function deleteAccount(db: D1Database, accountId: string): Promise<void> {
  await db.batch([
    db.prepare("DELETE FROM roster_entry WHERE account_id = ?").bind(accountId),
    db.prepare("DELETE FROM session WHERE account_id = ?").bind(accountId),
    db
      .prepare("DELETE FROM login_token WHERE email = (SELECT email FROM account WHERE id = ?)")
      .bind(accountId),
    db.prepare("DELETE FROM account WHERE id = ?").bind(accountId),
  ]);
}

export function sessionCookie(token: string, secure: boolean): string {
  const parts = [
    `${SESSION_COOKIE}=${token}`,
    "Path=/",
    "HttpOnly", // script cannot read it, so an XSS bug is not instantly an account takeover
    "SameSite=Lax", // survives following a link from the email, blocks cross-site POSTs
    `Max-Age=${SESSION_TTL_DAYS * 24 * 3600}`,
  ];
  if (secure) parts.push("Secure");
  return parts.join("; ");
}

export function clearedCookie(secure: boolean): string {
  const parts = [`${SESSION_COOKIE}=`, "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=0"];
  if (secure) parts.push("Secure");
  return parts.join("; ");
}
