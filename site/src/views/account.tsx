/**
 * Sign-in, roster and bulk-check views.
 *
 * These are the only pages on the site behind a session, and they are all `noindex`: a
 * signed-in workspace has no search value, and the roster is private by construction. The
 * pages worth indexing — one per organization — stay open to everyone.
 */

import type { FC, PropsWithChildren } from "hono/jsx";
import type { Check, Report } from "../report";
import { formatEin, verdictLabel } from "../report";
import { Disclosure, Page, REPO } from "./layout";

export type RosterRow = {
  ein: string;
  label: string | null;
  added_at: string;
  name: string | null;
  city: string | null;
  state: string | null;
  readiness: string;
  headline: string;
};

const Shell: FC<PropsWithChildren<{ title: string; description: string }>> = ({
  title,
  description,
  children,
}) => (
  <Page title={title} description={description} noindex>
    {children}
  </Page>
);

/** The sign-in page. One form, two fields, no password anywhere. */
export const Join: FC<{ next?: string; error?: string; email?: string }> = ({
  next,
  error,
  email,
}) => (
  <Shell
    title="Sign in — grantcheck"
    description="Sign in with an email address to check a whole roster at once and get told when something changes."
  >
    <h1 style="margin-top:44px">Check a whole roster</h1>
    <p class="lede prose">
      Single-organization reports are free and need no account. An address unlocks the parts that
      need to remember something: checking a list in one pass, monthly monitoring, and export.
    </p>

    {error ? <p class="formerror">{error}</p> : null}

    <form class="stack" method="post" action="/join">
      {next ? <input type="hidden" name="next" value={next} /> : null}
      <label>
        <span>Your name</span>
        <input name="name" autocomplete="name" required maxlength={120} />
      </label>
      <label>
        <span>Email address</span>
        <input
          name="email"
          type="email"
          autocomplete="email"
          required
          maxlength={254}
          value={email ?? ""}
          placeholder="you@organization.org"
        />
      </label>
      <button type="submit">Email me a sign-in link</button>
    </form>

    <p class="hint prose" style="margin-top:18px">
      No password. We send a link that works once and expires in fifteen minutes.
    </p>

    <h2>What the address is for, and what it is not</h2>
    <ul class="plain prose">
      <li>
        <strong>It is for monitoring.</strong> To tell you that an organization on your list was
        added to the automatic revocation file, we have to know where to write.
      </li>
      <li>
        <strong>There is no tracking.</strong> No analytics, no pixels, no third-party scripts — on
        this page or any other.
      </li>
      <li>
        <strong>We never sell or share it.</strong> The only mail we send is your sign-in link and
        the monitoring alerts you asked for.
      </li>
      <li>
        <strong>Deleting is instant and complete.</strong> One button on your account page removes
        the account, the roster and every session. No email, no waiting.
      </li>
      <li>
        <strong>You can skip all of it.</strong> <a href={REPO}>Install the CLI</a> and every
        feature here runs on your own machine, against the same published index, with nothing sent
        anywhere.
      </li>
    </ul>
    <p class="prose">
      All of that is stated in full, in the terms the law uses, in our{" "}
      <a href="/privacy">privacy policy</a>.
    </p>
    <Disclosure />
  </Shell>
);

/**
 * Shown after a link is requested — for a valid address and an unregistered one alike.
 *
 * Identical either way on purpose. A page that says "we do not have that address" turns the
 * form into an oracle for testing whether a given person has an account here.
 */
export const LinkSent: FC<{ email: string }> = ({ email }) => (
  <Shell title="Check your email — grantcheck" description="A sign-in link is on its way.">
    <h1 style="margin-top:44px">Check your email</h1>
    <p class="lede prose">
      If <strong>{email}</strong> can receive mail, a sign-in link is on its way. It works once and
      expires in fifteen minutes.
    </p>
    <p class="prose">
      Nothing arrived? Check spam, then <a href="/join">try again</a> — a new link invalidates
      nothing, and old links simply expire.
    </p>
    <Disclosure />
  </Shell>
);

export const LinkExpired: FC = () => (
  <Shell title="That link has expired — grantcheck" description="Request a new sign-in link.">
    <h1 style="margin-top:44px">That link no longer works</h1>
    <p class="lede prose">
      Sign-in links work once and expire after fifteen minutes. That is deliberate: it means a link
      sitting in an old email, a forwarded thread, or a mail scanner log cannot be used to get into
      your account.
    </p>
    <p class="prose">
      <a href="/join">Request a new one</a>.
    </p>
    <Disclosure />
  </Shell>
);

const VerdictPill: FC<{ readiness: string }> = ({ readiness }) => (
  <span class={`badge ${readiness}`}>{verdictLabel(readiness)}</span>
);

/** The roster. The reason an account exists at all. */
export const Roster: FC<{
  name: string;
  rows: RosterRow[];
  added?: string;
  notice?: string;
}> = ({ name, rows, added, notice }) => {
  const blocked = rows.filter((r) => r.readiness === "blocked").length;
  const attention = rows.filter((r) => r.readiness === "attention").length;

  return (
    <Shell title="Your roster — grantcheck" description="Organizations you are monitoring.">
      <div class="pagehead">
        <h1>Your roster</h1>
        <nav class="subnav">
          <a href="/bulk">Bulk check</a>
          <a href="/account">Account</a>
        </nav>
      </div>

      <p class="lede prose">
        Signed in as {name}. {rows.length === 0 ? "Nothing saved yet." : null}
        {rows.length > 0 ? (
          <>
            {rows.length} organization{rows.length === 1 ? "" : "s"}
            {blocked > 0 ? `, ${blocked} blocked` : ""}
            {attention > 0 ? `, ${attention} needing attention` : ""}. Re-checked against every
            monthly ingest; you get an email only when a verdict actually changes.
          </>
        ) : null}
      </p>

      {notice ? <p class="formerror">{notice}</p> : null}
      {added ? <p class="formok">Added {added} to your roster.</p> : null}

      <form class="row" method="post" action="/roster/add">
        <input name="ein" placeholder="EIN, e.g. 27-1067272" required maxlength={20} />
        <input name="label" placeholder="Label (optional)" maxlength={80} />
        <button type="submit">Add</button>
      </form>

      {rows.length > 0 ? (
        <>
          <table class="checks">
            <thead>
              <tr>
                <th class="status">
                  <span class="sr">Status</span>
                </th>
                <th>Organization</th>
                <th>Finding</th>
                <th>
                  <span class="sr">Remove</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr>
                  <td class="status">
                    <VerdictPill readiness={r.readiness} />
                  </td>
                  <td class="label">
                    <a href={`/ein/${formatEin(r.ein)}`}>{r.name ?? `EIN ${formatEin(r.ein)}`}</a>
                    <p class="detail">
                      <span class="mono">{formatEin(r.ein)}</span>
                      {r.city ? ` · ${r.city}, ${r.state}` : ""}
                      {r.label ? ` · ${r.label}` : ""}
                    </p>
                  </td>
                  <td>
                    <p class="detail" style="margin:0">
                      {r.headline}
                    </p>
                  </td>
                  <td class="asof">
                    <form method="post" action="/roster/remove" class="inline">
                      <input type="hidden" name="ein" value={r.ein} />
                      <button type="submit" class="link">
                        Remove
                      </button>
                    </form>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p class="sources">
            <a href="/roster/export.csv">Download as CSV</a> · every column, one row per
            organization, for a spreadsheet or a board packet.
          </p>
        </>
      ) : (
        <p class="prose" style="margin-top:28px">
          Add an EIN above, or paste a whole list into the <a href="/bulk">bulk check</a>.
        </p>
      )}

      <Disclosure />
    </Shell>
  );
};

/**
 * One line per organization, for a table cell.
 *
 * Label *and* value, because the label alone is the name of a question, not an answer:
 * "Organization type" tells a reader nothing, where "Organization type: private
 * foundation" tells them the thing they came for. The point of a roster view is to be
 * readable without opening thirty tabs.
 */
export function headline(report: Report): string {
  if (!report.organization) return "Not in the published IRS index.";
  const say = (c: Check) => (c.value ? `${c.label}: ${c.value}` : c.label);

  const blocking = report.checks.filter((c) => report.blocking_check_ids.includes(c.id));
  if (blocking.length > 0) return blocking.map(say).join("; ");

  const attention = report.checks.filter(
    (c) => c.status === "warn" || (c.status === "fail" && !c.blocking),
  );
  if (attention.length > 0) return attention.map(say).join("; ");

  return "No mechanical barrier found.";
}

/** Bulk check. Paste a list, get one table. The single most-asked-for thing. */
export const Bulk: FC<{
  reports?: Array<{ ein: string; report: Report }>;
  unparsed?: string[];
  raw?: string;
  truncated?: number;
}> = ({ reports, unparsed, raw, truncated }) => (
  <Shell title="Bulk check — grantcheck" description="Check a list of EINs in one pass.">
    <div class="pagehead">
      <h1>Bulk check</h1>
      <nav class="subnav">
        <a href="/roster">Roster</a>
        <a href="/account">Account</a>
      </nav>
    </div>

    <p class="lede prose">Paste EINs — one per line, or comma separated. Up to 200 at a time.</p>

    <form class="stack" method="post" action="/bulk">
      <label>
        <span class="sr">EINs</span>
        <textarea name="eins" rows={8} placeholder="27-1067272">
          {raw ?? ""}
        </textarea>
      </label>
      <button type="submit">Check them</button>
    </form>

    {truncated ? (
      <p class="formerror">
        Only the first 200 were checked; {truncated} more were left out. Run the rest in a second
        pass, or use <span class="mono">grantcheck</span> locally, which has no limit.
      </p>
    ) : null}

    {unparsed && unparsed.length > 0 ? (
      <p class="formerror">
        {unparsed.length === 1
          ? "Skipped 1 entry that is not a nine-digit EIN: "
          : `Skipped ${unparsed.length} entries that are not nine-digit EINs: `}
        <span class="mono">{unparsed.slice(0, 8).join(", ")}</span>
        {unparsed.length > 8 ? ` and ${unparsed.length - 8} more` : ""}.
      </p>
    ) : null}

    {reports && reports.length > 0 ? (
      <>
        <table class="checks">
          <thead>
            <tr>
              <th class="status">
                <span class="sr">Status</span>
              </th>
              <th>Organization</th>
              <th>Finding</th>
              <th>
                <span class="sr">Save</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {reports.map(({ ein, report }) => (
              <tr>
                <td class="status">
                  <VerdictPill readiness={report.readiness} />
                </td>
                <td class="label">
                  <a href={`/ein/${formatEin(ein)}`}>
                    {report.organization?.name ?? `EIN ${formatEin(ein)}`}
                  </a>
                  <p class="detail">
                    <span class="mono">{formatEin(ein)}</span>
                    {report.organization?.city
                      ? ` · ${report.organization.city}, ${report.organization.state}`
                      : ""}
                  </p>
                </td>
                <td>
                  <p class="detail" style="margin:0">
                    {headline(report)}
                  </p>
                </td>
                <td class="asof">
                  <form method="post" action="/roster/add" class="inline">
                    <input type="hidden" name="ein" value={ein} />
                    <input type="hidden" name="next" value="/bulk" />
                    <button type="submit" class="link">
                      Save
                    </button>
                  </form>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p class="sources">
          <a href="/roster/export.csv">Export your saved roster as CSV</a>. Or run the same check
          offline with no limit: <span class="mono">grantcheck --format json</span>.
        </p>
      </>
    ) : null}

    <Disclosure />
  </Shell>
);

export const AccountPage: FC<{
  name: string;
  email: string;
  created: string;
  rosterCount: number;
  error?: string;
}> = ({ name, email, created, rosterCount, error }) => (
  <Shell title="Account — grantcheck" description="Your account.">
    <div class="pagehead">
      <h1>Account</h1>
      <nav class="subnav">
        <a href="/roster">Roster</a>
        <a href="/bulk">Bulk check</a>
      </nav>
    </div>

    <table class="checks">
      <tbody>
        <tr>
          <td class="label">Name</td>
          <td>{name}</td>
        </tr>
        <tr>
          <td class="label">Email</td>
          <td class="mono">{email}</td>
        </tr>
        <tr>
          <td class="label">Joined</td>
          <td class="mono">{created.slice(0, 10)}</td>
        </tr>
        <tr>
          <td class="label">Saved organizations</td>
          <td>{rosterCount}</td>
        </tr>
      </tbody>
    </table>

    <h2>What we hold</h2>
    <p class="prose">
      Your name, your email address, and the EINs you saved. Nothing else. There is no record of
      which reports you read: report pages are served from cache, are never associated with an
      account, and per-request logging is switched off at the infrastructure level. The full account
      is in our <a href="/privacy">privacy policy</a>.
    </p>

    <h2>Leaving</h2>
    <p class="prose">
      Deleting removes the account, the roster and every active session immediately. It cannot be
      undone, and nothing is retained. Every feature you would lose is in{" "}
      <a href={REPO}>the open source CLI</a>, which runs entirely on your own machine.
    </p>
    {error ? <p class="formerror">{error}</p> : null}
    <form method="post" action="/account/delete" class="stack">
      <label>
        <span>Type DELETE to confirm</span>
        <input name="confirm" required maxlength={10} autocomplete="off" />
      </label>
      <button type="submit" class="danger">
        Delete my account
      </button>
    </form>

    <form method="post" action="/logout" style="margin-top:32px">
      <button type="submit" class="link">
        Sign out
      </button>
    </form>

    <Disclosure />
  </Shell>
);
