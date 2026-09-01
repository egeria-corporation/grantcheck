/**
 * Page shell and the whole design system.
 *
 * The CSS is inlined and hand-written, under 15 KB, with no web fonts and no client
 * framework. That is not minimalism for its own sake: this page exists to be read by
 * crawlers and language models, and every byte of JavaScript between them and the facts is
 * pure cost. It also means no layout shift, because the page is fully formed at first paint.
 */

import type { FC, PropsWithChildren } from "hono/jsx";

export const SITE = "check.opengrants.io";
export const REPO = "https://github.com/egeria-corporation/grantcheck";

export const DISCLOSURE =
  "This is informational only, derived from public data on the dates shown. It is not an " +
  "eligibility determination, and not legal, tax, or accounting advice. Verify against the " +
  "official source before relying on it.";

/**
 * Palette and type. Defined once as tokens so the entity page, the landing page, and the
 * explainers cannot drift into looking like three different sites.
 */
const CSS = `
:root {
  --ink: #14171a;
  --ink-soft: #4a5057;
  --ink-faint: #6b7280;
  --line: #e3e6ea;
  --line-soft: #eef1f4;
  --paper: #ffffff;
  --paper-tint: #f7f9fb;
  --accent: #12594a;
  --accent-soft: #e6f2ee;
  --pass: #1a7f5a;
  --warn: #9a6212;
  --warn-soft: #fdf5e6;
  --fail: #a32020;
  --fail-soft: #fdeeee;
  --muted: #7b8794;
  --radius: 10px;
  --measure: 68ch;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}

@media (prefers-color-scheme: dark) {
  :root {
    --ink: #e8eaed;
    --ink-soft: #b3b9c0;
    --ink-faint: #8b939c;
    --line: #2a2f36;
    --line-soft: #21252b;
    --paper: #14171a;
    --paper-tint: #1a1e23;
    --accent: #6fd3b4;
    --accent-soft: #16302a;
    --pass: #5fc99b;
    --warn: #e0ac54;
    --warn-soft: #2c2416;
    --fail: #e88b8b;
    --fail-soft: #2e1c1c;
    --muted: #8b939c;
  }
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  font-family: var(--font);
  font-size: 17px;
  line-height: 1.65;
  color: var(--ink);
  background: var(--paper);
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { text-decoration-thickness: 2px; }
code, .mono { font-family: var(--mono); font-size: 0.92em; }

.wrap { max-width: 960px; margin: 0 auto; padding: 0 24px; }
.prose { max-width: var(--measure); }

header.site {
  border-bottom: 1px solid var(--line);
  padding: 18px 0;
  font-size: 15px;
}
header.site .wrap { display: flex; gap: 20px; align-items: baseline; flex-wrap: wrap; }
header.site .brand { font-weight: 650; color: var(--ink); text-decoration: none; letter-spacing: -0.01em; }
header.site nav { margin-left: auto; display: flex; gap: 20px; }
header.site nav a { color: var(--ink-soft); text-decoration: none; }
header.site nav a:hover { color: var(--accent); text-decoration: underline; }

h1 { font-size: 2.1rem; line-height: 1.2; letter-spacing: -0.02em; margin: 0 0 12px; font-weight: 680; }
h2 { font-size: 1.35rem; line-height: 1.3; letter-spacing: -0.01em; margin: 40px 0 12px; font-weight: 650; }
h3 { font-size: 1.05rem; margin: 28px 0 8px; font-weight: 650; }
p { margin: 0 0 16px; }
.lede { font-size: 1.17rem; line-height: 1.55; color: var(--ink-soft); }

.hero { padding: 64px 0 8px; }
.hero h1 { font-size: 2.7rem; max-width: 20ch; }
@media (max-width: 600px) { .hero { padding: 40px 0 4px; } .hero h1 { font-size: 2rem; } }

form.check { display: flex; gap: 10px; margin: 28px 0 10px; flex-wrap: wrap; }
form.check input {
  flex: 1 1 260px;
  font: inherit;
  font-family: var(--mono);
  padding: 13px 15px;
  border: 1.5px solid var(--line);
  border-radius: var(--radius);
  background: var(--paper);
  color: var(--ink);
}
form.check input:focus { outline: 2px solid var(--accent); outline-offset: 1px; border-color: transparent; }
form.check button {
  font: inherit;
  font-weight: 600;
  padding: 13px 24px;
  border: 0;
  border-radius: var(--radius);
  background: var(--accent);
  color: #fff;
  cursor: pointer;
}
@media (prefers-color-scheme: dark) { form.check button { color: #0c1a16; } }
form.check button:hover { filter: brightness(1.08); }
.hint { font-size: 14px; color: var(--muted); margin: 0; }

.grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin: 24px 0; }
.card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 18px 20px;
  background: var(--paper-tint);
}
.card h3 { margin: 0 0 6px; font-size: 0.98rem; }
.card p { margin: 0; font-size: 15px; color: var(--ink-soft); }

.terminal {
  /* The sample output is aligned columns; without this the whole block reflows into a
     paragraph and stops being recognisable as terminal output at all. */
  white-space: pre;
  background: #0f1419;
  color: #d7dde3;
  border-radius: var(--radius);
  padding: 20px 22px;
  overflow-x: auto;
  font-family: var(--mono);
  font-size: 13.5px;
  line-height: 1.6;
  margin: 24px 0;
  border: 1px solid #232a31;
}
.terminal .p { color: #5fc99b; }
.terminal .w { color: #e0ac54; }
.terminal .f { color: #e88b8b; }
.terminal .d { color: #7b8794; }
.terminal .c { color: #9ad7ff; }

.verdict { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin: 0 0 4px; }
.badge {
  display: inline-block;
  font-size: 13px;
  font-weight: 650;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  padding: 5px 11px;
  border-radius: 999px;
}
.badge.ready { background: var(--accent-soft); color: var(--pass); }
.badge.attention { background: var(--warn-soft); color: var(--warn); }
.badge.blocked { background: var(--fail-soft); color: var(--fail); }
.badge.not_found { background: var(--line-soft); color: var(--muted); }

.identity { color: var(--ink-soft); font-size: 15px; margin: 0 0 8px; }
.identity .ein { font-family: var(--mono); }

table.checks { width: 100%; border-collapse: collapse; margin: 8px 0 4px; font-size: 15.5px; }
table.checks th { text-align: left; font-size: 12.5px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 600; padding: 14px 0 6px; border-bottom: 1px solid var(--line); }
table.checks td { padding: 12px 12px 12px 0; border-bottom: 1px solid var(--line-soft); vertical-align: top; }
table.checks td.status, table.checks th.status { width: 1%; white-space: nowrap; padding-right: 18px; }
/* Visually hidden but read by screen readers and present for crawlers. */
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
table.checks td.label { width: 34%; color: var(--ink); }
table.checks td.asof { width: 1%; white-space: nowrap; color: var(--muted); font-size: 13.5px; font-family: var(--mono); }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; vertical-align: 1px; }
.dot.pass { background: var(--pass); }
.dot.warn { background: var(--warn); }
.dot.fail { background: var(--fail); }
.dot.unknown, .dot.not_applicable { background: var(--muted); }
.detail { color: var(--ink-soft); font-size: 14.5px; margin: 6px 0 0; max-width: 62ch; }

.note { border-left: 3px solid var(--line); padding: 2px 0 2px 16px; color: var(--ink-soft); font-size: 15px; margin: 20px 0; }
.disclosure { border-top: 1px solid var(--line); margin-top: 44px; padding-top: 18px; font-size: 14px; color: var(--muted); max-width: 70ch; }
.sources { font-size: 14px; color: var(--muted); margin: 24px 0 0; }
.sources a { color: var(--ink-soft); }

footer.site { border-top: 1px solid var(--line); margin-top: 56px; padding: 28px 0 56px; font-size: 14.5px; color: var(--muted); }
footer.site .wrap { display: flex; gap: 24px; flex-wrap: wrap; align-items: baseline; }
footer.site nav { display: flex; gap: 18px; flex-wrap: wrap; }
footer.site a { color: var(--ink-soft); }
.spacer { margin-left: auto; }

ul.plain { list-style: none; padding: 0; margin: 16px 0; }
ul.plain li { padding: 7px 0; border-bottom: 1px solid var(--line-soft); }
.tag { font-family: var(--mono); font-size: 13px; color: var(--muted); }
`;

export type HeadProps = {
  title: string;
  description: string;
  canonical?: string;
  noindex?: boolean;
  jsonLd?: unknown;
};

export const Page: FC<PropsWithChildren<HeadProps>> = ({
  title,
  description,
  canonical,
  noindex,
  jsonLd,
  children,
}) => (
  <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>{title}</title>
      <meta name="description" content={description} />
      {canonical ? <link rel="canonical" href={canonical} /> : null}
      {noindex ? <meta name="robots" content="noindex, follow" /> : null}
      <meta property="og:title" content={title} />
      <meta property="og:description" content={description} />
      <meta property="og:type" content="website" />
      {canonical ? <meta property="og:url" content={canonical} /> : null}
      <meta name="twitter:card" content="summary" />
      {/* Inlined: one round trip, no render-blocking stylesheet, no layout shift. */}
      {/* biome-ignore lint/security/noDangerouslySetInnerHtml: an authored constant, never
          user input, and a stylesheet has to be injected as raw text to be a stylesheet. */}
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      {jsonLd ? (
        <script
          type="application/ld+json"
          // biome-ignore lint/security/noDangerouslySetInnerHtml: JSON-LD must be raw.
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      ) : null}
    </head>
    <body>
      <header class="site">
        <div class="wrap">
          <a class="brand" href="/">
            grantcheck
          </a>
          <nav>
            <a href="/methodology">Methodology</a>
            <a href="/data">Data</a>
            <a href={REPO}>Source</a>
          </nav>
        </div>
      </header>
      <main class="wrap">{children}</main>
      <footer class="site">
        <div class="wrap">
          <span>
            Built by Egeria Corporation · sponsored by{" "}
            <a href="https://opengrants.io">OpenGrants</a>
          </span>
          <nav class="spacer">
            <a href={REPO}>Open source</a>
            <a href="/llms.txt">llms.txt</a>
            <a href="/api/check/27-1067272">JSON API</a>
          </nav>
        </div>
      </footer>
    </body>
  </html>
);

export const Disclosure: FC = () => <p class="disclosure">{DISCLOSURE}</p>;
