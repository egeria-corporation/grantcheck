/**
 * Name search.
 *
 * Two things are being pinned here. First, that search actually finds organizations by words
 * in the middle of their legal name — the IRS records the Red Cross as AMERICAN NATIONAL RED
 * CROSS, so a prefix-only search would fail the most obvious query anyone types. Second, and
 * more important, that no input can reach FTS5's query grammar: MATCH takes a small language
 * with operators and column filters, and unescaped user text there is both a 500 and a way to
 * probe the index.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { ftsQuery, searchByName } from "../src/search";
import { type TestD1, testDb } from "./d1";

let db: TestD1 & D1Database;

const ORGS: Array<[string, string, string, string]> = [
  ["530196605", "AMERICAN NATIONAL RED CROSS", "WASHINGTON", "DC"],
  ["271067272", "CODE FOR AMERICA LABS INC", "SAN FRANCISCO", "CA"],
  ["363673599", "FEEDING AMERICA", "CHICAGO", "IL"],
  ["135562976", "BOYS & GIRLS CLUBS OF AMERICA", "ATLANTA", "GA"],
  ["942278431", "DAVID AND LUCILE PACKARD FOUNDATION", "LOS ALTOS", "CA"],
  ["131644147", "AT&T FOUNDATION", "DALLAS", "TX"],
  ["000841363", "IGLESIA BETHESDA INC", "MIAMI", "FL"],
];

beforeEach(async () => {
  db = testDb();
  for (const [ein, name, city, state] of ORGS) {
    await db
      .prepare("INSERT INTO organization (ein, name, city, state, in_bmf) VALUES (?, ?, ?, ?, 1)")
      .bind(ein, name, city, state)
      .run();
  }
  // External-content FTS5 indexes the base table in place, so it is populated by rebuilding
  // from it — exactly as the monthly loader does.
  db.exec("INSERT INTO organization_fts(organization_fts) VALUES('rebuild');");
});

describe("ftsQuery", () => {
  it("quotes each token and ANDs them implicitly", () => {
    expect(ftsQuery("red cross")).toBe('"red" "cross"*');
  });

  it("prefix-matches only the final token", () => {
    // The earlier words are already typed; prefixing them all would match far too much.
    expect(ftsQuery("american nat")).toBe('"american" "nat"*');
  });

  it("does not prefix-match a single trailing character", () => {
    expect(ftsQuery("a")).toBe('"a"');
  });

  it("strips FTS5 operators rather than escaping them", () => {
    // Each of these is either a syntax error or an operator inside MATCH.
    for (const raw of [
      'red " cross',
      "red OR cross",
      "name:secret",
      "red*",
      "(red)",
      "red^cross",
    ]) {
      const q = ftsQuery(raw);
      expect(q, raw).not.toContain(":");
      expect(q, raw).not.toContain("^");
      expect(q, raw).not.toContain("(");
      // Any quote that survives is one this function added around a token.
      expect(q?.match(/"/g)?.length ?? 0, raw).toBe((q?.split('"').length ?? 1) - 1);
    }
  });

  it("returns null when nothing searchable remains", () => {
    for (const raw of ["", "   ", "!!!", "***", '"']) {
      expect(ftsQuery(raw), raw).toBeNull();
    }
  });

  it("caps the number of tokens", () => {
    const q = ftsQuery("a b c d e f g h i j k l m n o p");
    expect((q?.match(/"/g)?.length ?? 0) / 2).toBe(8);
  });
});

describe("searching", () => {
  it("finds a word in the middle of a legal name", async () => {
    // The whole reason for FTS5. The IRS name is AMERICAN NATIONAL RED CROSS, so a
    // prefix-only search would return nothing for the most obvious query anyone types.
    const hits = await searchByName(db, "red cross");
    expect(hits.map((h) => h.ein)).toContain("530196605");
  });

  it("requires every token to be present", async () => {
    const hits = await searchByName(db, "feeding america");
    expect(hits.map((h) => h.name)).toEqual(["FEEDING AMERICA"]);
  });

  it("matches tokens in any order", async () => {
    const hits = await searchByName(db, "cross red");
    expect(hits.map((h) => h.ein)).toContain("530196605");
  });

  it("is case insensitive", async () => {
    for (const q of ["FEEDING", "feeding", "FeEdInG"]) {
      expect((await searchByName(db, q)).length, q).toBeGreaterThan(0);
    }
  });

  it("prefix-matches a partial final word", async () => {
    const hits = await searchByName(db, "amer");
    expect(hits.length).toBeGreaterThan(0);
  });

  it("returns several organizations sharing a word", async () => {
    const hits = await searchByName(db, "america");
    // AMERICAN NATIONAL RED CROSS is not a match: "america" is a distinct token from
    // "american", and only the last token is prefix-matched.
    expect(hits.length).toBeGreaterThanOrEqual(3);
  });

  it("survives punctuation in the stored name", async () => {
    const hits = await searchByName(db, "boys girls clubs");
    expect(hits.map((h) => h.ein)).toContain("135562976");
  });

  it("survives punctuation in the query", async () => {
    // AT&T: the ampersand is dropped, leaving "at" and "t".
    const hits = await searchByName(db, "AT&T foundation");
    expect(hits.map((h) => h.ein)).toContain("131644147");
  });

  it("returns the fields the results page renders", async () => {
    const [hit] = await searchByName(db, "feeding america");
    expect(hit).toMatchObject({
      ein: "363673599",
      name: "FEEDING AMERICA",
      city: "CHICAGO",
      state: "IL",
    });
  });

  it("returns nothing for an unmatched query, without throwing", async () => {
    expect(await searchByName(db, "zzzznotanorganization")).toEqual([]);
  });

  it("returns nothing for a query that is only punctuation", async () => {
    expect(await searchByName(db, "!!!")).toEqual([]);
  });

  it("cannot be used to query another column", async () => {
    // `name:` is an FTS5 column filter. Stripped to plain tokens, this simply finds nothing.
    expect(await searchByName(db, "state:CA")).toEqual([]);
  });

  it("caps the number of results", async () => {
    for (let i = 0; i < 40; i++) {
      await db
        .prepare("INSERT INTO organization (ein, name, in_bmf) VALUES (?, ?, 1)")
        .bind(String(900000000 + i), `COMMON WORD ORGANIZATION ${i}`)
        .run();
    }
    db.exec("INSERT INTO organization_fts(organization_fts) VALUES('rebuild');");
    expect((await searchByName(db, "common word")).length).toBe(20);
  });
});

describe("rebuilding the index", () => {
  it("picks up organizations added since the last rebuild", async () => {
    await db
      .prepare("INSERT INTO organization (ein, name, in_bmf) VALUES (?, ?, 1)")
      .bind("111111111", "BRAND NEW CHARITY")
      .run();

    // Deliberately not found yet: there are no triggers, by design. The loader rebuilds.
    expect(await searchByName(db, "brand new charity")).toEqual([]);

    db.exec("INSERT INTO organization_fts(organization_fts) VALUES('rebuild');");
    expect((await searchByName(db, "brand new charity")).map((h) => h.ein)).toEqual(["111111111"]);
  });

  it("drops organizations removed since the last rebuild", async () => {
    await db.prepare("DELETE FROM organization WHERE ein = ?").bind("363673599").run();
    db.exec("INSERT INTO organization_fts(organization_fts) VALUES('rebuild');");
    expect(await searchByName(db, "feeding america")).toEqual([]);
  });
});
