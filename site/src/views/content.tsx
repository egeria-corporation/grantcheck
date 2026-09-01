/**
 * Static content pages: the check explainers, methodology, and a generic wrapper.
 *
 * The explainers are the high-intent search surface. Somebody types "what does automatic
 * revocation of exemption mean" and there is currently no good free answer. Each page uses
 * the question as its H1 verbatim and answers it inside the first forty words, because that
 * is what gets quoted — by a search result and by a model.
 */

import type { FC, PropsWithChildren } from "hono/jsx";
import { Disclosure, Page } from "./layout";

export const Data: FC<
  PropsWithChildren<{ title: string; canonical: string; heading: string; noindex?: boolean }>
> = ({ title, canonical, heading, noindex, children }) => (
  <Page
    title={`${title} — grantcheck`}
    description={heading}
    canonical={canonical}
    noindex={noindex}
  >
    <h1 style="margin-top:40px">{heading}</h1>
    {children}
    <Disclosure />
  </Page>
);

type Explainer = {
  question: string;
  answer: string;
  body: Array<{ h: string; p: string[] }>;
};

/**
 * One entry per check id. The `answer` is deliberately short and self-contained: it is the
 * first thing after the H1, and it is what a generative engine will lift.
 */
const EXPLAINERS: Record<string, Explainer> = {
  auto_revocation: {
    question: "What does automatic revocation of exemption mean?",
    answer:
      "Three consecutive years without filing a Form 990, 990-EZ, or 990-N revokes a " +
      "nonprofit's tax-exempt status automatically, by operation of law. There is no hearing " +
      "and often no notice anybody reads. A revoked organization cannot receive federal " +
      "grants or tax-deductible contributions until it is reinstated.",
    body: [
      {
        h: "Being on the list is not the same as being revoked",
        p: [
          "This is the single most misread fact about the IRS Automatic Revocation of " +
            "Exemption List. Organizations that have been reinstated stay on the published " +
            "list permanently, with a reinstatement date recorded alongside the revocation.",
          "In the August 2026 file, 181,259 of 1,246,171 entries carry a reinstatement date — " +
            "roughly one in seven. Any tool that reads list membership as “revoked” " +
            "tells all of them they cannot apply for federal money. grantcheck reads the dates.",
          "An organization can also be revoked, reinstated, and revoked again. 19,136 EINs " +
            "have more than one entry, so current status comes from the most recent " +
            "revocation rather than whichever row appears first.",
        ],
      },
      {
        h: "How to get reinstated",
        p: [
          "Reinstatement is by Form 1023 or Form 1023-EZ. Retroactive reinstatement — which " +
            "restores exemption back to the revocation date, so the gap never existed for " +
            "donors — has deadlines that depend on how long ago revocation happened. IRS " +
            "Revenue Procedure 2014-11 sets out the four routes.",
          "Filing the missing returns is the immediate action either way.",
        ],
      },
    ],
  },
  filing_recency: {
    question: "How many years can a nonprofit miss filing before losing exemption?",
    answer:
      "Three. Three consecutive years without filing a Form 990, 990-EZ, or 990-N and the " +
      "exemption is revoked automatically. At one missed year there is time; at two, one more " +
      "lapse ends it; at three, the organization may already be on the next revocation posting.",
    body: [
      {
        h: "Why this number is hard to find",
        p: [
          "Nobody publishes the distance to the cliff. The IRS publishes filings, and it " +
            "publishes revocations, but not the count of years between the last filing and " +
            "today — which is the number that tells you whether to act this month.",
          "It is also easy to compute wrongly. The Business Master File carries a " +
            "“tax period” field that looks like a filing date and is not: it is the " +
            "period of the most recent return the IRS has processed, and processing lags " +
            "filing by weeks to more than a year. Counting from it can make an organization " +
            "that filed on time look two years delinquent.",
        ],
      },
      {
        h: "Who this does not apply to",
        p: [
          "433,337 organizations are not required to file at all — churches are 287,356 of " +
            "them, along with religious organizations, state instrumentalities, and " +
            "subordinates covered by a central organization's group return. They cannot be " +
            "delinquent because nothing was ever due, and grantcheck never flags them.",
        ],
      },
    ],
  },
  single_audit: {
    question: "Do I need a single audit?",
    answer:
      "If your organization expended $1,000,000 or more in federal awards during a fiscal year " +
      "beginning on or after 1 October 2024, yes. For fiscal years that began before that date " +
      "the threshold is $750,000. It keys on when the fiscal year began, not when it ended.",
    body: [
      {
        h: "Three things people leave out of the calculation",
        p: [
          "It counts what was <strong>expended</strong>, not received. Money drawn down this " +
            "year against an award made two years ago counts this year.",
          "It counts <strong>pass-through subawards</strong>. Federal money that reached you " +
            "through a state agency, a university, or a larger nonprofit is still federal " +
            "money expended. This is the category most often missed, and for many small " +
            "organizations it is most of the total.",
          "It is the <strong>total across all federal sources</strong>, not per award.",
        ],
      },
      {
        h: "Where the number actually lives",
        p: [
          "Your Schedule of Expenditures of Federal Awards. No public dataset carries it, " +
            "which is why this tool reports the threshold that applies to your fiscal year " +
            "rather than telling you whether you crossed it.",
          "If you are near the line, talk to your auditor before the fiscal year ends rather " +
            "than after. A single audit is a months-long engagement, not a form.",
        ],
      },
    ],
  },
  sam_registration: {
    question: "How do I know if my SAM.gov registration is active?",
    answer:
      "Check it at sam.gov, or look it up here by EIN. An active registration in the System " +
      "for Award Management is required before any federal grant application can be submitted. " +
      "Registrations lapse annually and renewal is not automatic.",
    body: [
      {
        h: "The most common avoidable disqualification",
        p: [
          "A registration that reads “Active” today and expires in three weeks is the " +
            "thing that quietly disqualifies an application submitted next month. Renewal " +
            "takes ten to fifteen business days to take effect, so grantcheck warns at 60 " +
            "days rather than at expiry.",
          "Expired and never-registered are different problems with different timelines. " +
            "Renewing is a couple of weeks; registering for the first time is weeks, starting " +
            "with a Unique Entity ID request. A tool that collapses them misleads you about " +
            "how much runway you have.",
        ],
      },
      {
        h: "Why we sometimes cannot tell you",
        p: [
          "You cannot look up a SAM.gov entity by EIN. Taxpayer identification number is " +
            "sensitive-tier data, so it is not a search key on the public tier — the public " +
            "keys are Unique Entity ID, CAGE code, and legal business name.",
          "That means the link between an EIN and a SAM.gov registration has to be inferred " +
            "from name and state, and where the inference is not confident this tool says so " +
            "instead of guessing. “We could not identify your registration” is a " +
            "statement about our matching, not about your organization.",
        ],
      },
    ],
  },
  pub78_deductibility: {
    question: "What is IRS Publication 78, and why is my organization not listed?",
    answer:
      "Publication 78 Data is the IRS list of organizations eligible to receive tax-deductible " +
      "charitable contributions. Funders use it as fast proof of good standing. Absence is " +
      "often completely normal — most commonly because a group ruling covers you.",
    body: [
      {
        h: "Group exemption subordinates are absent by design",
        p: [
          "If your organization is a subordinate under another organization's group ruling, " +
            "you do not appear in Publication 78 in your own right. The central organization " +
            "is listed, and the ruling covers its subordinates. Roughly 238,000 organizations " +
            "are in this position.",
          "A funder asking for proof of deductibility wants the central organization's group " +
            "exemption letter, not a Publication 78 entry.",
        ],
      },
      {
        h: "Other reasons to be absent",
        p: [
          "Churches may receive deductible contributions without being listed. A very recent " +
            "recognition takes a monthly cycle or two to appear. And a revoked exemption " +
            "removes an organization from the list, which is the case worth ruling out first.",
        ],
      },
    ],
  },
  exempt_status: {
    question: "How do I check if a nonprofit is a 501(c)(3)?",
    answer:
      "Look up the EIN in the IRS Exempt Organizations Business Master File — which is what " +
      "this page does. Subsection 03 with an unconditional exemption status is what most " +
      "federal grant programs require.",
    body: [
      {
        h: "Absence is not evidence of a problem",
        p: [
          "Churches and their integrated auxiliaries are exempt without applying and are " +
            "largely absent from the Business Master File. Government instrumentalities are " +
            "exempt under different provisions. Newly recognized organizations take a cycle " +
            "or two to appear.",
          "None of those organizations has done anything wrong, and a tool that reports " +
            "absence as failure is telling several hundred thousand compliant organizations " +
            "something untrue.",
        ],
      },
    ],
  },
  organization_type: {
    question: "Can a private foundation apply for federal grants?",
    answer:
      "Usually not. Most federal grant programs restrict eligibility to public charities and " +
      "exclude private foundations in the eligibility section of the notice of funding " +
      "opportunity. It is worth settling before investing time in an application.",
    body: [
      {
        h: "It is a classification, not a verdict",
        p: [
          "Some programs do accept private foundations, and the classification itself can be " +
            "wrong or out of date on the IRS side. This tool reports what the Business Master " +
            "File records and points you at the specific notice, rather than deciding for you.",
        ],
      },
    ],
  },
  most_recent_filing: {
    question: "How do I find a nonprofit's most recent Form 990?",
    answer:
      "This page reports the most recent annual return on record for an EIN, and says which " +
      "source it came from — because the two sources disagree in an important way.",
    body: [
      {
        h: "Most small nonprofits are missing from the obvious source",
        p: [
          "The majority of exempt organizations file the Form 990-N e-Postcard, which does " +
            "not appear in the IRS Form 990 electronic-filing index at all. Building filing " +
            "history from that index alone reports roughly 1.5 million small nonprofits as " +
            "having never filed anything.",
        ],
      },
    ],
  },
  ntee: {
    question: "What is an NTEE code?",
    answer:
      "The National Taxonomy of Exempt Entities code is how the IRS classifies a nonprofit's " +
      "purpose — a letter for the major group and digits for the specific activity. Program " +
      "officers and funder search filters both use it.",
    body: [
      {
        h: "It is frequently wrong",
        p: [
          "NTEE codes are self-reported when an organization applies for recognition, and " +
            "rarely updated afterwards. An organization whose work has changed can be filtered " +
            "out of searches it belongs in. It is worth checking that the code still describes " +
            "what you do, and asking the IRS to correct it if not.",
        ],
      },
    ],
  },
  sam_expiration: {
    question: "When does a SAM.gov registration expire?",
    answer:
      "Annually, on a date specific to the registration. Renewal is not automatic, and it " +
      "takes ten to fifteen business days to take effect — so a registration expiring inside " +
      "two months is a problem for anything you plan to submit.",
    body: [
      {
        h: "Renew early, not at the deadline",
        p: [
          "The gap between submitting a renewal and it taking effect is where applications " +
            "fail. An organization that renews the week its registration expires can still be " +
            "inactive on the day a deadline lands.",
        ],
      },
    ],
  },
  uei: {
    question: "What is a Unique Entity ID and how do I get one?",
    answer:
      "The Unique Entity ID is the twelve-character identifier that replaced the DUNS number " +
      "as the federal government's way of identifying entities it does business with. You " +
      "request one free through sam.gov, and it is the first step of registering.",
    body: [
      {
        h: "No UEI means no federal award",
        p: [
          "Every federal grant application asks for it. Without a Unique Entity ID there is no " +
            "SAM.gov registration, and without a registration there is no award — so this is " +
            "the first thing to sort out, not the last.",
        ],
      },
    ],
  },
};

export function CheckExplainer(id: string, canonical: string) {
  const e = EXPLAINERS[id];
  if (!e) return null;

  return (
    <Page
      title={`${e.question} — grantcheck`}
      description={e.answer.slice(0, 300)}
      canonical={canonical}
      // FAQPage markup, because this page exists to answer one question verbatim.
      jsonLd={{
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: [
          {
            "@type": "Question",
            name: e.question,
            acceptedAnswer: { "@type": "Answer", text: e.answer },
          },
        ],
      }}
    >
      {/* The question as the H1, verbatim, answered inside the first forty words. */}
      <h1 style="margin-top:40px">{e.question}</h1>
      <p class="lede prose">{e.answer}</p>

      {e.body.map((section) => (
        <>
          <h2>{section.h}</h2>
          {section.p.map((para) => (
            // biome-ignore lint/security/noDangerouslySetInnerHtml: authored copy, not user input.
            <p class="prose" dangerouslySetInnerHTML={{ __html: para }} />
          ))}
        </>
      ))}

      <h2>Check an organization</h2>
      <form class="check" action="/check" method="get">
        <input name="ein" type="text" inputmode="numeric" placeholder="27-1067272" />
        <button type="submit">Check readiness</button>
      </form>
      <p class="hint">Free, no account. Every answer carries its source and date.</p>

      <Disclosure />
    </Page>
  );
}

export const EXPLAINER_IDS = Object.keys(EXPLAINERS);

export const Methodology: FC<{ canonical: string }> = ({ canonical }) => (
  <Page
    title="Methodology — grantcheck"
    description="Where every number comes from, how fresh it is, and what this tool deliberately will not tell you."
    canonical={canonical}
  >
    <h1 style="margin-top:40px">Methodology</h1>
    <p class="lede prose">
      Every fact on this site comes from a public federal dataset, and every page names the dataset
      and the date it was published. Nothing is proprietary and nothing is inferred silently.
    </p>

    <h2>What we do with the data</h2>
    <p class="prose">
      The IRS publishes four bulk files monthly. We parse them, join them on EIN, and publish the
      result as an index that both this site and the command-line tool read. The parsing is the hard
      part: the files have no header row, no quoting convention, and real rows contain the
      delimiter. Rows we cannot parse structurally are quarantined and counted rather than guessed
      at.
    </p>

    <h2>Where we infer rather than look up</h2>
    <p class="prose">
      Exactly one place. You cannot look up a SAM.gov entity by EIN, because taxpayer identification
      number is sensitive-tier data and is not a public search key. So the link between an
      organization and its SAM.gov registration is inferred from legal name and state, with a
      confidence score that is printed rather than hidden. Below a confidence floor we report that
      we could not identify the registration, which is a statement about our matching and not about
      the organization.
    </p>

    <h2>What this will not tell you</h2>
    <ul class="plain prose">
      <li>
        Whether you are eligible for a specific program. That lives in each notice of funding
        opportunity.
      </li>
      <li>Whether you will win. No public dataset contains that.</li>
      <li>
        A score, a grade, or a probability. There isn't one, and inventing one would be dishonest.
      </li>
    </ul>

    <h2>When we are wrong</h2>
    <p class="prose">
      The source files change without notice — columns move, code values appear that are not in the
      data dictionary, files get reposted mid-month with different contents under the same name. If
      a page here disagrees with the{" "}
      <a href="https://apps.irs.gov/app/eos/">IRS Tax Exempt Organization Search</a>, the IRS is
      right and we would like to know:{" "}
      <a href="https://github.com/egeria-corporation/grantcheck/issues">open an issue</a>.
    </p>

    <Disclosure />
  </Page>
);
