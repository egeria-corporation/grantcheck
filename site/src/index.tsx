/**
 * check.opengrants.io — edge-rendered federal grant readiness, one page per EIN.
 *
 * Why edge SSR rather than a static site: see docs/ADR-001.md. Short version, there are
 * ~1.4M 501(c)(3) organizations and Cloudflare Pages allows 20,000 files per deployment on
 * the free plan and 100,000 on paid. Pre-rendering one page per organization exceeds the
 * paid ceiling by an order of magnitude.
 */

import { Hono } from "hono";
import { cors } from "hono/cors";
import type { OrgRow, Vintage } from "./report";
import { buildReport, formatEin } from "./report";
import { CheckExplainer, Data, Methodology } from "./views/content";
import { Entity, NotFound } from "./views/entity";
import { Landing } from "./views/landing";
import { LLMS_TXT, ROBOTS_TXT } from "./views/robots";

type Bindings = { DB: D1Database };

const app = new Hono<{ Bindings: Bindings }>();

/** Nine digits after normalization, or it never touches the database. */
function normalizeEin(raw: string): string | null {
  const digits = raw.replace(/[\s–—-]/g, "");
  if (!/^[0-9]{9}$/.test(digits)) return null;
  if (digits.startsWith("00")) return null; // the IRS does not issue prefix 00
  return digits;
}

function canonicalUrl(c: { req: { url: string } }, path: string): string {
  const url = new URL(c.req.url);
  return `${url.origin}${path}`;
}

async function vintages(db: D1Database): Promise<Record<string, Vintage>> {
  const { results } = await db
    .prepare("SELECT dataset, published, source_url FROM dataset_vintage")
    .all<Vintage>();
  return Object.fromEntries((results ?? []).map((v) => [v.dataset, v]));
}

/**
 * Cache keyed on the dataset vintage. A new ingest changes the string and the entire edge
 * cache invalidates in one step — no purge call, no TTL guessing, and no window where two
 * pages disagree about what the data says.
 *
 * The `v` parameter is constructed server-side and never appears in a link, a canonical
 * tag, or the sitemap.
 */
function versionOf(v: Record<string, Vintage>): string {
  return Object.keys(v)
    .sort()
    .map((k) => v[k]?.published ?? "")
    .join(".");
}

// Pure IRS-derived pages change monthly at the fastest. Serve stale while revalidating: a
// figure four hours old beats a spinner, and the page states its vintage regardless.
const ENTITY_CACHE = "public, max-age=0, s-maxage=604800, stale-while-revalidate=86400";
const STATIC_CACHE = "public, s-maxage=86400";

app.get("/", async (c) => {
  const v = await vintages(c.env.DB).catch(() => ({}) as Record<string, Vintage>);
  const vintage = Object.values(v)[0]?.published;
  c.header("Cache-Control", STATIC_CACHE);
  return c.html(<Landing canonical={canonicalUrl(c, "/")} vintage={vintage} />);
});

/** The form target. Never renders a result — results live at a shareable URL. */
app.get("/check", (c) => {
  const raw = (c.req.query("ein") ?? "").trim();
  const ein = normalizeEin(raw);
  if (!ein) return c.redirect(`/search?q=${encodeURIComponent(raw)}`, 302);
  return c.redirect(`/ein/${formatEin(ein)}`, 302);
});

/** Unhyphenated and slug variants redirect. Two URLs must never serve one organization. */
app.get("/ein/:ein{[0-9]{9}}", (c) => c.redirect(`/ein/${formatEin(c.req.param("ein"))}`, 301));
app.get("/ein/:ein/:slug", (c) => {
  const ein = normalizeEin(c.req.param("ein"));
  return ein ? c.redirect(`/ein/${formatEin(ein)}`, 301) : c.notFound();
});

app.get("/ein/:ein", async (c) => {
  const ein = normalizeEin(c.req.param("ein"));
  // Validation before D1 is touched. This is the entire abuse surface of the site.
  if (!ein) return c.text("Not a valid EIN. Expected nine digits, e.g. 27-1067272.", 400);

  const canonical = canonicalUrl(c, `/ein/${formatEin(ein)}`);
  const v = await vintages(c.env.DB);
  const row = await c.env.DB.prepare("SELECT * FROM organization WHERE ein = ?")
    .bind(ein)
    .first<OrgRow>();

  if (!row) {
    c.header("Cache-Control", ENTITY_CACHE);
    return c.html(<NotFound ein={formatEin(ein)} canonical={canonical} />, 404);
  }

  c.header("Cache-Control", ENTITY_CACHE);
  c.header("X-Index-Vintage", versionOf(v));
  const report = buildReport(row, ein, v, new Date());
  return c.html(<Entity report={report} canonical={canonical} />);
});

/** Same JSON as `grantcheck --format json`. CORS open, no key. */
app.use("/api/*", cors());
app.get("/api/check/:ein", async (c) => {
  const ein = normalizeEin(c.req.param("ein"));
  if (!ein) return c.json({ error: "invalid_ein", message: "Expected nine digits." }, 400);

  const v = await vintages(c.env.DB);
  const row = await c.env.DB.prepare("SELECT * FROM organization WHERE ein = ?")
    .bind(ein)
    .first<OrgRow>();

  c.header("Cache-Control", ENTITY_CACHE);
  return c.json(buildReport(row ?? null, ein, v, new Date()), row ? 200 : 404);
});

app.get("/search", async (c) => {
  const q = (c.req.query("q") ?? "").trim();
  c.header("Cache-Control", "public, s-maxage=300");
  const rows = q
    ? ((
        await c.env.DB.prepare(
          "SELECT ein, name, city, state FROM organization WHERE name LIKE ? LIMIT 20",
        )
          .bind(`%${q.toUpperCase()}%`)
          .all<OrgRow>()
      ).results ?? [])
    : [];
  // noindex: this exists to find an EIN, not to be a directory.
  return c.html(
    <Data
      title="Search"
      canonical={canonicalUrl(c, "/search")}
      noindex
      heading={q ? `Organizations matching “${q}”` : "Find an EIN"}
    >
      {rows.length === 0 ? (
        <p class="prose">
          {q
            ? "No match in the cached index. Try the full legal name as the IRS records it, or enter the EIN directly."
            : "Enter an organization name to find its Employer Identification Number."}
        </p>
      ) : (
        <ul class="plain">
          {rows.map((r) => (
            <li>
              <a href={`/ein/${formatEin(r.ein)}`}>{r.name}</a>{" "}
              <span class="tag">
                {formatEin(r.ein)}
                {r.city ? ` · ${r.city}, ${r.state}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Data>,
  );
});

app.get("/checks/:id", (c) => {
  c.header("Cache-Control", STATIC_CACHE);
  const page = CheckExplainer(c.req.param("id"), canonicalUrl(c, `/checks/${c.req.param("id")}`));
  return page ? c.html(page) : c.notFound();
});

app.get("/methodology", (c) => {
  c.header("Cache-Control", STATIC_CACHE);
  return c.html(<Methodology canonical={canonicalUrl(c, "/methodology")} />);
});

app.get("/data", async (c) => {
  const v = await vintages(c.env.DB).catch(() => ({}) as Record<string, Vintage>);
  c.header("Cache-Control", STATIC_CACHE);
  return c.html(
    <Data title="The data" canonical={canonicalUrl(c, "/data")} heading="What is in the index">
      <p class="prose">
        Everything on this site derives from public IRS bulk datasets. Nothing is proprietary,
        nothing is inferred silently, and the whole pipeline is open source.
      </p>
      <table class="checks">
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Published</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {Object.values(v).map((entry) => (
            <tr>
              <td class="label">{entry.dataset}</td>
              <td class="asof">
                <time datetime={entry.published}>{entry.published}</time>
              </td>
              <td>
                <a href={entry.source_url}>{entry.source_url}</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Data>,
  );
});

app.get("/robots.txt", (c) => c.text(ROBOTS_TXT, 200, { "Content-Type": "text/plain" }));
app.get("/llms.txt", (c) => c.text(LLMS_TXT, 200, { "Content-Type": "text/plain" }));

app.notFound((c) => c.text("Not found", 404));

export default app;
