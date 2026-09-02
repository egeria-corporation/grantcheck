/**
 * Sending the magic link.
 *
 * Behind an interface with two implementations, because the provider is a detail and the
 * flow should not be blocked on choosing one:
 *
 * - **Console** — logs the link. Used in development and whenever no provider is
 *   configured, so `wrangler dev` works with nothing set up.
 * - **Resend** — one API key, no SDK, a single fetch.
 *
 * A send failure never loses the account. The account row and the login token are already
 * written by the time this runs, so a provider outage means "we could not send the email",
 * not "your sign-up vanished".
 */

export type Mailer = {
  send(message: { to: string; subject: string; text: string }): Promise<boolean>;
};

/** No provider configured. Logs the link so development works with nothing set up. */
export const consoleMailer: Mailer = {
  async send({ to, subject, text }) {
    console.log(
      `\n--- email (no provider configured) ---\nto: ${to}\nsubject: ${subject}\n\n${text}\n---\n`,
    );
    return true;
  },
};

export function resendMailer(apiKey: string, from: string): Mailer {
  return {
    async send({ to, subject, text }) {
      try {
        const response = await fetch("https://api.resend.com/emails", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${apiKey}`,
            "Content-Type": "application/json",
            Accept: "application/json",
            // Cloudflare fronts api.resend.com and will answer a request it dislikes with
            // its own 403 ("error code: 1010") that never reaches Resend — and which looks
            // exactly like a revoked key. This project has now been bitten by that twice, on
            // the index CDN and while verifying this very key. A descriptive agent is
            // cheap insurance, not decoration.
            "User-Agent": "grantcheck (+https://github.com/egeria-corporation/grantcheck)",
          },
          body: JSON.stringify({ from, to: [to], subject, text }),
        });

        if (!response.ok) {
          // With Worker invocation logs switched off for privacy, this line is the only
          // signal that mail has stopped working. It has to be diagnosable.
          //
          // Resend answers errors as {statusCode, name, message}; `name` is a category
          // ("validation_error", "missing_required_field"), never a recipient. That is what
          // gets logged. The raw body never is: a provider error can echo the address back,
          // and an address is precisely what must not end up in a log.
          console.error(`mail send failed: HTTP ${response.status} ${await errorKind(response)}`);
          return false;
        }
        return true;
      } catch (error) {
        console.error("mail send threw", error instanceof Error ? error.message : "unknown");
        return false;
      }
    },
  };
}

/** A safe, address-free label for why a send failed. */
async function errorKind(response: Response): Promise<string> {
  // A Cloudflare interception is HTML, not JSON, and means the request never reached the
  // provider. Distinguishing it matters: the fix is a header, not a new API key.
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.includes("json")) {
    return response.status === 403
      ? "(blocked upstream, not by Resend — check the request headers)"
      : "(non-JSON response)";
  }
  try {
    const body = (await response.json()) as { name?: string };
    return body.name ? `(${body.name})` : "(no error name)";
  } catch {
    return "(unparseable JSON)";
  }
}

export function mailerFor(env: { RESEND_API_KEY?: string; MAIL_FROM?: string }): Mailer {
  if (env.RESEND_API_KEY && env.MAIL_FROM) {
    return resendMailer(env.RESEND_API_KEY, env.MAIL_FROM);
  }
  return consoleMailer;
}

/**
 * The sign-in email. Plain text, no tracking pixel, no HTML.
 *
 * It states the expiry, that the link is single-use, and what to do if the recipient did
 * not ask for it — because somebody typing the wrong address is the ordinary case, and the
 * person who receives it should know they need do nothing.
 */
export function signInEmail(link: string, minutes: number): { subject: string; text: string } {
  return {
    subject: "Your grantcheck sign-in link",
    text: `Sign in to grantcheck:

${link}

The link works once and expires in ${minutes} minutes.

If you did not ask to sign in, you can ignore this — no account was created for
you by somebody else typing your address, and nobody can sign in without this link.

grantcheck is free and open source: https://github.com/egeria-corporation/grantcheck
`,
  };
}
