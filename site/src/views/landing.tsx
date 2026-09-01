/**
 * The landing page.
 *
 * It has one job: get somebody from "I have an EIN" to a real answer. The form is the first
 * thing below the headline, and everything after it is there to establish that the numbers
 * can be trusted — where they come from, when they were published, and what the tool
 * deliberately refuses to say.
 *
 * No marketing claims about other products, per the program conventions. The argument is
 * made by showing the output.
 */

import type { FC } from "hono/jsx";
import { DISCLOSURE, Page, REPO } from "./layout";

const TITLE = "grantcheck — federal grant readiness check by EIN";
const DESCRIPTION =
  "Free, open check of whether a US nonprofit is mechanically ready to apply for federal " +
  "grants: 501(c)(3) status, Publication 78, automatic revocation, filing recency, SAM.gov " +
  "registration, and the single audit threshold. Every fact carries its source and date.";

export const Landing: FC<{ canonical: string; vintage?: string; signedIn?: boolean }> = ({
  canonical,
  vintage,
  signedIn,
}) => (
  <Page
    title={TITLE}
    description={DESCRIPTION}
    canonical={canonical}
    jsonLd={{
      "@context": "https://schema.org",
      "@type": "WebApplication",
      name: "grantcheck",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Any",
      description: DESCRIPTION,
      url: canonical,
      isAccessibleForFree: true,
      license: "https://www.apache.org/licenses/LICENSE-2.0",
      codeRepository: REPO,
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    }}
  >
    <section class="hero">
      <h1>Find out before you spend forty hours on the application.</h1>
      <p class="lede prose">
        Organizations write federal grant applications they were never able to submit. The exemption
        was automatically revoked. The SAM.gov registration expired. The Unique Entity ID was never
        issued. Every one of those is a hard stop, every one is public, and no free tool checks them
        together.
      </p>

      <form class="check" action="/check" method="get">
        <label class="sr-only" for="ein" style="position:absolute;left:-9999px">
          Employer Identification Number
        </label>
        <input
          id="ein"
          name="ein"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          placeholder="27-1067272"
          aria-describedby="ein-hint"
        />
        <button type="submit">Check readiness</button>
      </form>
      <p class="hint" id="ein-hint">
        Enter an Employer Identification Number, with or without the hyphen. No account, no email,
        nothing stored.
      </p>
    </section>

    <h2>What a report looks like</h2>
    <div class="terminal" aria-label="Example terminal output">
      <span class="d">$</span> uvx grantcheck --ein 27-1067272{"\n"}
      {"\n"}
      {"  "}CODE FOR AMERICA LABS{"                        "}EIN 27-1067272{"\n"}
      {"  "}
      <span class="d">SAN FRANCISCO, CA · NTEE W20 · 501(c)(3)</span>
      {"\n\n"}
      {"  "}
      <span class="p">READY TO APPLY</span>
      {"\n\n"}
      {"  "}
      <span class="c">TAX EXEMPTION</span>
      {"\n"}
      {"  "}
      <span class="p">✔</span> Exempt status{"          "}501(c)(3), unconditional exemption{"\n"}
      {"  "}
      <span class="p">✔</span> Pub 78 deductibility{"   "}Listed — PC (public charity){"\n"}
      {"  "}
      <span class="p">✔</span> Auto-revocation{"        "}No revocation on record{"\n"}
      {"  "}
      <span class="p">✔</span> Organization type{"      "}Public charity{"\n\n"}
      {"  "}
      <span class="c">FILING HEALTH</span>
      {"\n"}
      {"  "}
      <span class="p">✔</span> Most recent Form 990{"   "}Tax period ending 2024-12{"\n"}
      {"  "}
      <span class="p">✔</span> Years since filing{"     "}1{"\n\n"}
      {"  "}
      <span class="d">
        Sources: IRS EO Business Master File (2026-08-10); IRS Publication 78 (2026-08-11).
      </span>
    </div>
    <p class="prose">
      The same report is available here as a page you can link to, as{" "}
      <a href="/api/check/27-1067272">JSON</a>, and from the command line. All three come from the
      same code and the same data, so they cannot disagree.
    </p>

    <h2>What it checks</h2>
    <div class="grid">
      <div class="card">
        <h3>
          <a href="/checks/exempt_status">Exempt status</a>
        </h3>
        <p>
          Whether the IRS records an unconditional 501(c)(3) exemption. Most federal programs
          require it.
        </p>
      </div>
      <div class="card">
        <h3>
          <a href="/checks/auto_revocation">Automatic revocation</a>
        </h3>
        <p>
          Three missed years revokes the exemption by operation of law. Being on the list is not the
          same as being revoked today.
        </p>
      </div>
      <div class="card">
        <h3>
          <a href="/checks/filing_recency">Distance to revocation</a>
        </h3>
        <p>
          How many years since the last filing. Nobody publishes this number, and it is the leading
          indicator.
        </p>
      </div>
      <div class="card">
        <h3>
          <a href="/checks/sam_registration">SAM.gov registration</a>
        </h3>
        <p>
          The single most common avoidable disqualification. Registrations lapse annually and
          renewal is not automatic.
        </p>
      </div>
      <div class="card">
        <h3>
          <a href="/checks/pub78_deductibility">Publication 78</a>
        </h3>
        <p>
          Eligibility to receive tax-deductible contributions — and why a group subordinate is
          absent from it on purpose.
        </p>
      </div>
      <div class="card">
        <h3>
          <a href="/checks/single_audit">Single audit threshold</a>
        </h3>
        <p>
          $750,000 or $1,000,000 depending on when your fiscal year began. Most organizations do not
          know which applies.
        </p>
      </div>
    </div>

    <h2>More than one at a time</h2>
    <p class="prose">
      Everything above is free and needs no account, and that will not change — a report is a public
      fact about a public record. What an email address unlocks is the part that has to remember
      something:
    </p>
    <div class="grid">
      <div class="card">
        <h3>Check a whole list</h3>
        <p>
          Paste up to 200 EINs and get one table. A funder screening applicants, a fiscal sponsor
          reviewing projects, a consultant with a client list.
        </p>
      </div>
      <div class="card">
        <h3>Get told when it changes</h3>
        <p>
          Save a roster and we re-check it against every monthly IRS release. You get an email only
          when a verdict actually moves — not a digest, not a newsletter.
        </p>
      </div>
      <div class="card">
        <h3>Export it</h3>
        <p>CSV of the whole roster with findings and dates, for a spreadsheet or a board packet.</p>
      </div>
    </div>
    <p class="prose">
      {signedIn ? (
        <>
          <a href="/roster">Open your roster</a>.
        </>
      ) : (
        <>
          <a href="/join">Sign in with an email address</a> — no password, and the link is the whole
          of it. We send your sign-in link and the alerts you asked for, nothing else, and deleting
          your account takes one button and happens immediately. Or skip us entirely: the{" "}
          <a href={REPO}>command-line tool</a> does all of it on your own machine.
        </>
      )}
    </p>

    <h2>Why you can check our work</h2>
    <p class="prose">
      Every line of every report names the dataset it came from and the date that dataset was
      published. Nothing is inferred silently: where the tool has to guess — matching an
      organization to its SAM.gov registration, which cannot be looked up by EIN — it prints the
      confidence and tells you how to correct it.
    </p>
    <p class="prose">
      It is Apache 2.0 and the whole thing is on <a href={REPO}>GitHub</a>. The command-line tool
      runs with no account, no API key, and no connection to us. You do not have to trust this site;
      you can run it yourself.
    </p>

    <h2>Run it locally</h2>
    <div class="terminal">
      <span class="d"># one command, nothing to install first</span>
      {"\n"}uvx grantcheck --ein 27-1067272{"\n\n"}
      <span class="d"># or as a Model Context Protocol server, for an agent</span>
      {"\n"}uvx grantcheck mcp
    </div>

    <p class="note prose">
      <strong>What this is not.</strong> It is not an eligibility determination. It reports
      observable facts and what they usually mean. There is no score, no grade, and no probability,
      because the honest answer to "will we win this" is not in any of these datasets.
    </p>

    {vintage ? (
      <p class="sources">
        Index vintage <span class="mono">{vintage}</span>. Rebuilt monthly from the IRS bulk
        datasets. <a href="/data">What is in it</a>.
      </p>
    ) : null}

    <p class="disclosure">{DISCLOSURE}</p>
  </Page>
);
