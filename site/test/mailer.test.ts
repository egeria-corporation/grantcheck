/**
 * The mail path.
 *
 * Worth testing directly because two things here are easy to get wrong and silent when they
 * are: the request must carry a User-Agent (Cloudflare fronts Resend and blocks requests it
 * dislikes with a 403 that never reaches the provider), and a failure must never write a
 * recipient address into a log.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { REPLY_TO, consoleMailer, mailerFor, resendMailer, signInEmail } from "../src/mailer";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(response: Response) {
  const spy = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const MESSAGE = { to: "ada@example.org", subject: "hello", text: "body" };

describe("choosing a mailer", () => {
  it("uses Resend only when both the key and the from address are set", () => {
    expect(mailerFor({ RESEND_API_KEY: "k", MAIL_FROM: "a@b.com" })).not.toBe(consoleMailer);
    // A half-configured environment must fall back rather than send with a broken From.
    expect(mailerFor({ RESEND_API_KEY: "k" })).toBe(consoleMailer);
    expect(mailerFor({ MAIL_FROM: "a@b.com" })).toBe(consoleMailer);
    expect(mailerFor({})).toBe(consoleMailer);
  });
});

describe("the Resend request", () => {
  it("carries a descriptive User-Agent", async () => {
    const fetchSpy = mockFetch(jsonResponse(200, { id: "1" }));
    await resendMailer("key", "update@oss.opengrants.io").send(MESSAGE);

    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    // Load-bearing, not decoration: without it Cloudflare answers 403 and the message is
    // never delivered, while the log looks exactly like a revoked key.
    expect(headers["User-Agent"]).toContain("grantcheck");
    expect(headers.Authorization).toBe("Bearer key");
  });

  it("sets a Reply-To that can actually receive mail", async () => {
    const fetchSpy = mockFetch(jsonResponse(200, { id: "1" }));
    await resendMailer("key", "update@oss.opengrants.io").send(MESSAGE);

    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.reply_to).toBe(REPLY_TO);
    // The sending subdomain has no MX record, so a reply to From bounces into nothing.
    // Reply-To must therefore be on a different domain than the one we send from.
    expect(REPLY_TO.split("@")[1]).not.toBe(body.from.split("@")[1]);
  });

  it("sends the message it was given, to one recipient", async () => {
    const fetchSpy = mockFetch(jsonResponse(200, { id: "1" }));
    await resendMailer("key", "update@oss.opengrants.io").send(MESSAGE);

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.resend.com/emails");
    const body = JSON.parse(String(init.body));
    expect(body.to).toEqual(["ada@example.org"]);
    expect(body.subject).toBe("hello");
  });

  it("reports success", async () => {
    mockFetch(jsonResponse(200, { id: "1" }));
    expect(await resendMailer("key", "f@x.com").send(MESSAGE)).toBe(true);
  });
});

describe("when sending fails", () => {
  it("never writes the recipient address into the log", async () => {
    // Resend echoes the address back in some validation errors. Logging the raw body would
    // put an email address in a log, which is the one thing this must not do.
    mockFetch(
      jsonResponse(422, {
        name: "validation_error",
        message: "Invalid `to` field: ada@example.org is not valid",
      }),
    );
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(await resendMailer("key", "f@x.com").send(MESSAGE)).toBe(false);

    const logged = errorSpy.mock.calls.flat().join(" ");
    expect(logged).not.toContain("ada@example.org");
    expect(logged).toContain("validation_error"); // the category is safe and diagnosable
  });

  it("distinguishes an upstream block from a provider error", async () => {
    // Cloudflare's interception is HTML, not JSON. The fix is a header, not a new key, and
    // the log has to say so or the next person burns an afternoon rotating credentials.
    mockFetch(
      new Response("<html>error code: 1010</html>", {
        status: 403,
        headers: { "Content-Type": "text/html" },
      }),
    );
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(await resendMailer("key", "f@x.com").send(MESSAGE)).toBe(false);
    expect(errorSpy.mock.calls.flat().join(" ")).toContain("blocked upstream");
  });

  it("returns false rather than throwing when the network fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection reset")));
    vi.spyOn(console, "error").mockImplementation(() => {});

    // A provider outage must mean "we could not send", never a thrown request handler that
    // loses the account that was already written.
    expect(await resendMailer("key", "f@x.com").send(MESSAGE)).toBe(false);
  });
});

describe("the sign-in email", () => {
  it("carries the link, the expiry, and that it works once", () => {
    const mail = signInEmail("https://check.opengrants.io/auth/verify?token=abc", 15);
    expect(mail.text).toContain("https://check.opengrants.io/auth/verify?token=abc");
    expect(mail.text).toContain("15 minutes");
    expect(mail.text).toContain("works once");
  });

  it("tells an unintended recipient that nothing was created for them", () => {
    // True because issueLoginToken writes no account row. If that ever changes, this
    // sentence becomes a lie and this test should fail.
    expect(signInEmail("https://x", 15).text).toContain("no account was created");
  });

  it("is plain text with no tracking", () => {
    const mail = signInEmail("https://x", 15);
    expect(mail.text).not.toContain("<img");
    expect(mail.text).not.toContain("<html");
  });
});
