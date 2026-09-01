/**
 * The entity page. One permanent, citable URL per organization.
 *
 * Three constraints shape it, all from the hosted build prompt:
 *
 * 1. **Every fact is in the initial HTML.** No client-side fetching for anything primary.
 *    `curl` the page with JavaScript never executed and the complete answer must be there.
 *    That is the whole reason this site is edge-SSR rather than a static shell.
 * 2. **It opens with one self-contained paragraph** stating the conclusion, the reason, and
 *    the vintage — written so a language model can lift it whole and still be correct and
 *    attributable.
 * 3. **`schema.org` NGO with `taxID`.** That property is what makes the page
 *    machine-joinable, and it is the single most valuable line of markup here.
 */

import type { FC } from "hono/jsx";
import type { Check, Report } from "../report";
import { DATASET_NAMES, VERDICT_LABEL } from "../report";
import { Disclosure, Page } from "./layout";

const GROUPS: Array<[string, string]> = [
  ["tax_exemption", "Tax exemption"],
  ["filing_health", "Filing health"],
  ["federal_registration", "Federal registration"],
  ["audit_posture", "Audit posture"],
];

const STATUS_WORD: Record<string, string> = {
  pass: "OK",
  warn: "Attention",
  fail: "Problem",
  unknown: "Not checked",
  not_applicable: "Not applicable",
};

/**
 * The quotable paragraph. A model that lifts this sentence has the organization, the
 * conclusion, the reason, and the date — everything needed to cite it correctly.
 */
function summary(report: Report): string {
  const org = report.organization;
  const name = org?.name ?? `EIN ${report.ein}`;
  const asOf = report.vintages[0]?.published ?? "the dates shown";

  if (report.readiness === "blocked") {
    const blocking = report.checks
      .filter((c) => report.blocking_check_ids.includes(c.id))
      .map((c) => c.label.toLowerCase());
    return `As of ${asOf}, ${name} (EIN ${report.ein}) has ${blocking.length} issue${
      blocking.length === 1 ? "" : "s"
    } that mechanically prevent a federal grant application from being submitted: ${blocking.join(
      ", ",
    )}. This is derived from public IRS data and is not an eligibility determination.`;
  }

  const attention = report.checks.filter(
    (c) => c.status === "warn" || (c.status === "fail" && !c.blocking),
  );
  if (attention.length > 0) {
    return `As of ${asOf}, ${name} (EIN ${report.ein}) shows nothing that mechanically blocks a federal grant application, but ${attention.length} item${
      attention.length === 1 ? " needs" : "s need"
    } attention: ${attention.map((c) => c.label.toLowerCase()).join(", ")}. This is derived from public IRS data and is not an eligibility determination.`;
  }

  return `As of ${asOf}, ${name} (EIN ${report.ein}) shows no mechanical barrier to submitting a federal grant application: it is recognized under section 501(c)(3), has no automatic revocation on record, and is current on its annual filings. This is derived from public IRS data and is not an eligibility determination.`;
}

function jsonLd(report: Report, canonical: string) {
  const org = report.organization;
  if (!org) return undefined;
  const sameAs = [
    `https://apps.irs.gov/app/eos/detailsPage?ein=${report.ein.replace("-", "")}`,
    `https://projects.propublica.org/nonprofits/organizations/${report.ein.replace("-", "")}`,
  ];
  return {
    "@context": "https://schema.org",
    "@type": "NGO",
    name: org.name,
    ...(org.sort_name ? { alternateName: org.sort_name } : {}),
    // The property that makes this page machine-joinable to every other dataset keyed on
    // EIN. The most valuable line of markup on the site.
    taxID: report.ein,
    ...(org.uei ? { identifier: org.uei } : {}),
    ...(org.subsection === "03" ? { nonprofitStatus: "NonprofitType501c3" } : {}),
    address: {
      "@type": "PostalAddress",
      // Labelled as the IRS mailing address in the visible text too. It is a mailing
      // address, not a location — an organization operating in Ohio can carry a Delaware
      // registered-agent address here.
      ...(org.city ? { addressLocality: org.city } : {}),
      ...(org.state ? { addressRegion: org.state } : {}),
      addressCountry: "US",
    },
    url: canonical,
    sameAs,
  };
}

const StatusCell: FC<{ check: Check }> = ({ check }) => (
  <td class="status">
    <span class={`dot ${check.status}`} aria-hidden="true" />
    <span class="tag">{STATUS_WORD[check.status] ?? check.status}</span>
  </td>
);

export const Entity: FC<{ report: Report; canonical: string }> = ({ report, canonical }) => {
  const org = report.organization;
  const name = org?.name ?? `EIN ${report.ein}`;
  const where = [org?.city, org?.state].filter(Boolean).join(", ");
  const lede = summary(report);

  return (
    <Page
      title={`${name} — federal grant readiness, EIN ${report.ein}`}
      description={lede.slice(0, 300)}
      canonical={canonical}
      jsonLd={jsonLd(report, canonical)}
    >
      <h1 style="margin-top:40px">{name}</h1>
      <p class="identity">
        <span class="ein">EIN {report.ein}</span>
        {where ? ` · ${where}` : ""}
        {org?.ntee_code ? ` · NTEE ${org.ntee_code}` : ""}
        {org?.subsection === "03" ? " · 501(c)(3)" : ""}
      </p>

      <div class="verdict">
        <span class={`badge ${report.readiness}`}>{VERDICT_LABEL[report.readiness]}</span>
      </div>

      {/* The self-contained, quotable paragraph. */}
      <p class="lede prose">{lede}</p>

      {GROUPS.map(([group, title]) => {
        const members = report.checks.filter((c) => c.group === group);
        if (members.length === 0) return null;
        return (
          <>
            <h2>{title}</h2>
            <table class="checks">
              <thead>
                <tr>
                  {/* The cell text already says OK / Attention / Problem, so a visible
                      header here only collides with the next column. */}
                  <th class="status">
                    <span class="sr">Status</span>
                  </th>
                  <th>Check</th>
                  <th>Finding</th>
                  <th>As of</th>
                </tr>
              </thead>
              <tbody>
                {members.map((check) => (
                  <tr>
                    <StatusCell check={check} />
                    <td class="label">
                      <a href={`/checks/${check.id}`}>{check.label}</a>
                    </td>
                    <td>
                      {check.value ?? ""}
                      {check.status === "warn" || check.status === "fail" ? (
                        <p class="detail">{check.detail}</p>
                      ) : null}
                    </td>
                    <td class="asof">
                      {check.vintage ? (
                        <time datetime={check.vintage.published}>{check.vintage.published}</time>
                      ) : (
                        ""
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        );
      })}

      {report.notes.length > 0 ? (
        <div class="note">
          {report.notes.map((n) => (
            <p style="margin:0">{n}</p>
          ))}
        </div>
      ) : null}

      <p class="sources">
        {org?.city ? (
          <>
            Address shown is the IRS mailing address on file, which is not necessarily where the
            organization operates.{" "}
          </>
        ) : null}
        Derived from{" "}
        {report.vintages.map((v, i) => (
          <>
            {i > 0 ? "; " : ""}
            {v.source_url ? (
              <a href={v.source_url}>{DATASET_NAMES[v.dataset] ?? v.dataset}</a>
            ) : (
              (DATASET_NAMES[v.dataset] ?? v.dataset)
            )}{" "}
            published <time datetime={v.published}>{v.published}</time>
          </>
        ))}
        . <a href={`/api/check/${report.ein}`}>This report as JSON</a>.
      </p>

      <Disclosure />
    </Page>
  );
};

export const NotFound: FC<{ ein: string; canonical: string }> = ({ ein, canonical }) => (
  <Page
    title={`EIN ${ein} is not in the index — grantcheck`}
    description={`No organization with EIN ${ein} appears in the published IRS datasets.`}
    canonical={canonical}
    // noindex, so a well-formed but absent EIN does not create a billion crawlable
    // not-found URLs.
    noindex
  >
    <h1 style="margin-top:40px">Not in the index</h1>
    <p class="identity">
      <span class="ein">EIN {ein}</span>
    </p>
    <p class="lede prose">
      That is a well-formed EIN, and no organization with it appears in the IRS datasets this site
      publishes. That is a real answer rather than an error.
    </p>
    <h2>Why an organization can be legitimately absent</h2>
    <ul class="plain prose">
      <li>
        <strong>Churches and their integrated auxiliaries</strong> are exempt without applying and
        are largely absent from the Business Master File.
      </li>
      <li>
        <strong>Government instrumentalities</strong> — school districts, tribal governments, public
        hospitals — are exempt under different provisions.
      </li>
      <li>
        <strong>Recently recognized organizations</strong> take a monthly cycle or two to appear.
      </li>
      <li>
        <strong>Some EIN prefixes were never issued.</strong> Ten of the hundred possible two-digit
        prefixes have no organizations at all.
      </li>
    </ul>
    <p class="prose">
      Check the <a href="https://apps.irs.gov/app/eos/">IRS Tax Exempt Organization Search</a>{" "}
      directly before concluding anything, and <a href="/">try another EIN</a>.
    </p>
    <Disclosure />
  </Page>
);
