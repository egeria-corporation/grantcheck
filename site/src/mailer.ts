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
          },
          body: JSON.stringify({ from, to: [to], subject, text }),
        });
        if (!response.ok) {
          // Deliberately not logging the body: a provider error can echo the address back,
          // and this log is not the place for it.
          console.error(`mail send failed: ${response.status}`);
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
