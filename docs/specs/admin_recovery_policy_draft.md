# Administrator Recovery Policy

**Operational document · DRAFT for review**
Not a design spec. Referenced by *Identity & Seats v1.0* §5.

| | |
|---|---|
| Status | Draft — requires counsel review before use |
| Owner | [unassigned] |
| Approval authority | [unassigned — must be a defined role, not a shift] |
| Notice period | [10] business days — placeholder |
| Must exist by | Before the first tenant account is created |

---

## 1. Purpose

An account may be left without a reachable administrator — through departure,
dismissal, illness, or simple non-response. On the entry plan, one of two people
holds every irreversible action, so this is a certainty at volume rather than an
edge case.

There are only three responses to such a request. Refusing permanently strands
the customer's own diligence files. Acting on an emailed assertion of ownership
allows anyone able to spoof an address to seize a company's KYC material. This
policy is the third response, and it exists so that nobody improvises the second
one under pressure.

---

## 2. Policy

Where an account has no reachable administrator, a person acting for the account
holder may request that administrator rights be assigned to an existing user of
that account. We will act on such a request only where the requester
establishes, to our satisfaction, that they are authorised to act for the legal
entity that holds the account. Evidence of control of an email address,
including the address of the departed administrator, is not sufficient and will
not be accepted on its own. The requester must provide current evidence of the
entity's existence and of their own authority to act for it — typically
incorporation or registration documents together with a board resolution, an
officer's certificate, or equivalent evidence of appointment. We will corroborate
that evidence against information already held on the account, including the
billing instrument, the registered address, and the email domains of existing
users. We may decline any request without giving reasons, and we may require
further evidence at any point.

Where a request is accepted, we will give notice to the existing administrator
at their recorded address and will not make any change for [10] business days
from that notice. If the existing administrator objects within that period, no
change will be made and the matter will be referred back to the parties.
Administrator rights, once assigned, permit publishing configuration, changing
the plan, making payment, and deleting the account and all data within it; we
therefore assign them only to a person who already holds a seat on the account,
and never to a new address introduced during the request. We do not restore
deleted accounts or deleted data under this policy, and we do not disclose the
contents of an account to a requester before rights are assigned. We keep a
record of every request, the evidence accepted or refused, the notice given, and
the person within our organisation who approved the outcome.

---

## 3. Handling notes for staff

- **Never assign rights to an address that is not already a seat.** This is the
  single control that prevents the policy becoming an account-takeover route.
- **Never describe the contents of the account** — counterparty names, document
  counts, memo subjects — to a requester before rights are assigned. Confirming
  what an account contains is itself a disclosure.
- **Do not shorten the notice period for urgency.** Urgency is what a genuine
  attacker will claim. If the customer needs faster access, the answer is a
  second administrator, not a faster exception.
- **Escalate rather than judge.** Front-line staff collect evidence; the named
  approval authority decides.

---

## 4. Prevention

The cheapest version of this policy is one that is never invoked.

- Signup actively prompts for a second administrator.
- The account settings surface warns whenever a tenant has only one.
- Warning text states plainly what is lost if that person becomes unreachable.

---

## 5. Open before use

1. **Notice period** — [10] business days is a placeholder.
2. **Approval authority** — must be a named role.
3. **Counsel review** — particularly the discretion to decline without reasons,
   which is standard but sits differently across jurisdictions.
4. **Evidence standard by jurisdiction** — a board resolution means different
   things in Delaware, Germany and a UAE free zone. The product will have
   tenants in all three.
