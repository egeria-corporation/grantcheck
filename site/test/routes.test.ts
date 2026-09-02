/**
 * The gate, end to end, through the real Hono app.
 *
 * Two claims are load-bearing and both are made in public copy:
 *
 * 1. **Report pages stay open.** Reports, explainers and the JSON API must work with no
 *    session at all. If signing in ever became the price of an answer, the entire argument
 *    for the site — that it is worth indexing and citing — collapses.
 * 2. **A roster belongs to exactly one account.** This is the only place the site joins a
 *    person to a set of EINs, so a leak here is the leak the privacy policy rules out.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { SESSION_COOKIE, issueLoginToken, redeemLoginToken } from "../src/auth";
import { app } from "../src/index";
import { normalizeEin } from "../src/report";
import { parseEinList } from "../src/routes/account";
import { type TestD1, testDb } from "./d1";

let db: TestD1 & D1Database;
const env = () => ({ DB: db }) as never;

const ORG = {
  ein: "271067272",
  name: "CODE FOR AMERICA LABS INC",
  city: "SAN FRANCISCO",
  state: "CA",
  subsection: "03",
  classification: "1000",
  affiliation: "3",
  deductibility: "1",
  foundation: "15",
  organization_form: "1",
  exempt_status: "01",
  tax_period: "202412",
  filing_req_cd: "01",
  ntee_cd: "W20",
  pub78_deductibility_code: "PC",
};

beforeEach(async () => {
  db = testDb();
  const cols = Object.keys(ORG);
  await db
    .prepare(
      `INSERT INTO organization (${cols.join(",")}, in_bmf, in_pub78) VALUES (${cols
        .map(() => "?")
        .join(",")}, 1, 1)`,
    )
    .bind(...Object.values(ORG))
    .run();
  await db
    .prepare("INSERT INTO dataset_vintage (dataset, published, source_url) VALUES (?, ?, ?)")
    .bind("bmf", "2026-08-10", "https://www.irs.gov/")
    .run();
});

async function signIn(email = "ada@example.org", name = "Ada"): Promise<string> {
  const token = await issueLoginToken(db, email, name);
  const result = await redeemLoginToken(db, token);
  if (!result) throw new Error("redeem failed");
  return result.sessionToken;
}

async function get(path: string, session?: string): Promise<Response> {
  return app.request(
    `http://localhost${path}`,
    { headers: session ? { Cookie: `${SESSION_COOKIE}=${session}` } : {} },
    env(),
  );
}

async function post(
  path: string,
  form: Record<string, string>,
  session?: string,
): Promise<Response> {
  return app.request(
    `http://localhost${path}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        ...(session ? { Cookie: `${SESSION_COOKIE}=${session}` } : {}),
      },
      body: new URLSearchParams(form).toString(),
    },
    env(),
  );
}

describe("the public site stays public", () => {
  it("serves an entity page with no session", async () => {
    const res = await get("/ein/27-1067272");
    expect(res.status).toBe(200);
    const html = await res.text();
    expect(html).toContain("CODE FOR AMERICA LABS INC");
    expect(html).toContain("27-1067272");
  });

  it("serves the JSON API with no session", async () => {
    const res = await get("/api/check/27-1067272");
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ein: string; readiness: string };
    expect(body.ein).toBe("27-1067272");
    expect(body.readiness).toBeTruthy();
  });

  it("serves landing, methodology, data and explainers with no session", async () => {
    for (const path of [
      "/",
      "/methodology",
      "/data",
      "/privacy",
      "/checks/exempt_status",
      "/robots.txt",
    ]) {
      expect((await get(path)).status, path).toBe(200);
    }
  });

  it("keeps entity pages cacheable and indexable", async () => {
    const res = await get("/ein/27-1067272");
    // If these ever became private/no-store, every report would drop out of every index.
    expect(res.headers.get("Cache-Control")).toContain("s-maxage");
    expect(await res.text()).not.toContain("noindex");
  });
});

describe("EIN validation", () => {
  it("accepts the 00 prefix, which the IRS does issue", () => {
    // 136 organizations in the published index carry it: 19 in the Business Master File,
    // 14 in Publication 78, and 90 on the automatic revocation list. Rejecting the prefix
    // made those 90 answer "not a valid EIN" instead of "revoked".
    expect(normalizeEin("00-1037180")).toBe("001037180");
    expect(normalizeEin("000841363")).toBe("000841363");
  });

  it("rejects the all-zeros placeholder", () => {
    expect(normalizeEin("00-0000000")).toBeNull();
  });

  it("rejects anything that is not nine digits", () => {
    for (const raw of ["", "abc", "1234", "27/0125367", "٢٧٠١٢٥٣٦٧"]) {
      expect(normalizeEin(raw), raw).toBeNull();
    }
  });

  it("serves a prefix-00 organization rather than a 400", async () => {
    await db
      .prepare(
        "INSERT INTO organization (ein, name, in_bmf, in_revocation, revocation_date) " +
          "VALUES (?, ?, 1, 1, ?)",
      )
      .bind("001037180", "A REVOKED CHURCH", "2026-05-15")
      .run();
    const res = await get("/ein/00-1037180");
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("A REVOKED CHURCH");
  });
});

describe("the gate", () => {
  it("bounces a signed-out visitor to sign-in, remembering the destination", async () => {
    for (const path of ["/roster", "/bulk", "/account", "/roster/export.csv"]) {
      const res = await get(path);
      expect(res.status, path).toBe(302);
      expect(res.headers.get("Location"), path).toBe(`/join?next=${encodeURIComponent(path)}`);
    }
  });

  it("lets a signed-in visitor through", async () => {
    const session = await signIn();
    const res = await get("/roster", session);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("Your roster");
  });

  it("never caches a signed-in page", async () => {
    const session = await signIn();
    const res = await get("/roster", session);
    expect(res.headers.get("Cache-Control")).toBe("private, no-store");
  });

  it("marks account pages noindex", async () => {
    const session = await signIn();
    expect(await (await get("/roster", session)).text()).toContain("noindex");
    expect(await (await get("/join")).text()).toContain("noindex");
  });

  it("treats a forged cookie as signed out", async () => {
    const res = await get("/roster", "f".repeat(64));
    expect(res.status).toBe(302);
  });
});

describe("sign-in", () => {
  it("shows the same page whether or not the address is known", async () => {
    const first = await post("/join", { name: "Ada", email: "ada@example.org" });
    const second = await post("/join", { name: "Ada", email: "ada@example.org" });
    expect(await first.text()).toBe(await second.text());
  });

  it("rate limits sign-in mail per address", async () => {
    for (let i = 0; i < 5; i++) {
      await post("/join", { name: "Ada", email: "ada@example.org" });
    }
    // Three issued, the rest silently declined — and the page is identical either way, so
    // the form cannot be used to probe whether an address is being targeted.
    expect(db.raw("SELECT * FROM login_token")).toHaveLength(3);
  });

  it("rate limits one address without affecting another", async () => {
    for (let i = 0; i < 5; i++) await post("/join", { name: "Ada", email: "ada@example.org" });
    await post("/join", { name: "Eve", email: "eve@example.org" });
    expect(db.raw("SELECT * FROM login_token WHERE email = 'eve@example.org'")).toHaveLength(1);
  });

  it("rejects a malformed address without issuing anything", async () => {
    const res = await post("/join", { name: "Ada", email: "not-an-address" });
    expect(await res.text()).toContain("does not look like an email address");
    expect(db.raw("SELECT * FROM login_token")).toHaveLength(0);
  });

  it("refuses an off-site redirect after sign-in", async () => {
    // `next` is attacker-controlled, so the sign-in flow must not be usable as a redirector.
    for (const next of ["https://evil.example", "//evil.example", "http://evil.example/x"]) {
      const token = await issueLoginToken(db, "ada@example.org", "Ada");
      const res = await get(`/auth/verify?token=${token}&next=${encodeURIComponent(next)}`);
      expect(res.headers.get("Location"), next).toBe("/roster");
    }
  });

  it("honours a same-site redirect", async () => {
    const token = await issueLoginToken(db, "ada@example.org", "Ada");
    const res = await get(`/auth/verify?token=${token}&next=%2Fbulk`);
    expect(res.headers.get("Location")).toBe("/bulk");
  });

  it("sets an HttpOnly session cookie on verify", async () => {
    const token = await issueLoginToken(db, "ada@example.org", "Ada");
    const res = await get(`/auth/verify?token=${token}`);
    const cookie = res.headers.get("Set-Cookie") ?? "";
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=Lax");
  });

  it("shows the expired page for a used or unknown token", async () => {
    const token = await issueLoginToken(db, "ada@example.org", "Ada");
    await get(`/auth/verify?token=${token}`);
    const res = await get(`/auth/verify?token=${token}`);
    expect(res.status).toBe(400);
    expect(await res.text()).toContain("no longer works");
  });
});

describe("the roster is scoped to its account", () => {
  it("shows one account nothing of another's", async () => {
    const ada = await signIn("ada@example.org", "Ada");
    const eve = await signIn("eve@example.org", "Eve");

    await post("/roster/add", { ein: "27-1067272", label: "Ada's client" }, ada);

    expect(await (await get("/roster", ada)).text()).toContain("CODE FOR AMERICA");
    const eveSees = await (await get("/roster", eve)).text();
    expect(eveSees).not.toContain("CODE FOR AMERICA");
    expect(eveSees).not.toContain("Ada&#39;s client");
    expect(eveSees).toContain("Nothing saved yet");
  });

  it("will not let one account delete another's entry", async () => {
    const ada = await signIn("ada@example.org", "Ada");
    const eve = await signIn("eve@example.org", "Eve");
    await post("/roster/add", { ein: "27-1067272" }, ada);

    await post("/roster/remove", { ein: "271067272" }, eve);

    expect(db.raw("SELECT * FROM roster_entry")).toHaveLength(1);
    expect(await (await get("/roster", ada)).text()).toContain("CODE FOR AMERICA");
  });

  it("exports only the signed-in account's rows", async () => {
    const ada = await signIn("ada@example.org", "Ada");
    const eve = await signIn("eve@example.org", "Eve");
    await post("/roster/add", { ein: "27-1067272" }, ada);

    const mine = await (await get("/roster/export.csv", ada)).text();
    expect(mine).toContain("CODE FOR AMERICA LABS INC");

    const theirs = await (await get("/roster/export.csv", eve)).text();
    expect(theirs).not.toContain("CODE FOR AMERICA");
    expect(theirs.trim().split("\r\n")).toHaveLength(1); // header only
  });

  it("adds an EIN once, not twice", async () => {
    const ada = await signIn();
    await post("/roster/add", { ein: "27-1067272" }, ada);
    await post("/roster/add", { ein: "271067272" }, ada);
    expect(db.raw("SELECT * FROM roster_entry")).toHaveLength(1);
  });

  it("refuses a malformed EIN with a message rather than a row", async () => {
    const ada = await signIn();
    const res = await post("/roster/add", { ein: "abc" }, ada);
    expect(res.headers.get("Location")).toContain("notice=");
    expect(db.raw("SELECT * FROM roster_entry")).toHaveLength(0);
  });

  it("renders an entry whose organization is not in the index", async () => {
    const ada = await signIn();
    // Legitimate: saved before the org appeared, or dropped by a later ingest. The LEFT
    // JOIN yields null columns and the page must still render.
    await post("/roster/add", { ein: "13-1644147" }, ada);
    const res = await get("/roster", ada);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("13-1644147");
  });
});

describe("CSV export", () => {
  it("is a downloadable, Excel-safe CSV", async () => {
    const ada = await signIn();
    await post("/roster/add", { ein: "27-1067272" }, ada);
    const res = await get("/roster/export.csv", ada);
    expect(res.headers.get("Content-Type")).toContain("text/csv");
    expect(res.headers.get("Content-Disposition")).toContain("attachment");
    // Read as bytes, not through text(): the Fetch decode algorithm strips a leading BOM,
    // so res.text() cannot see the very thing this asserts.
    const bytes = new Uint8Array(await res.arrayBuffer());
    expect([bytes[0], bytes[1], bytes[2]]).toEqual([0xef, 0xbb, 0xbf]);
    const body = new TextDecoder().decode(bytes.slice(3));
    expect(body.split("\r\n")[0]).toBe("ein,name,city,state,label,readiness,finding,added");
  });

  it("quotes a name containing a comma", async () => {
    const ada = await signIn();
    await db
      .prepare("UPDATE organization SET name = ? WHERE ein = ?")
      .bind('SOME ORG, INC. "THE ORG"', "271067272")
      .run();
    await post("/roster/add", { ein: "27-1067272" }, ada);
    const body = await (await get("/roster/export.csv", ada)).text();
    expect(body).toContain('"SOME ORG, INC. ""THE ORG"""');
  });
});

describe("bulk check", () => {
  it("checks a pasted list in one pass", async () => {
    const ada = await signIn();
    const res = await post("/bulk", { eins: "27-1067272\n13-1644147" }, ada);
    const html = await res.text();
    expect(html).toContain("CODE FOR AMERICA LABS INC");
    expect(html).toContain("13-1644147");
  });

  it("reports what it could not read rather than dropping it", async () => {
    const ada = await signIn();
    const html = await (await post("/bulk", { eins: "27-1067272, banana" }, ada)).text();
    expect(html).toContain("banana");
    expect(html).toContain("Skipped 1 entry that is not a nine-digit EIN");
  });
});

describe("parseEinList", () => {
  it("accepts newlines, commas, semicolons and tabs", () => {
    const { eins } = parseEinList("27-1067272\n131644147, 530196605;  27-1067272");
    expect(eins).toEqual(["271067272", "131644147", "530196605"]); // deduplicated
  });

  it("separates what it could not parse", () => {
    const { eins, unparsed } = parseEinList("27-1067272\nbanana\n123");
    expect(eins).toEqual(["271067272"]);
    expect(unparsed).toEqual(["banana", "123"]);
  });

  it("caps the list and says how many were left out", () => {
    const many = Array.from({ length: 250 }, (_, i) => `27${String(i).padStart(7, "0")}`);
    const { eins, extra } = parseEinList(many.join("\n"));
    expect(eins).toHaveLength(200);
    expect(extra).toBe(50);
  });

  it("is empty for empty input", () => {
    expect(parseEinList("   \n  ").eins).toEqual([]);
  });
});

describe("account deletion", () => {
  it("requires the confirmation word", async () => {
    const ada = await signIn();
    const res = await post("/account/delete", { confirm: "yes" }, ada);
    expect(res.status).toBe(400);
    expect(db.raw("SELECT * FROM account")).toHaveLength(1);
  });

  it("deletes on confirmation and clears the cookie", async () => {
    const ada = await signIn();
    await post("/roster/add", { ein: "27-1067272" }, ada);
    const res = await post("/account/delete", { confirm: "DELETE" }, ada);
    expect(res.headers.get("Set-Cookie")).toContain("Max-Age=0");
    expect(db.raw("SELECT * FROM account")).toHaveLength(0);
    expect(db.raw("SELECT * FROM roster_entry")).toHaveLength(0);
    expect((await get("/roster", ada)).status).toBe(302);
  });
});

describe("sign out", () => {
  it("ends the session and clears the cookie", async () => {
    const ada = await signIn();
    const res = await post("/logout", {}, ada);
    expect(res.headers.get("Set-Cookie")).toContain("Max-Age=0");
    expect((await get("/roster", ada)).status).toBe(302);
  });
});
