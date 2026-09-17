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
