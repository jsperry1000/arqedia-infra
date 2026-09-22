# ARQEDIA — Backlog Item

## ONB-01 · There is no way to create an account

| | |
|---|---|
| Status | Front end mocked and routed. Nothing server-side exists |
| Priority | Blocking. Both marketing buttons lead to a sign-in card with no way past it |
| Type | Cognito, API, edge, front end |
| Raised | 14 September 2026 |
| Depends on | Nothing. Everything it needs is additive |

---

### Where it stands

`arqedia.com` carries two **Start a trial** buttons. Both point at
`app.arqedia.com`. The application opens a sign-in card. A person with no
account has nowhere to go from there, and no route in the product creates one.

The user pool is admin-create-only. The test accounts in the 9 September
handoff were created by hand, which is why the first sign-in presented a
new-password challenge.

`ui/src/SignUp.tsx` exists, is routed at `/signup`, and is reachable from the
sign-in card. It walks all six steps and creates nothing. It is marked as a
mock on every screen.

---

### The flow, settled

From `frontend_onboarding_spec_v1.md` §8, unchanged. Each step earns its place;
none is there for completeness.

| | Step | Why it exists |
|---|---|---|
| 1 | Email and password | One trial per email domain. The domain is shown back as it is typed |
| 2 | Verify the address | Nothing is created until the address answers. This is also what stops a throwaway address taking a trial |
| 3 | Organisation and jurisdiction | The declared jurisdiction binds, not the address the request came from. It decides the terms |
| 4 | Region | Suggested from location, confirmed by the person, then immutable |
| 5 | Starter pack | First run is a fork, never an empty editor |
| 6 | Second administrator | Optional, prompted. The cheapest account recovery is the one nobody has to invoke |

**No card at any step.** Thirty days, full use, $5.00 of metered credit. A card
wall at the front contradicts the positioning and cuts trial starts.

> **Corrected 22 September 2026.** The trial is **14 days**, not 30. It was
> changed by the Paddle decision record of 16 September
> (`paddle_subscription_decisions_2026-09-16.md`, "Trial is 14 days in all
> cases (was 30, Wallet §2)") and `signup.TRIAL_DAYS` has said 14 since. The
> line above is left standing because it is what this document said; the
> published figure now lives in `config/plans.json` as `trial_days`, which
> the marketing site and the application both render at build.

**Region is the only irreversible choice**, and the screen says so plainly.
Moving a tenant afterwards means re-filing every document, and every memorandum
already written would name a revision whose documents are no longer behind it.

---

### Three things that must exist before it is real

**1 · Self-registration on the user pool.** Enabled, with the email verified by
code. Terraform change in `auth.tf`; the pool is admin-create-only today.

**2 · A create-tenant call.** There is no endpoint. It must, in one
transaction: mint the tenant row, set `custom:tenant_id` on the Cognito user,
record the declared jurisdiction, pin the region, fork the chosen pack as
revision 1, and open the trial bucket — $5.00, expiring at `trial_ends_at`.

Partial completion is the failure that matters. A Cognito user with no tenant
can sign in and reach an application that cannot answer any request about them.

**3 · The abuse controls**, §Abuse below. They belong at the edge and in the
handler. The front end can be bypassed by anyone calling the API directly, so
nothing enforced there counts.

---

### Abuse, in order of how much each actually does

**The $5.00 metered ceiling on the trial.** Somebody who cycles ten colleagues
through gets $50 of inference. That is the whole exposure and it is bounded
however every other control fails. Already specified in the wallet.

**One trial per email domain.** `@vmac.com` gets one tenant. A second person
from that domain is offered a seat on the existing one rather than a new trial
— which is also the better product, because they probably meant to join their
colleagues.

**Disposable-domain blocking.** A maintained list. `@mailinator.com` and its
thousand cousins cannot take a trial at all.

**Rate limiting per address and per domain, at the edge.** Stops scripted
signups. It does not stop a determined person and is not meant to.

---

### IP addresses — a signal, never a gate

**Recorded on the signup row. Never used to block.**

Blocking on IP fails in both directions. A VPN or a home connection defeats it
in seconds, while a shared office NAT or a university network blocks strangers
who have nothing to do with each other. Ten colleagues at one firm share a
handful of office addresses, and the domain rule has already stopped the first
of them.

What it is good for is review. Nine trials from one connection is evidence a
human should see. So the address is recorded, surfaced when the abuse flags
fire, and does nothing on its own.

**Two things this obliges, both cheap now and expensive later:**

- An IP address is personal data in the EU and the UK. Recording it needs a
  lawful basis stated in the privacy policy and a retention limit. Ninety days
  is the usual answer.
- The column and its retention job are written when signup is built, not
  retrofitted across a live signup table.

---

### The exception path

Domain blocking will catch genuine cases. A holding company with three trading
names on one domain. A consultant who wants a tenant per client.

The rule is right; it needs a lift. Support marks a named domain as permitted
to hold more than one tenant. That is a column and an admin action, not a
policy change, and it should exist from the first day the rule does — or the
first real customer it catches becomes a support incident with no resolution.

---

### What the front end already establishes

The order, the wording and the shape are done and can be judged now. The screen
carries the domain back to the person as they type it, states the region
warning before the choice rather than after it, gives the honest reason for a
second administrator, and ends on a summary of exactly what is about to begin.

`SignUp.tsx` carries the three server-side prerequisites in its own header, so
whoever builds them does not have to find this document first. This document is
where they are argued.

---

### Open

1. **Vetting position.** `frontend_onboarding_spec_v1.md` §11 stands unanswered:
   we would be selling a sanctions and diligence tool self-serve at $25 with no
   vetting of the buyer. Three positions are available — accept it and say so,
   require a business email and a verified payment method, or vet above a usage
   threshold. Needs a decision and probably counsel.
2. **IP retention period**, and the privacy-policy wording that accompanies it.
3. **Disposable-domain list** — maintained by us, or a third-party service.
   Web-search the options rather than assuming; a stale list is worse than none
   because it reads as working.
4. **What happens to the second administrator's invitation** if the trial
   lapses before they accept.

---

### Acceptance

A person arriving at `arqedia.com`, clicking **Start a trial**, and following
the six steps ends signed in to their own tenant, on a forked pack, with a
trial bucket open and no card held — and a second person from the same domain
is offered a seat rather than a second trial.
