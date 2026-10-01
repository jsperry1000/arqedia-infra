# Share & Viewer Accounts — Spec v1.0

**DD SaaS product · greenfield · design spec**
Component 5 of 9. Gated by *Wallet & Entitlement Gate v1.0*. Consumes memos
produced by *Pipeline v1.0*.

> **Amended 21 September 2026 — the verified term is 2 weeks (12.1).** A
> recipient who has only clicked the link keeps access for **2 weeks from
> send**, not 30 days. Six places carried the old figure and all six are
> changed: §3 twice, §6 twice, §7's funnel and §9's settled list.
>
> **The registered term is unchanged at 6 months**, and so is everything the
> extension rests on — it is the incentive to register, and shortening the
> verified term widens the gap rather than narrowing it. §6's ceiling rule is
> unchanged: an expiry a tenant sets deliberately still wins, and extension
> still applies only where the tenant left the default.
>
> Nothing else in this document has been altered.

> **Amended 1 October 2026 — allowance, overage, rate limit, storage
> (share-recipient).** Changed in place: §6's allowance table, its rate-limit
> row, and §9 item 1. Added: §6's trial, overage and reset paragraphs, and the
> note at the end of §8. What §6's table said before, so it is not lost:
>
> | | Base | Small Business | Enterprise |
> |---|---|---|---|
> | Shares per month | 5 | unlimited | negotiated |
> | Rate limit | applies | applies | applies |
>
> **Business is not unlimited.** It includes 25 a month and is metered past
> them. **A trial is Base's shape**, not a tier of its own: ten shares once,
> for the whole fourteen-day trial. The registered term is computed per grant
> from its own send (§6). Nothing else in this document has been altered.

---

## 0. Status of every claim here

Every rule below is a decision made for this product. Items awaiting a decision
from you are collected in §9. **§5 and §7 are the important sections** — §5
settles watermarked download and the real limits of revocation, and §7
separates what we may do with a viewer's email from what the tenant may do.
That second distinction is a legal one, not a product preference.

---

## 1. Scope

**Owns:** share grants, viewer accounts, the viewer experience, revocation,
audit, and the conversion path off a shared memo.

**Does not own:** memo production (pipeline), plan allowances (wallet), tenant
identity and seats (component 9).

**Why it matters commercially:** a viewer is a qualified lead who has just read
a finished memo your system produced. They see output quality before they see a
price. This is the cheapest acquisition channel in the product, and the reason
share allowance sits in the plan grid rather than being unlimited everywhere.

---

## 2. What a share is

A grant of read access to **exactly one rendered memo**, held by a viewer
account.

- **One memo, not a folder, not an account, not a document set.** Scope is a
  single artifact and cannot be widened.
- **Memos are immutable** (*Pipeline* §7), so a shared memo never changes under
  the viewer. Regeneration produces a new memo, which is a separate share
  decision.
- **The viewer sees no source documents**, no extracted values, no config, and
  no other memo. There is no navigation out of the artifact into the tenant's
  workspace.

---

## 3. The viewer account

A real account with a permanently non-consuming entitlement. Not a seat, never
billed, and it does not count toward the tenant's seat minimum.

**Creation.** The tenant enters an email and sends. The recipient receives a
link, verifies by clicking it, and a viewer account is created against that
address. First verification captures `first_opened_at`.

**Two viewer states.** *Verified* — reached by clicking the link, 2-week access,
no relationship with us. *Registered* — the viewer accepts our terms and sets a
password and multi-factor, access extends to 6 months, and §7 applies
(*Identity* §4). The prompt to register
lives inside the memo view and leads with the extension, which is the honest
pitch: register and keep access for six months instead of two weeks.

**Why an account rather than an unauthenticated link.** A bare link forwards
freely and audits nothing — the tenant cannot answer who read a due diligence
memo, which is the question that matters in this domain. Requiring email
verification means every read is attributable.

**Capabilities:** read memos granted to them in the app and download watermarked
copies of them (§5), and nothing else. A viewer account can hold grants from
multiple tenants without those tenants being visible to each other.

**Upgrade path.** A viewer may convert to a tenant of their own at any time.
Their viewer grants survive the conversion.

---

## 4. Viewer delivery — served from cache, not the cluster

**The viewer surface must not touch the paused Aurora cluster.** Resume from
0 ACU takes roughly 15 seconds (*Isolation* §3). For an admin uploading
documents that is unremarkable. For a viewer opening a shared memo it is the
first impression this product makes on a qualified lead, on the one surface that
exists to acquire them.

**What is cached at share time**, written when the grant is created, not on
first access:

- The rendered memo artifact, watermarked per viewer (§5).
- A grant record sufficient to authorise: grant ID, viewer ID, expiry, revoked
  flag.

**Serving path:** CDN and object storage plus a lightweight authorisation check
against the cached grant record. No Aurora read on the hot path.

**Revocation must invalidate the cache synchronously.** A revoked grant that
keeps serving from cache is a real access-control failure, not a stale-data
annoyance. Revocation writes through: cache entry removed and CDN invalidated
before the revoke returns success to the tenant. Expiry is enforced from the
cached record's own expiry timestamp, so it needs no write at all.

**Registration extension writes through the same path** (§6), updating the
cached expiry when a viewer registers.

**Access logging is asynchronous.** Views and downloads are queued and written
to `share_access_log` off the hot path, so the audit trail costs the viewer no
latency and does not wake the cluster.

**Settled — viewers read in the app and can download a watermarked copy.** The
memo renders in the viewer experience; a download produces the same artifact in
the template's output format (PDF, DOCX, or both).

**Every rendered view and every downloaded copy is watermarked** with the
viewer's email, the tenant name, and a timestamp, burned into the artifact
rather than overlaid in a removable layer.

**Why download stays.** A due diligence memo sent to a lender or counterparty is
meant to be filed on their side. Withholding it would make the feature useless
for its actual purpose and would push tenants to generate the memo and email it
manually — which audits nothing and defeats the whole component.

**What revocation therefore does.** It ends future access to the artifact in the
app. It does not recall a copy already downloaded. **The share UI must say this
in plain language at the point of sending**, not in terms of service. A tenant
who believes revocation recalls a document has been misled by the interface, and
in this domain that misunderstanding is expensive.

The watermark is what makes an onward-distributed copy attributable. It is the
honest substitute for control we do not have, and the product should not imply
more than that.

> **Noted 28 September 2026.** This document has no `## 5.` heading: the
> sections run §4 then §6. Every citation of §5 — here in §0, §3, §4 and §9, and in
> `docs/ARQEDIA_worklist_UX02_2026-09-20.md` 12.4 and 21.8 — means the text from
> "Settled — viewers read in the app and can download a watermarked copy" to
> this note, which sits under §4's heading. No heading is added, so no
> section number already cited elsewhere moves.

---

## 6. Allowance, expiry, revocation, audit

| | Trial | Base | Small Business | Enterprise |
|---|---|---|---|---|
| Shares included | 10 for the whole trial | 10 a month | 25 a month | as contracted |
| Each share past that | $1.00 | $1.00 | $0.25 | as contracted |
| Rate limit | 20 a day | 20 a day | 20 a day | 20 a day |

**Past the allowance a share is charged, never refused.** The price is the
plan's `meter_price` row - `share_overage_base` or `share_overage_business`
(migration 036) - charged through `wallet.charge`, shown and accepted before
the send. A trial is charged at Base's price.

**A trial is Base's shape, not a tier of its own.** Ten shares, once, for the
whole trial - anchored to `tenant.trial_ends_at`, never reset during it, and
whatever plan the tenant signed up for. On conversion the tenant moves to its
plan's monthly allowance from the conversion date.

**A month is the billing period**, the same one a monthly credit bucket lives
for: it ends at `subscription.current_period_ends_at`.

**Re-sending a memorandum to the same address uses no allowance and costs
nothing**, revoked or not - it finds the same grant and reinstates it (§8). It
does count toward the daily limit, because it sends an email.

**A rate limit applies at every tier.** Free viewer accounts with no revenue
behind them are an abuse and storage surface; an allowance is a commercial
promise about normal use, not an invitation to bulk-send.

**Expiry — settled, two-stage.**

| Viewer state | Grant term |
|---|---|
| Sent, email-verified only | 2 weeks from send |
| Registered with the app | 6 months from that grant's own send |

Registration is a real signup — the viewer accepts our terms and privacy policy
and sets a password. It costs nothing, grants no product capability beyond
longer access to memos already shared with them, and is the moment a passive
recipient becomes someone with a direct relationship to us.

**The tenant retains the ceiling.** If a tenant explicitly sets an expiry at
send time, that date wins and registration cannot extend past it. Extension
applies only where the tenant left the 2-week default, which signals a default
rather than a deliberate limit. A tenant who sets a short window for a reason
keeps it.

**Extension is per grant, applied at registration and to grants received
afterwards**, across every tenant that has shared with that viewer.

> **Settled 1 October 2026 (share-recipient; UX02 12.5).** A registered
> viewer's grant runs to its own `sent_at` + 6 months, unless the tenant set
> the expiry. Registering recomputes every grant the viewer holds. There is no
> account-level registration date in the computation: a grant sent five months
> before its recipient registered gets one more month, not six.

**Revocation** is immediate and available to any seat, admin or member, at any
time — including in `capped`, since revoking is a reduction of access and a
tenant locked out for non-payment must still be able to pull a memo back.

**Audit per grant:** who sent it, to which address, when, when first opened,
every subsequent open, every download, and who revoked it. This is the record a
tenant needs when someone asks who saw the file — and, because downloads are
logged with the watermark identity, who took a copy of it.

**Account deletion revokes every outstanding grant** and destroys the memos
behind them (*Wallet* §9).

---

## 7. Marketing the viewer — the registration boundary

**Settled: registration is the line.** A viewer who has only clicked a
verification link has no relationship with us — the tenant collected that
address and we delivered a file to it. A viewer who registers has accepted our
terms and privacy policy directly, and is ours to contact.

| Viewer state | What we may do |
|---|---|
| Sent, verified only | Show the memo. Transactional email about that memo only. In-artifact prompt to register. |
| Registered | Everything above, plus marketing, subject to §7.1. |

**The conversion funnel this creates:**

```
recipient → verified viewer → registered viewer → tenant
 (2 weeks)       (6 months)        (paying)
```

The 6-month extension is the incentive to register, and registration is what
makes the contact marketable. That is a clean trade and the viewer can see
exactly what they are getting.

### 7.1 What registration does and does not settle

Registration establishes a direct relationship and a lawful basis for service
communication. It does **not** by itself constitute marketing consent
everywhere — several jurisdictions require an affirmative opt-in for marketing
regardless of account status, and pre-ticked boxes are not valid consent in
those places.

**Engineering answer, not a warning:** a marketing preference presented at
registration, with a jurisdiction-aware default — unticked where affirmative
opt-in is required, ticked-with-clear-opt-out elsewhere. One field,
`marketing_opt_in`, set by that control. This costs almost nothing to build now
and is expensive to retrofit across a live viewer base.

**Flagged for counsel, not resolvable here:** which jurisdictions take which
default; the wording of the authority-to-disclose affirmation (§7.2); and
whether the in-artifact conversion prompt needs disclosure in the tenant's own
terms with its recipients.

### 7.2 The tenant's obligation

**The tenant asserts authority to disclose at send time** — a single
affirmation that they are entitled to share this material with this recipient.
Due diligence memos contain third-party identity material, and that assertion
belongs to the tenant, not to us.

---

## 8. Data model

Aurora MySQL, same cluster. `share_grant` currently sits in the wallet spec's
data model; it belongs here and should move.

```
viewer_account        viewer_account_id PK, email, verified_at,
                      registered_at NULL,          -- NULL = verified only
                      marketing_opt_in TINYINT(1) DEFAULT 0,
                      marketing_opt_in_at, marketing_jurisdiction,
                      converted_tenant_id FK NULL, created_at

share_grant           grant_id PK, tenant_id FK, memo_id FK,
                      viewer_account_id FK, sent_by_seat_id FK,
                      created_at, expires_at,
                      expiry_set_by_tenant TINYINT(1),  -- ceiling; blocks extension
                      revoked_at, revoked_by_seat_id FK NULL,
                      first_opened_at,
                      UNIQUE KEY (memo_id, viewer_account_id)

share_access_log      access_id PK, grant_id FK, action,   -- view | download
                      occurred_at, ip_hash, user_agent
```

The unique key means re-sending the same memo to the same address updates the
existing grant rather than consuming a second share from the allowance.

> **Built 1 October 2026 in DynamoDB, not Aurora (share-recipient).** The
> model above is the design; what was built is four pay-per-request tables in
> `share.tf`, so that nothing a viewer does reaches the cluster (§4):
>
> - `share_grant`, keyed `"<memo_id>#<viewer_account_id>"` - the key is the
>   unique rule. Revoking flips `revoked`; the item stays. Re-sending
>   reinstates the same item with the same link token. Carries
>   `authority_affirmed_at` (§7.2), which the model above did not. `sent_by`
>   and `revoked_by` are email addresses, as every other act in the product
>   records its author, not seat ids. Indexed by tenant and by viewer.
> - `viewer_account`, keyed by the first 32 hex characters of sha256 of the
>   lower-cased address, so a grant can name its recipient before the
>   recipient has opened anything. Created on the first open.
> - `share_access_log`, written asynchronously.
> - `share_usage`, the allowance and daily counters - not in the model
>   above, and needed so two sends cannot both take the last free share.
>
> There is no foreign key and no cascade from `memo`: an archived memorandum
> still resolves for a grant (migration 030).

---

## 9. Open

1. ~~**Rate limit** (§6) — the number, at every tier.~~ **Settled 1 October
   2026:** 20 shares a day per tenant, every plan.
2. **Counsel review** (§7.1) — jurisdiction defaults for the marketing
   preference, and the authority-to-disclose wording.
3. **Email delivery** — no provider named. Deferred behind an interface like
   payments; verified against live documentation at selection.

**Settled:** watermarked download permitted, revocation limited to future access
(§5); expiry — 2 weeks, extending to 6 months on registration, with tenant-set
expiry as a ceiling (§6); marketing — permitted once registered, subject to the
opt-in control (§7); cached viewer delivery (§4).

Items 1 and 3 are build-phase. Item 2 should start before launch, not at it.

> **Corrected 28 September 2026.** Item 3 is picked: the product sends mail
> through **Amazon SES** (`lambda/api/mail.py`, `lambda/signup/app.py`; UX02
> 10.4–10.5). Identity is **Amazon Cognito** (`auth.tf`); payments are
> **Paddle**. None of this component is built: sharing and the viewer are
> mocked (`CLAUDE.md`, "What is mocked"), and no migration creates
> `viewer_account`, `share_grant` or `share_access_log`.
