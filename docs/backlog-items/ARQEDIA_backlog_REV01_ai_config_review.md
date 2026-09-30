# ARQEDIA — Backlog Item

## REV-01 · AI Review of a tenant's configuration

| | |
|---|---|
| Status | Proposed. Decisions below; nothing built, nothing migrated |
| Priority | Jumps the UX-02 queue, by decision (30 September 2026) |
| Type | One Lambda (or a second mode of the proposer), four API routes, one screen, one `meter_price` row |
| Raised | 30 September 2026 |
| Depends on | The config draft editor, the proposer, the wallet |
| Branch | `feature/ai-review-mode`, from `origin/main` |

---

### The need

A tenant's configuration is written by people who are not prompt engineers
(Config Editors §5.3). A field description too vague to extract against, a
section prompt that asks for a fact no bound field supplies, a document type
whose description will not tell it apart from its neighbour: each one produces
a memorandum that is worse than it needed to be, and none of them is caught by
`registry.validate`, which checks structure, not sense.

AI Review reads the open draft and says what it would change, and why. It also
proposes the fields a memorandum is missing and the document types each field
should be sought in. The person accepts or declines each suggestion. What is
accepted lands in the draft, and nothing reaches a memorandum until the draft is
published.

### What it is, and what it is not

- **It reads the draft (revision 0) and writes only the draft**, through the
  functions in `lambda/shared/editor.py` that every other configuration edit
  uses. No new write path.
- **It never writes without a click.** Every suggestion is offered; none is
  applied. That is the proposer's rule ("matching is shown, never applied",
  `lambda/proposer/app.py:29-33`) and it holds here for the same reason.
- **It never proposes a deletion.** Removing a field or a type is a real break
  (`editor.delete_field` docstring). A suggestion may say a field looks unused;
  deleting it stays a person's act on the ordinary screen.
- **It does not touch extracted values, documents or memoranda**, and it does
  not re-read anything filed. Read once, at filing, stands.
- **It is not HONE-01.** HONE-01 moves one instruction, tried on a real memo,
  into one section prompt. REV-01 critiques the configuration as a whole with no
  memo in view. They are compatible, and neither needs the other.

---

### Settled, 30 September 2026

1. **Administrators only.** `_require_admin` (`lambda/api/app.py:2311`), as
   every draft route is.
2. **$1.00 per session.** A session runs from opening Review Mode to closing
   it. It is charged once, on the first accepted suggestion. A session in which
   nothing is accepted is not charged.
3. **Jumps the UX-02 queue.** No UX-02 branch was open when this was decided.

---

### What the reads found

Read in full for this item: `lambda/shared/editor.py`, `lambda/shared/config.py`,
`lambda/shared/wallet.py`, `lambda/proposer/app.py`, `proposer.tf`,
`db/migrations/015_wallet.sql`, `018_billing.sql`, `033_plan_limits.sql`,
`docs/specs/config_editors_spec_v1.md`, `docs/specs/config_registry_spec_v1.md`,
HONE-01, `ARQEDIA_config_consistency_review.md`. Read in part:
`lambda/api/app.py` (header, `_key`, branding gate, `generate`,
`_require_admin`, the proposer routes, the dispatcher), `lambda/api/seats.py`
(`seats_bought`), `lambda/composition/app.py` (`_invoke`).

**1 · The pipeline never reads the draft, so no job lock is needed.**
`config.py:11-12`: "The draft - revision 0 - is never loaded here: editors
write it, and nothing in the pipeline reads it." Extraction reads the revision
a document was filed under, composition the revision the memo is written under
(`config.py:14-17`). A reviewer that writes only revision 0 cannot collide with
extraction or composition. The mutual-exclusion lock proposed earlier would be
a second record of a fact the revision split already enforces, which is the
failure pattern of `ARQEDIA_config_consistency_review.md`. **Not proposed.**

**2 · The real concurrency is draft against draft, and it already exists.**
The spec's `draft_lock` (Registry §4, §8) was never built. Grep finds no
`draft_lock`, `acquire_lock` or `heartbeat` in any `.py`, `.sql` or `.tsx`.
Two administrators can edit one draft at once today. A review adds a third
writer that works from a snapshot taken minutes earlier. It is handled per
suggestion (below), not with a lock.

**3 · No editor save is partial, except for order and context.**
`save_field` overwrites `label`, `field_type`, `cardinality`, `description` and
`group_key` from the body, defaulting absent ones (`editor.py:749-776`), and
rewrites a table's columns whole (`_save_columns`, `editor.py:792-843`).
`save_section` overwrites `numeral`, `title`, `kind`, `prompt`; only
`sort_order` and `context_sections` survive absence (`editor.py:256-296`).
`save_document_type` overwrites `category_key` (default `other`), `read_mode`
(default `text`) and `always_ocr` (default false) (`editor.py:881-903`).
**So accepting "change this description" must read the whole object from the
draft and write it back whole with one value changed.** Sent alone, the
description would reset the rest. This is the exact fault class the
consistency review records.

**4 · Where a field is found is one relation, written from either end.**
`set_field_documents(field, types)` takes the full set and derives the schema
(`editor.py:560-619`). `set_document_fields` is the same relation read from the
other end (`editor.py:622-662`). A "seek this field in these documents"
suggestion is one call to the first, with the full set.

**5 · The proposer is the pattern to copy.** An asynchronous Lambda invoked by
the API (`app.py:2448`), because reading takes minutes and API Gateway
allows 29 seconds. Progress is an S3 object the screen polls
(`proposer/app.py:19-22`), keyed under a tenant prefix the API checks
(`_own_sample`, `app.py:2438`). Bedrock is called at temperature zero, with
waits on throttling (`proposer/app.py:115-155`). The proposer already reads the
draft (`_existing`, `proposer/app.py:179-216`). It holds only
`rds-data:ExecuteStatement` (`proposer.tf:62-68`) and writes nothing to the
database; the screen accepts through the editor routes.

**6 · `charge()` opens its own transaction** (`wallet.py:538-606`). The editor
functions call `execute_statement` without a transaction id. So the charge and
the draft write cannot be one transaction without changing both modules. See
decision D3.

**7 · The idempotency key already records the session.** `wallet_ledger` has
`UNIQUE (tenant_id, idempotency_key)`, `VARCHAR(64)` (`015_wallet.sql`). A key
of `review:<session_id>` makes the second accept in a session a repeat that
`charge()` returns without debiting (`wallet.py:524-536`). No session table is
needed to charge once.

**8 · Plan gating today reads `tenant.plan` inline.** `may_brand = plan in
("business", "enterprise")` (`app.py:1998`), enforced by `_require_branding`
(`app.py:2009`). CLAUDE.md says nothing decides on `tenant.plan` alone;
`seats.seats_bought` does it properly: `subscription.plan_id` first, and
`tenant.plan` only on a trial. **Enterprise is not a `plan` row** and never has
been (`033_plan_limits.sql`, "ENTERPRISE IS ABSENT, DELIBERATELY"). So a
column on `plan` cannot express "Business and above": an Enterprise tenant has
no row to carry it.

**9 · `registry.validate` already finds the structural faults.** It refuses
unbound fields, tables without columns, column keys without their prefix, and
composed sections reading later ones (consistency review, "Corrected 28
September"). The review should be given those findings, not asked to
rediscover them.

**10 · The models.** `extraction_model_id` = Haiku 4.5, used by the proposer.
`composition_model_id` = Sonnet 4.6 (`variables.tf:19-29`). Both are confirmed
on the live dev Lambdas.

---

### Proposed shape

#### Flow

1. **Open.** `POST /config/draft/review`. Checks: admin, a draft is open, the
   plan allows it, and `wallet.quote(tenant, "config_review")` is affordable
   (refused before a minute of reading, not after). The API mints a
   `session_id` and invokes the reviewer asynchronously. Nothing is charged.
2. **Read.** The reviewer loads `editor.draft(tenant)` and
   `registry.validate(tenant, 0)`, calls the model (below), and writes
   `tenants/<t>/reviews/<session_id>.review.json` to the review bucket,
   rewriting it as each part finishes. Same shape as the proposer.
3. **Poll.** `GET /config/draft/review?session=<id>` returns that object.
4. **Accept.** `POST /config/draft/review/accept {session, suggestion_id,
   value?}`. The server takes the suggestion from its own stored object, never
   from the request body (a person may edit the proposed value; `value` carries
   that and nothing else). It checks the draft still holds `current`, writes
   through the editor function, and charges `review:<session_id>`.
5. **Close.** The session is spent when the screen closes it. A new session
   is a new read and a new price.

#### The model calls

Three kinds, all fed the draft and the validation findings:

- **One per memorandum:** its sections, their prompts and bound fields.
  Critique each prompt against the fields it can actually read.
- **One for the vocabulary:** every field's label and description and every
  document type's description. Critique extractability and classifiability.
- **One for coverage:** the facts each memorandum's sections ask for that no
  field supplies (proposed new fields), and the document types each field
  should be sought in.

One call per memorandum, not one for everything, for the proposer's reason: an
answer that runs past the token limit loses its end with nothing to say so
(`proposer/app.py:24-27`).

#### Suggestion payload

```
{
  "id":        "s-0007",                 minted by the reviewer
  "kind":      "field_description" | "section_prompt" |
               "document_type_description" | "field_found_in" |
               "new_field" | "question",
  "target":    {"field_key": ...} | {"template_key": ..., "section_key": ...} |
               {"type_key": ...},
  "current":   the value as read, or null for new_field,
  "proposed":  the value to write, or null for question,
  "reason":    one or two sentences,
  "question":  for kind "question" only: what the reviewer needs to know,
  "status":    "open" | "accepted" | "declined" | "stale"
}
```

Each kind maps to one existing editor function:

| kind | writes through | read first and sent back whole |
|---|---|---|
| `field_description` | `save_field` | label, type, cardinality, columns with their keys |
| `section_prompt` | `save_section` | numeral, title, kind, template_key |
| `document_type_description` | `save_document_type` | label, category, read_mode, always_ocr |
| `field_found_in` | `set_field_documents` | the full set of types |
| `new_field` | `save_field` (no key), then `set_field_documents` | nothing: it is a create, and a taken key is refused (`editor.py:735-738`) |
| `question` | nothing | — |

A `new_field` does not bind the field to a section. Binding it is
`set_section_fields`, which replaces a section's whole list. See D5.

**Stale is refused, not overwritten.** If the draft no longer holds `current`
when the person accepts, the accept is refused and the suggestion is marked
`stale`. Another administrator's edit is never undone by a suggestion made
before it.

#### Plan gate

`_require_review(tenant_id, role)`: admin, then the plan resolved as
`seats_bought` resolves it (`subscription` → `plan.plan_key`, else
`tenant.plan` on a trial), then `plan_key in ("business", "enterprise")`. The
same set `may_brand` uses, read from the authoritative source. **No schema
change.** `GET /settings` gains `may_review`, so the screen can disable the
control and say why.

#### Charge

- `meter_price`: `(NULL, 'config_review', 100)`. The event name fits the
  `VARCHAR(32)` column.
- Key: `review:<session_id>`. The first accept charges; later accepts in the
  same session are repeats and debit nothing.
- The price is shown on opening Review Mode and again on the first accept
  control, as filing and generating show theirs (UX-02 Group 4).
- Model failure costs nothing: no suggestion means no accept, and no accept
  means no charge. **No refund path is needed**, so the gap between
  `wallet.refund()`, which is document-only, and this item does not arise.

#### Session record

The S3 review object is the session: suggestions, their status, who opened it,
token usage, and the ledger entry id once charged. **No new table.** The
ledger row is the durable record of payment; the object is the working state,
as the proposer's is.

#### What changes in Terraform

A Lambda (or a new mode of the proposer; D1), its role with
`rds-data:ExecuteStatement`, `bedrock:InvokeModel` and the review bucket
prefix, and `REVIEW_FUNCTION` on the API. Four new API Gateway routes. The API
role already holds the four `rds-data` actions that `charge()` needs.

---

### Cost

**Unverified.** The dev database read was declined in this session. The size
below is estimated from the seed packs (`009_pack_revision_1.sql` 108 KB,
`021_pack_from_tenant_2.sql` 140 KB, SQL syntax included), not measured from a
tenant's draft.

A whole configuration is roughly 20–30k tokens. Assume a two-memorandum
tenant: four calls at about 30k tokens in and 4k out each.

| Model | Rate (first-party, $/M in / out) | One session |
|---|---|---|
| Haiku 4.5 | 1 / 5 | about $0.20 |
| Sonnet 4.6 | 3 / 15 | about $0.60 |

Bedrock is billed separately and may differ; confirm against the Bedrock
price page before relying on these figures. At $1.00 per charged session,
Sonnet leaves about $0.40 of margin, and every session closed without an accept
costs the full amount with nothing charged. Measure `tokens_in`/`tokens_out`
on the first ten real sessions (the object records them, as the proposer's
does) before this is called settled.

---

### Against the earlier plan

The plan this item replaces proposed two tables for Item 1: an eligibility flag
on plan or tenant, and a mutual-exclusion lock. **Neither is proposed:**

- **Eligibility flag.** Enterprise has no `plan` row to carry it (finding 8).
  The existing gate is a set of plan keys, and this item follows it.
- **Lock.** The pipeline never reads the draft (finding 1). Draft-against-draft
  contention is handled per suggestion by the stale check.

The only database change is one `meter_price` row, which is a data migration.
It is still a migration and is put to you before it runs.

**BYO-LLM (Enterprise)** stays a separate item and is not started. Two facts
for it: `provider_credential` is spec only (`provider_abstraction_spec_v1.md`
§ at line 176), with no table and no code path to mirror. And every model call
in the system is Bedrock `invoke_model`, so a tenant-supplied credential for
another provider is a second call path, not just a credential table.

---

### Decisions needed before code

- **D1 · A new Lambda, or a second mode of the proposer?** Recommended: a new
  function, `arqedia-dev-reviewer`. The proposer's contract is "reads a
  sample, deletes it" and its failure handling is built around that file. The
  new function copies `_invoke`, `_as_json` and the progress-object pattern.
- **D2 · Which model?** Recommended: Sonnet 4.6 (`composition_model_id`).
  Critiquing prose prompts is judgement, not bounded extraction. Haiku is a
  third of the cost and can be switched by variable.
- **D3 · The order of charge and write on the first accept.** The two cannot
  share a transaction (finding 6). Recommended: quote, write, then charge. The
  rule is that a failed act is not charged: writing first means a refused or
  failed write never takes the dollar. The cost is a narrow race in which the
  write lands and the charge then finds the balance gone. That is one free
  session, logged. Charging first would instead need a refund path for a
  failed write, which does not exist for this event.
- **D4 · Trials.** A trial has no subscription row, so the gate reads
  `tenant.plan`. Does a trial whose `tenant.plan` is `business` get Review
  Mode, spending trial credit? Recommended: yes, since the gate follows the
  plan and money is gated by the wallet.
- **D5 · Should a `new_field` suggestion also offer binding to a section?**
  Recommended: yes, as a second control on the same suggestion that calls
  `set_section_fields` with the section's current list plus the new field. A
  field nothing binds is reported at publish as unbound.
- **D6 · The `meter_price` migration.** One row, `(NULL, 'config_review',
  100)`. Applying it is yours.
- **D7 · Sessions and time.** A session has no fixed end if the tab is left
  open. Recommended: the screen closes the session when Review Mode is closed,
  and a session older than 24 hours refuses accepts.

---

### Not changed

- Extraction, composition, classification, and any revision other than 0.
- The proposer and its routes.
- `editor.py`. Every write goes through it as it stands.
- Any existing table.
