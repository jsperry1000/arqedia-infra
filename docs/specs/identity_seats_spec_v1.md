# Identity & Seats — Spec v1.0

**DD SaaS product · greenfield · design spec**
Component 9 of 9. Consumed by every other component.

---

## 0. Status of every claim here

Every rule below is a decision made for this product. **§3 and §5 are the important sections** — §3 covers where a person's identity lives in a multi-region product,
where the obvious answer is the wrong one; §5 covers account recovery, which is
an unavoidable attack surface rather than a support detail. Items awaiting a decision are collected
in §8.

---

## 1. Scope

**Owns:** tenant accounts, seats, roles, authentication, session handling, and
the relationship between a seat and a viewer account.

**Does not own:** billing (component 1), config permissions beyond the role
itself (component 2), share grants (component 5).

---

## 2. The three kinds of account

| Kind | Billed | Can | Cannot |
|---|---|---|---|
| **Admin seat** | Yes | Everything, including publish, plan changes, top-up, deletion | — |
| **Member seat** | Yes | Upload, file, generate, share, revoke, read config | Publish, pay, delete, change plan |
| **Viewer** | No | Read and download memos granted to them | Everything else |

**Seats are fixed by the plan** — 2 on Base, 5 on Small Business. Adding a seat
is a plan change, not a proration. There is no per-seat purchase.

**At least one admin at all times.** The last admin cannot be demoted or
removed. Seat count is enforced at invitation, not at login.

**A viewer is not a seat** and never counts toward the minimum or the billing.

---

## 3. Identity in a multi-region product

**The obvious design is one global user directory. It is the wrong one.**

A user directory holds names and email addresses, which are personal data. An EU
tenant who chose Frankfurt precisely so their data stays in Frankfurt has not
agreed to their staff's identities sitting in Ohio. Putting the directory in one
region quietly undoes the residency promise the rest of the architecture works
to keep.

**Settled — regional identity pools, with a global routing directory that holds
no addresses.**

```
Global directory     email_hash (one-way)  →  region
Regional pool        the actual identity: email, name, credentials, MFA
```

**Login flow:** the person enters their email; the address is hashed in the
browser or at the edge; the global directory returns a region; the browser is
redirected to that region's login. The global plane never stores an address it
could disclose.

**Consequence to accept honestly:** hashing means the global directory cannot
enumerate users, cannot send email, and cannot do fuzzy matching on addresses.
That is the point. Anything needing those capabilities belongs in the regional
pool.

**Cross-region membership.** One person may hold a seat in a US tenant and be a
viewer of an EU tenant. These are separate identities in separate pools that
happen to share an address. They are not linked, and linking them would
reintroduce exactly the global personal-data store this design avoids.

---

## 4. Authentication

- **Email and password, plus multi-factor.** **MFA is required on every seat,
  admin and member alike.** A product that holds KYC files for a living should
  not have a weaker tier of account, and a member seat can still read every
  memo and every source document the tenant holds.
- **Viewers are a separate case and are treated separately.** A verified-only
  viewer never sets a password — access is by a link sent to their address, so
  control of the mailbox is itself the factor. That is a defensible single
  factor for 30-day read access to one artifact. **A registered viewer sets a
  password and therefore takes MFA**, because they are holding six-month access
  to third-party identity material and the extension is what they received in
  exchange. This is friction on the conversion funnel and it is the right place
  to accept it.
- **Sessions are token-based** with no server-side session store, consistent
  with holding no persistent connections (*Isolation* §3).
- **Single sign-on is an Enterprise feature**, carried on the plan row like
  every other entitlement. Not built for Base or Small Business. Where SSO is in
  use, MFA is enforced by the customer's own identity provider rather than by
  us.

---

## 5. Seat lifecycle

**Invitation.** An admin invites an address to a role. The invitation is
regional — it creates an identity in the tenant's own pool. Unaccepted
invitations expire.

**Deactivation.** A seat is deactivated, never deleted. Everything that seat
did — filings, memos, shares sent, config published — stays attributed. An
audit trail with holes in it is not an audit trail.

**Reassignment.** A freed seat can be invited to someone new. The prior holder's
history remains under their own identity.

**Admin recovery when the only admin is gone.** On Base, one of two people
carries every irreversible action. If they leave, are dismissed, or stop
responding, the tenant cannot publish, pay, or close the account, and their own
diligence files sit there unadministrable.

There are only three responses to that call, and two are unacceptable. Refusing
means the customer loses their work permanently. Acting on an emailed assertion
that someone is the owner means anyone able to spoof an email can seize a
company's KYC files — which is how account takeovers happen.

**The third is a written procedure agreed in advance.** It must establish that
the caller controls the *company*, not that they control an email address:

- Evidence the legal entity exists and the caller is entitled to act for it —
  incorporation and authority documents, the same class of evidence this product
  exists to review.
- Corroboration against what the account already holds: the billing instrument,
  the registered address, the domain of existing seats.
- A cooling-off notice to the existing admin's address before any change takes
  effect, so a genuine but absent admin can object.
- A full audit record of the request, the evidence accepted, and who at our end
  approved it.

**Drafted as a separate operational document:** `admin_recovery_policy_draft.md`.
It is a support procedure, not a design artifact, and must be finalised before
the first tenant exists. It will be needed under
pressure, by someone distressed, and whoever answers will improvise if there is
nothing to follow. Improvised account recovery is where the breach comes from.

Signup should also actively push for a second admin, since the cheapest fix is
the customer never needing this.

---

## 6. The viewer relationship

Viewer accounts are defined in *Share & Viewer Accounts* §3. Two joins matter
here:

- **A viewer may convert to a tenant of their own.** Their viewer grants survive
  the conversion (*Share* §3). The new tenant is created in the viewer's own
  chosen region, not necessarily the region of whoever shared with them.
- **A viewer may separately hold a seat elsewhere.** Same address, separate
  identities, no linkage (§3).

---

## 7. Audit

Every seat action is attributable: who filed, who generated, who published, who
shared, who revoked, who paid, who changed the plan.

This is not a nice-to-have in this domain. The tenant's own regulator or client
may ask who saw a due diligence file and who signed off on it, and the answer
has to come out of the system rather than out of someone's memory.

---

## 8. Open

1. **Identity provider** — no vendor named. Deferred behind an interface like
   payments and email. Whatever is chosen must support per-region pools, so a
   single-region-only service disqualifies itself.
2. **Admin recovery procedure** (§5) — the criteria are specified; the
   operational document, evidence standard and approval authority are not.
   Must be written before the first tenant exists.
3. **SSO protocol for Enterprise** (§4) — SAML, OIDC, or both. Phase 2.
4. **Session lifetime and re-authentication frequency** — build-phase, but note
   that the viewer surface must not re-authenticate aggressively (*Share* §4),
   because friction there costs conversions.

None of these block the design.
