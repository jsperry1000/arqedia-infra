# Share & Viewer Accounts — Spec v1.0

**DD SaaS product · greenfield · design spec**
Component 5 of 9. Gated by *Wallet & Entitlement Gate v1.0*. Consumes memos
produced by *Pipeline v1.0*.

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

**Two viewer states.** *Verified* — reached by clicking the link, 30-day access,
no relationship with us. *Registered* — the viewer accepts our terms and sets a
password and multi-factor, access extends to 6 months, and §7 applies
(*Identity* §4). The prompt to register
lives inside the memo view and leads with the extension, which is the honest
pitch: register and keep access for six months instead of thirty days.

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

---

## 6. Allowance, expiry, revocation, audit

| | Base | Small Business | Enterprise |
|---|---|---|---|
| Shares per month | 5 | unlimited | negotiated |
| Rate limit | applies | applies | applies |

**A rate limit applies at every tier including unlimited.** Free viewer accounts
with no revenue behind them are an abuse and storage surface; "unlimited" is a
commercial promise about normal use, not an invitation to bulk-send.

**Expiry — settled, two-stage.**

| Viewer state | Grant term |
|---|---|
| Sent, email-verified only | 30 days from send |
| Registered with the app | Extended to 6 months from registration |

Registration is a real signup — the viewer accepts our terms and privacy policy
and sets a password. It costs nothing, grants no product capability beyond
longer access to memos already shared with them, and is the moment a passive
recipient becomes someone with a direct relationship to us.

**The tenant retains the ceiling.** If a tenant explicitly sets an expiry at
send time, that date wins and registration cannot extend past it. Extension
applies only where the tenant left the 30-day default, which signals a default
rather than a deliberate limit. A tenant who sets a short window for a reason
keeps it.

**Extension is per grant, applied at registration and to grants received
afterwards**, across every tenant that has shared with that viewer.

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
   (30d)         (6 months)        (paying)
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

---

## 9. Open

1. **Rate limit** (§6) — the number, at every tier.
2. **Counsel review** (§7.1) — jurisdiction defaults for the marketing
   preference, and the authority-to-disclose wording.
3. **Email delivery** — no provider named. Deferred behind an interface like
   payments; verified against live documentation at selection.

**Settled:** watermarked download permitted, revocation limited to future access
(§5); expiry — 30 days, extending to 6 months on registration, with tenant-set
expiry as a ceiling (§6); marketing — permitted once registered, subject to the
opt-in control (§7); cached viewer delivery (§4).

Items 1 and 3 are build-phase. Item 2 should start before launch, not at it.
