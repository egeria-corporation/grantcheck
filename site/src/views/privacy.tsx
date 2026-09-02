/**
 * The privacy policy.
 *
 * Structured on the attorney-drafted U.S. template published by General Legal at
 * github.com/modernzen/legal-templates, which is released under CC0 1.0 — free to use,
 * modify and distribute without attribution. Every section that template includes for
 * legal-compliance reasons is kept: the state privacy rights notice, the CCPA disclosure
 * table, verification and authorized agents, Shine the Light, Nevada, Texas, retention,
 * security, children, changes, contact.
 *
 * Everything the template includes to describe a commercial SaaS product is **removed**
 * rather than left in and softened — advertising partners, payment processors, social login,
 * analytics, interest-based advertising, AI training on user data, mobile geolocation,
 * publicly visible profiles. This site does none of those things, and a policy that reserves
 * rights we do not exercise is not caution, it is a false description of the product. It
 * would also flatly contradict what the sign-in page promises, which is the one thing a
 * privacy policy must never do.
 *
 * The negative claims here are therefore load-bearing and must be checked against the code
 * before each change. As of this writing the site makes exactly one outbound request, to
 * Resend, to send mail; there is no analytics of any kind; there is one cookie; and Worker
 * invocation logging is switched off in wrangler.jsonc precisely so that "we do not keep a
 * record of which organizations were looked up" is true at the infrastructure level rather
 * than merely intended.
 */

import type { FC } from "hono/jsx";
import { Page, REPO } from "./layout";

/**
 * The contact details, in one place, because they appear in several sections and a policy
 * that gives two different addresses for the same purpose is worse than one that gives none.
 *
 * `email` is deliberately on opengrants.io rather than the oss.opengrants.io subdomain we
 * send from: that subdomain has no MX record and cannot receive mail at all, so an address
 * there would be a contact channel that silently swallows every deletion and access request
 * — the opposite of what several state privacy laws require. The same address is the
 * Reply-To on outbound mail, so replying to an alert reaches a person.
 *
 * The postal address is not decoration either: the CCPA requires a business serving
 * California residents to offer a non-electronic way to reach it.
 */
export const PRIVACY_CONTACT = {
  entity: "Egeria Corporation",
  email: "support@opengrants.io",
  street: "705 Gold Lake Drive, Suite 250",
  locality: "Folsom",
  region: "CA",
  postalCode: "95630",
  country: "USA",
  effective: "2026-09-01",
};

const Updated: FC = () => (
  <p class="identity">
    Effective <time datetime={PRIVACY_CONTACT.effective}>{PRIVACY_CONTACT.effective}</time>
  </p>
);

export const Privacy: FC<{ canonical: string }> = ({ canonical }) => (
  <Page
    title="Privacy policy — grantcheck"
    description="What check.opengrants.io collects, what it does not, and how to delete it. One cookie, two service providers, no analytics, no tracking, no sale of personal information."
    canonical={canonical}
  >
    <h1 style="margin-top:44px">Privacy policy</h1>
    <Updated />

    <p class="lede prose">
      {PRIVACY_CONTACT.entity} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) operates{" "}
      <strong>check.opengrants.io</strong> (the &ldquo;Service&rdquo;), a free tool that reports
      whether a US nonprofit is mechanically ready to apply for federal grants, using published IRS
      data. This policy describes what the Service collects, what it does not, and how to remove it.
    </p>

    <div class="note prose">
      <p style="margin:0 0 10px">
        <strong>The short version.</strong> You can use most of this site without giving us
        anything. Reading a report needs no account, and we do not record which organizations are
        looked up. If you sign in, we hold your name, your email address, and the list of
        organizations you chose to save — nothing else. There is no tracking of any kind, we never
        sell or share your information, and one button on your account page deletes all of it
        immediately.
      </p>
      <p style="margin:0">
        If you would rather give us nothing at all, <a href={REPO}>the command-line tool</a> does
        everything this site does, on your own machine.
      </p>
    </div>

    <h2>What this policy covers</h2>
    <p class="prose">This policy covers the website at check.opengrants.io only.</p>
    <ul class="plain prose">
      <li>
        <strong>
          The grantcheck command-line tool and MCP server are not covered, because they collect
          nothing.
        </strong>{" "}
        They run entirely on your machine and send us no reports, no telemetry, and no record of
        what you checked. They do download the published index files from our CDN, which — like any
        file download — reveals your IP address and which index shard you requested to the network.
        A shard covers a whole two-digit EIN prefix, so it does not identify the organization you
        were interested in.
      </li>
      <li>
        <strong>opengrants.io is a separate service</strong> operated under its own privacy policy.
        Signing in here does not create an account there, and we do not send your information to it.
      </li>
      <li>
        <strong>Sites we link to are not covered.</strong> The IRS, ProPublica, SAM.gov and others
        have their own policies. Following a link from a report page tells them you visited, not us.
      </li>
    </ul>

    <h2>Personal information we collect</h2>

    <h3>If you sign in</h3>
    <p class="prose">
      Signing in is optional and unlocks only bulk checking, saved rosters, monitoring and export.
      We collect:
    </p>
    <ul class="plain prose">
      <li>
        <strong>Your name and email address</strong>, which you type into the sign-in form. The
        address is how monitoring alerts reach you; without one, monitoring cannot work.
      </li>
      <li>
        <strong>The organizations you save</strong> — their EINs and any labels you add.
      </li>
      <li>
        <strong>Sign-in and session tokens</strong>, stored only as irreversible SHA-256 hashes,
        never as the tokens themselves, together with their creation and expiry times.
      </li>
    </ul>
    <p class="prose">
      <strong>Asking for a sign-in link does not create an account.</strong> An account exists only
      once somebody opens the link, proving they can read that mailbox. If you receive a sign-in
      email you did not request, nothing has been created in your name and you need do nothing.
    </p>

    <h3>Everyone, signed in or not</h3>
    <p class="prose">
      Serving a web page necessarily involves receiving a request. Our hosting provider, Cloudflare,
      processes your IP address, your browser&rsquo;s user agent, and the address you requested in
      order to deliver the response and to protect the Service from attack and abuse. That
      processing is transient and governed by{" "}
      <a href="https://www.cloudflare.com/privacypolicy/">Cloudflare&rsquo;s privacy policy</a>.
    </p>
    <p class="prose">
      <strong>We have switched off request logging.</strong> Our hosting platform offers per-request
      logs that would retain the address of every page requested for several days. For this Service
      that address is the sensitive fact — a log of <span class="mono">/ein/12-3456789</span> is a
      record of who looked up which organization — so we have disabled it. We keep no such log, and
      we cannot produce one for a past date, because it was never written.
    </p>

    <h3>What we do not collect</h3>
    <p class="prose">
      These are not reservations of rights we might exercise later. They are descriptions of what
      the code does, and each is checkable in <a href={REPO}>the public source</a>:
    </p>
    <ul class="plain prose">
      <li>
        <strong>No analytics.</strong> No Google Analytics, no product analytics, no pixels, no
        clear GIFs, no beacons, no session recording, no heatmaps.
      </li>
      <li>
        <strong>No third-party scripts.</strong> The pages load no JavaScript from anyone else, and
        in fact load almost no JavaScript at all.
      </li>
      <li>
        <strong>No advertising.</strong> We run none, we work with no advertising partners, and we
        do not build or buy audience segments.
      </li>
      <li>
        <strong>No tracking cookies, and no cross-site tracking.</strong> See Cookies below.
      </li>
      <li>
        <strong>No payment information.</strong> The Service is free and there is nothing to buy, so
        there is no payment processor.
      </li>
      <li>
        <strong>No social login</strong> and no connections to social platforms.
      </li>
      <li>
        <strong>No location data</strong> beyond the country-level information inherent in an IP
        address, which we do not store.
      </li>
      <li>
        <strong>No sensitive personal information</strong> as defined by state privacy laws. We do
        not ask for it and have no use for it.
      </li>
      <li>
        <strong>No profiles, no public content, no messaging.</strong> There is nothing on this site
        that other users can see about you.
      </li>
      <li>
        <strong>No training of AI models on your information.</strong>
      </li>
    </ul>

    <h2>Cookies</h2>
    <p class="prose">
      The Service sets <strong>one</strong> cookie, and only after you sign in:
    </p>
    <table class="checks">
      <thead>
        <tr>
          <th>Cookie</th>
          <th>Purpose</th>
          <th>Expires</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="label mono">gc_session</td>
          <td>
            Keeps you signed in. It holds a random session identifier and nothing else — no name, no
            email address, no record of what you viewed. It is marked{" "}
            <span class="mono">HttpOnly</span> so scripts cannot read it and{" "}
            <span class="mono">SameSite=Lax</span> so other sites cannot use it.
          </td>
          <td class="asof">30 days</td>
        </tr>
      </tbody>
    </table>
    <p class="prose">
      That cookie is strictly necessary: without it, signing in cannot work. There are no analytics,
      advertising or preference cookies, which is why this site shows no cookie consent banner —
      there is nothing to consent to. Signing out deletes it.
    </p>

    <h2>How we use personal information</h2>
    <p class="prose">We use it for three purposes, and no others:</p>
    <ul class="plain prose">
      <li>
        <strong>To sign you in.</strong> Sending the link, and keeping you signed in afterwards.
      </li>
      <li>
        <strong>To keep your roster.</strong> Storing the organizations you saved so they are there
        next time.
      </li>
      <li>
        <strong>To send the alerts you asked for.</strong> Re-checking your saved organizations
        against each monthly IRS release and emailing you when a verdict changes. If nothing
        changes, we send nothing.
      </li>
    </ul>
    <p class="prose">
      We may also use it to comply with the law, to enforce our terms, and to protect the Service,
      our users, and the public from fraud, abuse or security threats.
    </p>
    <p class="prose">
      <strong>We do not send marketing email.</strong> The only messages you will receive are your
      sign-in links and the monitoring alerts you asked for. There is no newsletter and no
      promotional list.
    </p>

    <h2>How we share personal information</h2>
    <p class="prose">
      We use two service providers, and they are the only third parties that receive anything:
    </p>
    <table class="checks">
      <thead>
        <tr>
          <th>Provider</th>
          <th>What it receives</th>
          <th>Why</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="label">
            <a href="https://www.cloudflare.com/privacypolicy/">Cloudflare</a>
          </td>
          <td>Requests to the site, and the database in which accounts and rosters are stored</td>
          <td>Hosting, content delivery, and the database itself</td>
        </tr>
        <tr>
          <td class="label">
            <a href="https://resend.com/legal/privacy-policy">Resend</a>
          </td>
          <td>Your email address and the content of the message</td>
          <td>Delivering sign-in links and monitoring alerts</td>
        </tr>
      </tbody>
    </table>
    <p class="prose">
      We may also disclose information to law enforcement or other authorities where we believe in
      good faith that the law requires it, and to professional advisers such as lawyers and auditors
      in the course of the services they provide us. If the Service is ever transferred to another
      organization — through a merger, acquisition, or transfer of assets — account information may
      transfer with it, and we would give notice here before that took effect.
    </p>
    <p class="prose">
      <strong>
        We do not sell your personal information, and we do not share it for cross-context
        behavioural advertising
      </strong>
      , as those terms are defined by state privacy laws. We have never done so.
    </p>

    <h2>How long we keep it</h2>
    <table class="checks">
      <thead>
        <tr>
          <th>What</th>
          <th>How long</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="label">Your account and roster</td>
          <td>Until you delete it. There is no inactivity expiry.</td>
        </tr>
        <tr>
          <td class="label">Sign-in links</td>
          <td>
            15 minutes, and they work once. The record is deleted as soon as it is used or expires.
          </td>
        </tr>
        <tr>
          <td class="label">Sessions</td>
          <td>30 days, then deleted. Signing out deletes yours immediately.</td>
        </tr>
        <tr>
          <td class="label">Request logs</td>
          <td>Not kept. See above.</td>
        </tr>
        <tr>
          <td class="label">Sent email</td>
          <td>
            Retained briefly by our email provider under its own policy, as delivery requires.
          </td>
        </tr>
      </tbody>
    </table>

    <h2>Deleting your account</h2>
    <p class="prose">
      Go to <a href="/account">your account page</a> and use the delete button. This removes your
      account, your roster, every active session and any outstanding sign-in links{" "}
      <strong>immediately and permanently</strong>. There is no queue, no waiting period, no email
      to send, and no soft-delete: the rows are gone and cannot be restored, by you or by us.
    </p>
    <p class="prose">
      Deleting stops all email, since we hold nothing to send to. If you would rather keep the
      account and stop the alerts, remove the organizations from your roster — monitoring only
      reports on saved organizations.
    </p>

    <h2>Your choices and rights</h2>
    <ul class="plain prose">
      <li>
        <strong>Access and correction.</strong> Your account page shows everything we hold about
        you. To have anything corrected, email us.
      </li>
      <li>
        <strong>Deletion.</strong> Immediate and self-service, as above. You do not need to ask.
      </li>
      <li>
        <strong>Email.</strong> We send no marketing, so there is nothing to unsubscribe from.
        Alerts stop when you empty your roster or delete your account.
      </li>
      <li>
        <strong>Cookies.</strong> Your browser can block or clear the one cookie we set; you will be
        signed out.
      </li>
      <li>
        <strong>Do Not Track and Global Privacy Control.</strong> We do not track you across sites
        and do not sell or share personal information, so there is nothing for these signals to
        switch off. We honour them regardless.
      </li>
      <li>
        <strong>Declining to give us anything.</strong> Reports, the explainers and the JSON API
        need no account and never will. You can also run <a href={REPO}>the open source tool</a>{" "}
        entirely on your own machine.
      </li>
    </ul>

    <h2>State privacy rights</h2>
    <p class="prose">
      Several US states give residents rights over personal information. Depending on where you
      live, you may have the right to know what we have collected, to obtain a copy, to correct it,
      to delete it, to opt out of sale, sharing for targeted advertising, or profiling, to appeal a
      refusal, and not to be discriminated against for exercising any of these.
    </p>
    <p class="prose">
      Three of those need no request here, because the underlying practice does not exist:{" "}
      <strong>
        we do not sell personal information, we do not share it for targeted advertising, and we do
        not use it for profiling or automated decision-making.
      </strong>{" "}
      Deletion is self-service and immediate. For anything else, email us and we will respond within
      the time the applicable law allows.
    </p>
    <p class="prose">
      <strong>Verifying who you are.</strong> Because we hold so little, verification is simple: we
      will ask you to confirm the request from the email address on the account. We do not ask for
      identity documents, and you should be suspicious of anyone claiming to be us who does. An
      authorized agent may act for you where the law allows, and we may ask for proof of their
      authority.
    </p>

    <h3>Categories collected, in the terms the CCPA uses</h3>
    <p class="prose">
      This describes our practices currently and for the twelve months before the effective date of
      this policy.
    </p>
    <table class="checks">
      <thead>
        <tr>
          <th>What we collect</th>
          <th>CCPA category</th>
          <th>Why</th>
          <th>Disclosed to</th>
          <th>Sold or shared</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="label">Name, email address</td>
          <td>Identifiers</td>
          <td>Sign-in, monitoring alerts</td>
          <td>Hosting and email providers</td>
          <td>No</td>
        </tr>
        <tr>
          <td class="label">Saved EINs and labels</td>
          <td>Identifiers; commercial information</td>
          <td>Keeping your roster; monitoring</td>
          <td>Hosting provider</td>
          <td>No</td>
        </tr>
        <tr>
          <td class="label">Session and sign-in token hashes</td>
          <td>Identifiers</td>
          <td>Keeping you signed in</td>
          <td>Hosting provider</td>
          <td>No</td>
        </tr>
        <tr>
          <td class="label">IP address, user agent</td>
          <td>Identifiers; internet activity</td>
          <td>Delivering the page; security</td>
          <td>Hosting provider</td>
          <td>No</td>
        </tr>
      </tbody>
    </table>
    <p class="prose">
      We collect no other CCPA category — no financial information, no biometric or geolocation
      data, no sensitive personal information, and no inferences drawn to create a profile. We do
      not attempt to re-identify de-identified data.
    </p>

    <h3>California, Nevada and Texas</h3>
    <p class="prose">
      <strong>California &ldquo;Shine the Light&rdquo;.</strong> California residents may ask which
      personal information we disclosed to third parties for their direct marketing purposes. We
      disclose none, because we do no direct marketing. Requests may be sent to the address below
      with the subject &ldquo;Shine the Light Request&rdquo;.
    </p>
    <p class="prose">
      <strong>Nevada.</strong> Nevada residents may opt out of the sale of personal information for
      monetary consideration. We do not make such sales. Should that ever change, we would say so
      here first.
    </p>
    <p class="prose">
      <strong>Texas.</strong> We do not sell sensitive or biometric personal data as the Texas Data
      Privacy and Security Act defines those terms.
    </p>

    <h2>Security</h2>
    <p class="prose">
      We use technical and organizational safeguards designed to protect what we hold. Some are
      worth naming because they are structural rather than promises: there are{" "}
      <strong>no passwords</strong> on this Service, so there is no password database to breach;
      sign-in and session tokens are stored only as irreversible hashes, so reading our database
      would not yield a working credential; and the session cookie cannot be read by scripts. We
      hold no payment information because we take no payments.
    </p>
    <p class="prose">
      No system is perfectly secure, and we cannot guarantee the security of information transmitted
      over the internet. To report a vulnerability, see{" "}
      <a href={`${REPO}/security/policy`}>our security policy</a>.
    </p>

    <h2>International transfers</h2>
    <p class="prose">
      We are based in the United States and our providers operate there and elsewhere. If you use
      the Service from outside the United States, your information will be processed in the United
      States, where privacy laws may differ from those where you live.
    </p>

    <h2>Children</h2>
    <p class="prose">
      The Service is meant for people doing professional grant work and is not directed at children.
      We do not knowingly collect personal information from anyone under 18. If you believe a child
      has given us information, contact us and we will delete it.
    </p>

    <h2>Changes to this policy</h2>
    <p class="prose">
      We may update this policy. The effective date at the top always reflects the current version,
      and because this site is open source, every past version and the exact change between them is
      in <a href={`${REPO}/commits/main/site/src/views/privacy.tsx`}>the public git history</a> —
      you do not have to take our word for what it used to say. If we ever make a change that
      materially reduces the protections described here, we will say so prominently rather than
      quietly changing the date.
    </p>

    <h2>How to contact us</h2>
    <p class="prose">
      For any privacy question or request, including access, correction and deletion:
    </p>
    <ul class="plain prose">
      <li>
        <strong>Email:</strong>{" "}
        <a href={`mailto:${PRIVACY_CONTACT.email}`}>{PRIVACY_CONTACT.email}</a> — read by a person,
        and the address replies to our emails go to.
      </li>
      <li>
        <strong>Post:</strong>
        {/* A real <address> element, so a screen reader announces it as an address and a
            parser can lift it. Marked up with h-card class names for the same reason the
            entity pages carry schema.org: machine-readable costs nothing here. */}
        <address class="postal h-card">
          <span class="p-name">{PRIVACY_CONTACT.entity}</span>
          <br />
          <span class="p-street-address">{PRIVACY_CONTACT.street}</span>
          <br />
          <span class="p-locality">{PRIVACY_CONTACT.locality}</span>,{" "}
          <span class="p-region">{PRIVACY_CONTACT.region}</span>{" "}
          <span class="p-postal-code">{PRIVACY_CONTACT.postalCode}</span>
          <br />
          <span class="p-country-name">{PRIVACY_CONTACT.country}</span>
        </address>
      </li>
    </ul>

    <p class="disclosure">
      This policy describes how we handle information about <em>you</em>. It is not about the
      organizations the Service reports on: those reports are derived entirely from datasets the IRS
      publishes for public use, and describe organizations rather than individuals.
    </p>
  </Page>
);
