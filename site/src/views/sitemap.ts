/**
 * The sitemap index and the child sitemaps it points at.
 *
 * There are ~3.27M organizations in the index, which is 65 times the 50,000-URL ceiling in
 * the sitemaps.org protocol, so `/sitemap.xml` cannot be a `<urlset>`. It is a
 * `<sitemapindex>` naming one static child and N paginated entity children, each of which is
 * generated at the edge from D1. Nothing is pre-rendered, for the same reason the entity
 * pages are not — see docs/ADR-001.md.
 *
 * Two rules govern what goes in:
 *
 * 1. **Only URLs that resolve.** Every EIN is re-validated through `normalizeEin` on the way
 *    out, so a malformed row in the index can never become a `<loc>` that the site answers
 *    with a 400.
 * 2. **Only `lastmod` we can defend.** Google stops trusting the field across an entire site
 *    when it disagrees with what the crawler actually fetches, so a page whose last change
 *    the Worker cannot know carries no `lastmod` at all rather than a plausible guess.
 */

import { formatEin, normalizeEin } from "../report";
import { EXPLAINER_IDS } from "./content";
import { PRIVACY_CONTACT } from "./privacy";

/**
 * The sitemaps.org ceiling. A child may hold fewer URLs — and routinely will, see the
 * rowid-window note in src/index.tsx — but it may never hold more.
 */
export const URLS_PER_SITEMAP = 50_000;

/** The one child sitemap that is not a page of entities. */
export const STATIC_SITEMAP = "/sitemap-static.xml";

/** The path of the nth entity child. Pages are 1-based; page 0 would be an empty range. */
export function entitySitemapPath(page: number): string {
  return `/sitemap-${page}.xml`;
}

/**
 * The public pages that are not one-per-EIN, and what each can honestly claim as `lastmod`.
 *
 * `/` and `/data` re-render from `dataset_vintage`, so an ingest genuinely is their last
 * modification: they take the newest vintage date. `/privacy` states its own effective date.
 * `/methodology` and the eleven explainers are authored copy whose last change was a deploy,
 * and a Worker has no way to know when that was — so they are listed with no `lastmod`.
 *
 * Deliberately absent: `/search`, `/join`, `/roster`, `/bulk`, `/account` are `noindex` by
 * design and have no search value, and `/check` is a form target that only ever redirects.
 */
const STATIC_PAGES: Array<{ path: string; dated: "vintage" | "privacy" | "never" }> = [
  { path: "/", dated: "vintage" },
  { path: "/data", dated: "vintage" },
  { path: "/methodology", dated: "never" },
  { path: "/privacy", dated: "privacy" },
  ...EXPLAINER_IDS.map((id) => ({ path: `/checks/${id}`, dated: "never" as const })),
];

/** Every static path the sitemap advertises, for tests that want to walk them. */
export const STATIC_SITEMAP_PATHS = STATIC_PAGES.map((p) => p.path);

/**
 * Escape a `<loc>`.
 *
 * Nothing that reaches this today can contain an XML metacharacter — the paths are a closed
 * set, the EINs are re-validated to nine digits, and an origin cannot hold one. That is a
 * property of the current callers though, not of this file, so the file guarantees it
 * itself.
 */
function loc(url: string): string {
  return url
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function entry(tag: "url" | "sitemap", url: string, lastmod?: string): string {
  const when = lastmod ? `<lastmod>${lastmod}</lastmod>` : "";
  return `  <${tag}><loc>${loc(url)}</loc>${when}</${tag}>`;
}

/**
 * No `<changefreq>` and no `<priority>`.
 *
 * Google ignores both and has said so; every other consumer treats them as advisory at best.
 * Emitting them would mean inventing a number for 3.27M pages and publishing it as though it
 * meant something, which is the one thing this site does not do anywhere else.
 */
function document(root: "urlset" | "sitemapindex", entries: string[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<${root} xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries.join("\n")}
</${root}>
`;
}

/** `/sitemap.xml` — the static child, then one child per page of entities. */
export function sitemapIndex(origin: string, entityPages: number, vintage?: string): string {
  const children = [STATIC_SITEMAP];
  for (let page = 1; page <= entityPages; page++) children.push(entitySitemapPath(page));
  // Every child's newest URL changes when the ingest does, so the vintage is the honest
  // lastmod for all of them, static included — `/` and `/data` live in that one.
  return document(
    "sitemapindex",
    children.map((path) => entry("sitemap", `${origin}${path}`, vintage)),
  );
}

/** `/sitemap-static.xml` — everything that is not one-page-per-EIN. */
export function staticSitemap(origin: string, vintage?: string): string {
  const lastmod = { vintage, privacy: PRIVACY_CONTACT.effective, never: undefined };
  return document(
    "urlset",
    STATIC_PAGES.map((page) => entry("url", `${origin}${page.path}`, lastmod[page.dated])),
  );
}

/**
 * `/sitemap-N.xml` — one page of entity URLs.
 *
 * Rows whose `ein` the site would refuse are dropped rather than emitted: the index is
 * loaded from upstream files that have been known to carry placeholders, and a sitemap full
 * of URLs that answer 400 is worse than a shorter one.
 */
export function entitySitemap(origin: string, eins: string[], vintage?: string): string {
  const entries: string[] = [];
  for (const raw of eins) {
    const ein = normalizeEin(raw);
    if (ein) entries.push(entry("url", `${origin}/ein/${formatEin(ein)}`, vintage));
  }
  return document("urlset", entries);
}
