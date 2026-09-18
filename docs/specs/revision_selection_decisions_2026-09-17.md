# Revision Selection — Decision Record

**17 September 2026**
Additive to *TPL-02 Base and Templates* and *TPL-04 Authoring a memorandum
template*. Those specs are not edited beyond a pointer to this file; where this
record differs, this record applies from this date.

---

## 1. Supersedes

| Spec wording | Now |
|---|---|
| TPL-04 — "A template is authored… in a real tenant… When it is right, it is exported into the catalogue" | Authoring happens directly in tenant 0. Nothing crosses tenants, and there is no export |
| TPL-04 — "A script under `tools/`, run by hand against dev" | No script. `tools/` is not created |
| TPL-04 — "exporting the same `pack_key` again writes a new revision and the older one stops being offered… `template_packs()` returns the highest revision for each `pack_key`" | What is on offer is an explicit mark, not the highest revision |
| TPL-02 record — "Nothing validates a pack revision and nothing can — `tenant_id` comes from the token, so tenant 0 is unreachable" | Tenant 0 is reached by a curator, and what that means is open (section 3) |

**TPL-04 open item 2 is answered:** authoring happens in tenant 0 directly.

---

## 2. Approved

1. **Publishing makes a revision available, and nothing more.** Many published
   revisions coexist. Publishing is still the act that says a person looked at
   it.
2. **A separate tick selects which published revision is in use.**
   `tenant.active_revision` is that tick. It exists (migration 008) and is
   already read by composition, the normalizer and `GET /config`; what is
   missing is a way to set it other than publishing.
3. **It applies to every tenant, including tenant 0.**
4. **Reverting is selecting an earlier published revision.** Nothing is
   retired, nothing is deleted, and an earlier revision can always be selected
   again.
5. **What is already filed or generated does not move.** A document pins
   `document.config_revision` at filing and a memorandum pins
   `memo.config_revision`; both keep resolving against the revision they name.
   Selecting a revision decides what NEW work is written against.
6. **In tenant 0 only, a further tick marks a memorandum as on offer**
   ("push to pack"): it is what new tenants are offered in Get started. The
   base on offer is marked the same way.
7. **What is on offer is the mark, never the highest revision.**
   `_pack_revision`, `packs()` and `template_packs()` read the marks.
   `packs()` was changed on 17 September to return the newest published base
   per key; this item supersedes that, and the code stays as it is until the
   tenant-0 work happens.
8. **Two rules carry over from TPL-04 to the mark.**
   - **The missing-facts refusal.** A memorandum whose bindings are not all in
     the base on offer cannot be marked, and the refusal names what is
     missing. Today `fork_template` catches this at the customer, at the worst
     moment.
   - **Only the memorandum.** A template pack carries `config_template`,
     `config_section` and `config_section_field` and nothing else. Facts,
     document types, schemas and categories belong to the base.
9. **A draft opens from the selected revision**, not from the newest published
   one, or editing after reverting silently reopens the newer work.
10. **Publishing keeps numbering from the highest revision**, whichever is
    selected. The series is append-only; selection does not renumber it.

### Amendment — 17 September 2026

**Selecting a revision is refused while a draft is open.** The refusal names
the revision the draft was opened from, and says it must be published or
discarded first. PROPOSED.

A draft is a copy of the revision it was opened from, and publishing numbers
from the highest revision (item 10). Selecting another revision underneath an
open draft would leave a person editing one configuration while new work filed
against another, and their publish would ship the first over the second.

### Note — 17 September 2026

**`pack_offer` is written only by migration 024.** The table holds the marks
and `registry` reads them, so what is on offer is no longer derived from the
newest revision. Nothing in the app sets or clears a mark: putting a
memorandum on offer, moving it to another revision or taking it off all mean
another migration until a screen exists for it.

**No route writes `pack_offer`**, so nothing reachable by a tenant can change
what is offered.

**The curator is `admin@arqedia.com`, an administrator of tenant 0.** Created
by hand in the Cognito pool; `custom:tenant_id` is immutable, so no other
account can be moved to tenant 0. What stops a tenant token reaching tenant 0
is still that no such token is issued: `caller()` accepts whatever tenant the
token carries, and the control is that only this account carries 0.

### Note — 17 September 2026, what tenant 0 is refused

**Refused deliberately.** `lambda/api/app.py` names five routes in
`CURATOR_REFUSED_ROUTES` and refuses them for tenant 0 with one sentence: the
ARQEDIA workspace curates the catalogue and does not file documents, generate
memoranda or subscribe.

    POST /config/templates/fork    it would copy a memorandum into tenant 0's
                                   own draft, beside the original
    POST /uploads
    POST /engagements/{id}/file
    POST /engagements/{id}/generate
    POST /billing/checkout

**Also refused deliberately, at the two ends of an invitation.**
`seats.invite` refuses to invite into tenant 0, and `signup.accept` refuses an
invitation that names it. A seat there is created by hand.

**Refused incidentally, and NOT to be mistaken for controls.** Each of these
refuses today for a reason that can change tomorrow:

    POST /config/fork          refused because tenant 0 has published
                               revisions, not because it is tenant 0
    POST /settings, /settings/logo, /settings/logo/confirm
                               refused because branding wants Business or
                               Enterprise and tenant 0 is on 'base'
    POST /wallet/top-up        refused because there is no subscription
    POST /billing/plan         refused because there is no active subscription
    filing and generating      would also fail for want of funds, which is
                               why they are named above as well

Funding a wallet, changing a plan or publishing nothing would remove any of
those refusals without anybody deciding to.

**This answers the first item in section 3 below**, which was written before
the curator existed.

### Note — 18 September 2026, marking what is on offer

**The mark is per memorandum within a revision.** That is what `pack_offer`
already stores: one row per `pack_key`, naming a revision and a
`template_key`.

**Unticking takes a memorandum off offer.** The row is deleted. It stops
appearing in Get started, and `fork_template` refuses it by name. No tenant
who already took it is affected, and no revision is touched.

**Every mark names the same revision, and the base is not marked separately.**
The revision a memorandum is offered from is the revision its base comes from.
This is forced rather than chosen: `fork_template` resolves a template's
missing facts from the BASE mark, so a memorandum marked at one revision and a
base at another refuses at the customer with "this template binds facts the
base does not define" - the worst possible moment, and the one item 8 was
written to move earlier.

**Marks may not span revisions.** A tick at a revision other than the one the
marks name is refused. Offering from a newer revision is a separate,
deliberate act - MOVE THE OFFER - which re-points every mark, base and
memoranda together, to that revision at once and reports what it moved. It
refuses, naming them, where the new revision does not hold every memorandum
currently marked.

**One route, and it carries the whole offer.** `PUT /config/offer` takes a
revision and the memoranda offered from it, and replaces every mark in one
transaction. The rule above is then structural rather than policed: there is
no way to express a mark at a second revision. Ticking is a name added,
unticking a name left out, and moving the offer is the same call with a
different revision. PROPOSED.

**The curator never sets a pack key.** `pack_key` is never written into a
tenant's configuration: a forked memorandum is keyed by `template_key`,
`forked_from` records `pack:<tenant>:<revision>`, and the "already yours"
marker reads `template_key`. Nothing downstream remembers it, and the one job
a stable key could do - unifying a memorandum across two revisions offered at
once - cannot arise while marks may not span revisions. A tick writes
`pack_key = template_key`, and a migration rewrites the four hand-written keys
so there is one convention rather than two. PROPOSED.

### Note — 18 September 2026, the Catalogue screen

**The rail's "Configure a report" becomes "Catalogue", and a page rather than
a fly-out panel.** It carries:

    the tenant's own memoranda   the body of the page, which is what "Open an
                                 existing report" listed in the panel
    three actions                Create from scratch; Create from a report you
                                 already write; Select an ARQEDIA Template

"Open an existing report" leaves the actions because the memoranda it listed
are now the page itself.

**In tenant 0 the same page carries the ticks.** Tenant 0's own memoranda are
the catalogue, so a tick sits beside each one and means "offered". The page
also says which revision the marks name, which is not necessarily the revision
in use - tenant 0 today has marks at revision 9, revision 9 in use, and a
draft open over it. MOVE THE OFFER lives there.

**The screen reads the tenant from the token**, as `App.tsx` already does for
the signed-in line: `custom:tenant_id` off the ID token payload. No field is
added to `GET /config`.

Three things follow, and one has teeth:

    what the UI hides is not a control   the refusal lives in the dispatcher
                                         beside CURATOR_REFUSED_ROUTES, which
                                         is what the server trusts
    the claim is a string                "0", not 0, and 0 is falsy: a
                                         careless `if (tenantId)` makes tenant
                                         0 the one tenant the check never
                                         fires for
    custom:tenant_id is immutable        nobody can move themselves to tenant
                                         0; that is the real control, and it
                                         is recorded above

PROPOSED, all of it. No code is written.

---

## 3. Open

- **The curator identity, and what stops a tenant token reaching tenant 0.**
  Nothing distinguishes an ARQEDIA curator from a tenant administrator today:
  both are `custom:role = admin`, and the tenant is whatever the token says.
  TPL-04 refused a route into tenant 0 in writing — "a route that could would
  be a route worth attacking" — and this record does not answer it.
- **Whether `status = 'retired'` is dropped**, and revisions 2 and 3 of tenant
  0 republished. Under this model what is on offer is the mark, so `retired`
  carries no meaning; migrations 021 and 022 used it before this record
  existed.
- **`fork_template` copies every template row in its source revision.** A
  tenant-0 revision under this model holds several memoranda, so the fork has
  to take the one that was marked.
- **Where the marks live.** No table holds them. A flag inside a revision
  cannot: a revision is immutable and cached for the life of a container.
