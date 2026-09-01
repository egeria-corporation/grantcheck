# What this replaces

> **Note on scope.** This file describes the capability gap `grantcheck` fills. It deliberately
> names no vendor and quotes no price. Comparative analysis of commercial products is maintained
> outside this repository for now. Nothing in the tool, its help text, its command output, or any
> hosted page may name or price a commercial product — see `docs/program/CONVENTIONS.md`.

## The shape of the gap

`grantcheck` does not replace a product. It replaces a **feature bundled inside several different
subscription products**, none of which sells it separately, and none of which a small organization
buys for this alone.

The feature has a name in the sector — "grant readiness" or "pre-award compliance check" — and it is
one of the standard first-engagement deliverables a grant consultant produces.

## Done by hand, it is about ninety minutes

For one organization:

1. Pull the IRS Tax Exempt Organization Search record and read the exemption status.
2. Check Publication 78 for deductibility, and know to skip that step for a group-exemption
   subordinate.
3. Search the Automatic Revocation List, and know that presence on it does not mean currently
   revoked.
4. Find the most recent Form 990 on file, and know that a 990-N filer will not appear where the
   full filers do.
5. Log into SAM.gov, find the entity without being able to search by EIN, and read the registration
   status and expiration date.
6. Confirm a Unique Entity ID exists.
7. Ask the finance director what the federal expenditure line looked like last year, and compare it
   against the single audit threshold and the date that threshold changed.

Nothing in that list is difficult. All of it is public. It is tedious, it is easy to get subtly
wrong in the four specific ways documented in `data-sources.md`, and it is exactly the kind of work
that does not get done at all when it is unbilled.

**A consultant with a roster of twelve clients has this problem twelve times, quarterly.**

## Why the gap exists

The data lives in two agencies that do not share a join key. The IRS identifies organizations by
Employer Identification Number; SAM.gov's public tier cannot be searched by one, because taxpayer
identification number is sensitive-tier. Joining them requires inferred name-and-state matching with
an honest confidence score, which is unglamorous work that no one has published openly.

That join, and the packaging around it, is the whole contribution. The data was always free.

## What `grantcheck` does not claim

- It is not a determination of eligibility. It reports observable facts and what they usually mean.
- It does not cover every disqualification. Program-specific eligibility rules are out of scope and
  are on the non-goals list.
- It does not replace reading the notice of funding opportunity.
