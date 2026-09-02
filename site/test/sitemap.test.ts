/**
 * The sitemap, end to end through the real Hono app.
 *
 * The claim being tested is narrower than "the XML parses". A sitemap is a promise to a
 * crawler, and there are exactly three ways to break the promise: advertise a URL that does
 * not resolve, advertise a URL your own robots.txt forbids fetching, or fail to advertise a
 * page that exists. Each has a test here, and the first two are checked by actually walking
 * every URL the sitemap emits rather than by asserting on a string.
 *
 * Pagination is checked at the boundary with explicit rowids rather than by inserting 50,001
 * organizations. The arithmetic is what can be wrong — an off-by-one that drops one row per
 * page loses 66 organizations across the index and nothing ever says so.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { app } from "../src/index";
import { EXPLAINER_IDS } from "../src/views/content";
import { ROBOTS_TXT } from "../src/views/robots";
import { STATIC_SITEMAP_PATHS, URLS_PER_SITEMAP } from "../src/views/sitemap";
import { type TestD1, testDb } from "./d1";

let db: TestD1 & D1Database;
const env = () => ({ DB: db }) as never;

const ORIGIN = "http://localhost";

async function get(path: string): Promise<Response> {
  return app.request(`${ORIGIN}${path}`, {}, env());
}

/** Insert one organization, optionally at a chosen rowid, so page boundaries are reachable. */
async function org(ein: string, rowid?: number): Promise<void> {
  await db
    .prepare(
      rowid === undefined
        ? "INSERT INTO organization (ein, name, in_bmf) VALUES (?, ?, 1)"
        : "INSERT INTO organization (ein, name, in_bmf, rowid) VALUES (?, ?, 1, ?)",
    )
    .bind(...(rowid === undefined ? [ein, `ORG ${ein}`] : [ein, `ORG ${ein}`, rowid]))
    .run();
}

/** Every `<loc>` in a sitemap or sitemap index, in document order. */
function locs(xml: string): string[] {
  return [...xml.matchAll(/<loc>([^<]*)<\/loc>/g)].map((m) => m[1] as string);
}

function lastmods(xml: string): string[] {
  return [...xml.matchAll(/<lastmod>([^<]*)<\/lastmod>/g)].map((m) => m[1] as string);
}

/**
 * Is `path` crawlable under a robots.txt, per RFC 9309?
 *
 * Rules are prefix matches; `$` anchors to the end; the most specific — longest — matching
 * rule wins, and `Allow` wins a tie. Small enough to be obviously right, which matters
 * because the point of it is to make "the sitemap never advertises a blocked URL" a real
 * assertion rather than a string comparison against the file we just wrote.
 */
function robotsAllows(robots: string, path: string): boolean {
  let best: { length: number; allow: boolean } = { length: -1, allow: true };
  for (const line of robots.split("\n")) {
    const rule = /^(Allow|Disallow):\s*(\S*)$/.exec(line.trim());
    if (!rule) continue;
    const pattern = rule[2] as string;
    const anchored = pattern.endsWith("$");
    const prefix = anchored ? pattern.slice(0, -1) : pattern;
    const matches = anchored ? path === prefix : path.startsWith(prefix);
    if (matches && prefix.length >= best.length) {
      best = { length: prefix.length, allow: rule[1] === "Allow" };
    }
  }
  return best.allow;
}

beforeEach(async () => {
  db = testDb();
  await db
    .prepare("INSERT INTO dataset_vintage (dataset, published, source_url) VALUES (?, ?, ?)")
    .bind("bmf", "2026-08-10", "https://www.irs.gov/")
    .run();
  await db
    .prepare("INSERT INTO dataset_vintage (dataset, published, source_url) VALUES (?, ?, ?)")
    .bind("pub78", "2026-07-14", "https://www.irs.gov/")
    .run();
});

describe("the sitemap index", () => {
  it("is served at the address robots.txt advertises", async () => {
    const advertised = /^Sitemap:\s*(\S+)$/m.exec(ROBOTS_TXT)?.[1];
    expect(advertised).toBe("https://check.opengrants.io/sitemap.xml");
    // The path of that URL, not the URL — the test app is not on the production origin.
    expect((await get(new URL(advertised as string).pathname)).status).toBe(200);
  });

  it("is a sitemapindex, not a urlset", async () => {
    const xml = await (await get("/sitemap.xml")).text();
    expect(xml).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(xml).toContain('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">');
    expect(xml).not.toContain("<urlset");
  });

  it("is served as XML", async () => {
    await org("271067272");
    for (const path of ["/sitemap.xml", "/sitemap-static.xml", "/sitemap-1.xml"]) {
      const res = await get(path);
      expect(res.headers.get("Content-Type"), path).toContain("application/xml");
    }
  });

  it("names the static child even when the index is empty", async () => {
    expect(locs(await (await get("/sitemap.xml")).text())).toEqual([
      `${ORIGIN}/sitemap-static.xml`,
    ]);
  });

  it("names one entity child per page of rowids", async () => {
    // One organization parked past two full windows: three pages, the first two empty. A
    // gap is legal and coverage is unaffected, which is the property being pinned.
    await org("271067272", URLS_PER_SITEMAP * 2 + 1);
    expect(locs(await (await get("/sitemap.xml")).text())).toEqual([
      `${ORIGIN}/sitemap-static.xml`,
      `${ORIGIN}/sitemap-1.xml`,
      `${ORIGIN}/sitemap-2.xml`,
      `${ORIGIN}/sitemap-3.xml`,
    ]);
  });

  it("dates every child with the newest vintage", async () => {
    await org("271067272");
    const xml = await (await get("/sitemap.xml")).text();
    // 2026-08-10 is newer than the 2026-07-14 Publication 78 vintage seeded alongside it.
    expect(lastmods(xml)).toEqual(["2026-08-10", "2026-08-10"]);
  });
});

describe("pagination", () => {
  it("splits exactly at the window boundary", async () => {
    await org("271067272", URLS_PER_SITEMAP - 1);
    await org("131644147", URLS_PER_SITEMAP);
    await org("530196605", URLS_PER_SITEMAP + 1);

    expect(locs(await (await get("/sitemap-1.xml")).text())).toEqual([
      `${ORIGIN}/ein/27-1067272`,
      `${ORIGIN}/ein/13-1644147`,
    ]);
    expect(locs(await (await get("/sitemap-2.xml")).text())).toEqual([`${ORIGIN}/ein/53-0196605`]);
  });

  it("never exceeds the protocol ceiling, because the window cannot", async () => {
    // A rowid window URLS_PER_SITEMAP wide holds at most that many rows whatever the data
    // does, so the guarantee is structural. This pins the constant against the spec.
    expect(URLS_PER_SITEMAP).toBeLessThanOrEqual(50_000);
  });

  it("404s a page past the end rather than serving empty sitemaps forever", async () => {
    await org("271067272");
    expect((await get("/sitemap-1.xml")).status).toBe(200);
    expect((await get("/sitemap-2.xml")).status).toBe(404);
    expect((await get("/sitemap-0.xml")).status).toBe(404);
  });

  it("serves each page from exactly one URL", async () => {
    await org("271067272");
    // /sitemap-01.xml would be a second address for page one. Two URLs, one document is the
    // thing the entity routes go out of their way to prevent; the sitemap is no different.
    expect((await get("/sitemap-01.xml")).status).toBe(404);
    expect((await get("/sitemap-1.0.xml")).status).toBe(404);
    expect((await get("/sitemap-abc.xml")).status).toBe(404);
    expect((await get("/sitemap-1.txt")).status).toBe(404);
    expect((await get("/sitemapX1.xml")).status).toBe(404);
  });
});

describe("what the entity sitemap contains", () => {
  it("lists only EINs in the organization table, hyphenated", async () => {
    await org("271067272");
    await org("001037180");
    const xml = await (await get("/sitemap-1.xml")).text();
    expect(locs(xml)).toEqual([`${ORIGIN}/ein/27-1067272`, `${ORIGIN}/ein/00-1037180`]);
    // Not a page for every EIN that could exist — only for rows we actually hold.
    expect(xml).not.toContain("13-1644147");
  });

  it("drops a row whose EIN the site would refuse", async () => {
    await org("271067272");
    await org("000000000"); // the all-zeros placeholder: /ein/00-0000000 answers 400
    await org("27106727"); // eight digits, from a bad upstream row
    expect(locs(await (await get("/sitemap-1.xml")).text())).toEqual([`${ORIGIN}/ein/27-1067272`]);
  });

  it("dates entity URLs with the newest vintage", async () => {
    await org("271067272");
    expect(lastmods(await (await get("/sitemap-1.xml")).text())).toEqual(["2026-08-10"]);
  });

  it("omits lastmod entirely when the index carries no vintage", async () => {
    await db.prepare("DELETE FROM dataset_vintage").run();
    await org("271067272");
    const xml = await (await get("/sitemap-1.xml")).text();
    expect(xml).toContain("<loc>");
    expect(xml).not.toContain("<lastmod>");
  });
});

describe("the static sitemap", () => {
  const staticPaths = async () =>
    locs(await (await get("/sitemap-static.xml")).text()).map((l) => new URL(l).pathname);

  it("lists the landing page, methodology, data, privacy and every explainer", async () => {
    const paths = await staticPaths();
    expect(paths).toContain("/");
    expect(paths).toContain("/methodology");
    expect(paths).toContain("/data");
    expect(paths).toContain("/privacy");
    for (const id of EXPLAINER_IDS) expect(paths, id).toContain(`/checks/${id}`);
    expect(EXPLAINER_IDS).toHaveLength(11);
  });

  it("omits every page that is noindex by design", async () => {
    const paths = await staticPaths();
    for (const path of ["/search", "/join", "/roster", "/bulk", "/account", "/check"]) {
      expect(paths, path).not.toContain(path);
    }
  });

  it("dates only the pages an ingest can actually change", async () => {
    const xml = await (await get("/sitemap-static.xml")).text();
    const entries = [...xml.matchAll(/<url>.*?<\/url>/g)].map((m) => m[0]);
    const dated = (path: string) =>
      entries.find((e) => e.includes(`<loc>${ORIGIN}${path}</loc>`))?.includes("<lastmod>");

    // These two re-render from dataset_vintage; the explainers are authored copy whose last
    // change was a deploy, and claiming a date for those would be a guess.
    expect(dated("/")).toBe(true);
    expect(dated("/data")).toBe(true);
    expect(dated("/methodology")).toBe(false);
    expect(dated("/checks/auto_revocation")).toBe(false);
    // The privacy policy states its own effective date, so it can carry a real one.
    expect(xml).toContain(`<loc>${ORIGIN}/privacy</loc><lastmod>2026-09-01</lastmod>`);
  });
});

describe("every URL the sitemap advertises is one a crawler can actually take", () => {
  it("resolves each static URL to a 200", async () => {
    for (const loc of locs(await (await get("/sitemap-static.xml")).text())) {
      const path = new URL(loc).pathname;
      expect((await get(path)).status, path).toBe(200);
    }
  });

  it("resolves each entity URL to a 200", async () => {
    await org("271067272");
    await org("001037180");
    for (const loc of locs(await (await get("/sitemap-1.xml")).text())) {
      const path = new URL(loc).pathname;
      expect((await get(path)).status, path).toBe(200);
    }
  });

  it("resolves each child of the index to a 200", async () => {
    await org("271067272");
    for (const loc of locs(await (await get("/sitemap.xml")).text())) {
      const path = new URL(loc).pathname;
      expect((await get(path)).status, path).toBe(200);
    }
  });

  it("advertises nothing its own robots.txt forbids fetching", async () => {
    await org("271067272");
    const advertised = [
      ...locs(await (await get("/sitemap-static.xml")).text()),
      ...locs(await (await get("/sitemap-1.xml")).text()),
      ...locs(await (await get("/sitemap.xml")).text()),
    ];
    expect(advertised.length).toBeGreaterThan(STATIC_SITEMAP_PATHS.length);
    for (const loc of advertised) {
      const path = new URL(loc).pathname;
      expect(robotsAllows(ROBOTS_TXT, path), path).toBe(true);
    }
  });
});

describe("robots.txt", () => {
  it("keeps the explainers crawlable while still blocking the form target", () => {
    // `Disallow: /check` is a prefix match, so it used to block all eleven /checks/ pages —
    // the site's entire high-intent search surface — while robots.txt looked correct.
    for (const id of EXPLAINER_IDS) {
      expect(robotsAllows(ROBOTS_TXT, `/checks/${id}`), id).toBe(true);
    }
    expect(robotsAllows(ROBOTS_TXT, "/check")).toBe(false);
    expect(robotsAllows(ROBOTS_TXT, "/check?ein=271067272")).toBe(false);
    expect(robotsAllows(ROBOTS_TXT, "/search")).toBe(false);
    expect(robotsAllows(ROBOTS_TXT, "/ein/27-1067272")).toBe(true);
    expect(robotsAllows(ROBOTS_TXT, "/")).toBe(true);
  });
});

describe("sitemap caching", () => {
  it("uses the same vintage-keyed strategy as the entity pages", async () => {
    await org("271067272");
    const entity = await get("/ein/27-1067272");
    for (const path of ["/sitemap.xml", "/sitemap-static.xml", "/sitemap-1.xml"]) {
      const res = await get(path);
      expect(res.headers.get("Cache-Control"), path).toBe(entity.headers.get("Cache-Control"));
      expect(res.headers.get("X-Index-Vintage"), path).toBe(entity.headers.get("X-Index-Vintage"));
    }
  });

  it("changes the vintage key when an ingest lands", async () => {
    const before = (await get("/sitemap.xml")).headers.get("X-Index-Vintage");
    await db
      .prepare("UPDATE dataset_vintage SET published = ? WHERE dataset = ?")
      .bind("2026-09-08", "bmf")
      .run();
    const after = await get("/sitemap.xml");
    expect(after.headers.get("X-Index-Vintage")).not.toBe(before);
    expect(lastmods(await after.text())[0]).toBe("2026-09-08");
  });

  it("never puts the cache key in a URL it publishes", async () => {
    await org("271067272");
    // The version string is constructed server-side precisely so it cannot leak into a
    // canonical tag or a sitemap and fragment the index.
    for (const path of ["/sitemap.xml", "/sitemap-static.xml", "/sitemap-1.xml"]) {
      expect(await (await get(path)).text(), path).not.toContain("?v=");
    }
  });
});
