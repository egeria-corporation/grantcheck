# SAM.gov registration

**What it checks.** Whether the organization has an active entity registration in the System
for Award Management at <https://sam.gov>.

**Why it can stop an application.** An active SAM.gov registration is a hard gate on every
federal grant and contract. Registrations lapse annually and renewal is not automatic, which
makes this the single most common avoidable disqualification in the federal system.

**Why the answer is sometimes "could not identify the registration".** The IRS identifies
organizations by Employer Identification Number, and SAM.gov's public tier cannot be
searched by one — taxpayer identification number is sensitive-tier data. The link has to be
inferred from legal name and state, and where that inference is not confident, this check
says so rather than guessing. **That is not a finding about the organization.** Re-run with
`--uei` to pin the registration and get a definite answer.

**Registration purpose matters.** An entity registered for federal contracts only is active
and still cannot receive a grant. The check reports that separately.

**What to do.** Register or renew at <https://sam.gov>. It is free. Registering for the
first time takes considerably longer than renewing — start with the Unique Entity ID
request.
