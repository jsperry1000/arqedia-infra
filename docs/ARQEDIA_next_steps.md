# ARQEDIA — Next Steps

| | |
|---|---|
| Raised | 28 September 2026, from the documentation review (branch `docs-review-0928`) |
| Purpose | One list of what is left to build or decide, drawn from UX02, the backlog items, the specs, CLAUDE.md "What is open" and the handoffs. For prioritising |
| How to use | Fill **Pri** (1 = first). Each row names its source; the source holds the detail. Items the source marks as needing a decision say so, quoted where the source words it |
| Not included | Anything verified built on main as of 28 September 2026 |
| Revised | 29 September 2026 — done on this branch: CLAUDE (5d47d8f), SPECS (seven specs committed), EOL (`*.md text eol=lf`), FOREIGN (parse-first-upload moved to terraform_package), SEAT-DATA's stale CLAUDE.md line dropped. Filing price decided: $0.25 per split part. PROMPTS stays git-excluded by decision. UNI-01's file is on no disk and in no commit; Propose.tsx no longer carries a fact or document form (UX-21, #135), so CFG-rev D may be moot |

Grouped by area, not by priority. Where a source states urgency, it is in the Work column.

---

## 1. Money and billing

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | 20.1 | A failed generation refunds its charge, and the screen says nothing was charged | — (no-charge-on-failure decided 28 Sep) | UX02 G20 |
| | 20.2 | Composition gets a failure destination; every failed run recorded where somebody can see it | — | UX02 G20 |
| | 20.3 | Carry the ledger entry id into composition and store it on the memo | — | UX02 G20 |
| | 20.4 | Retry a transient model failure inside the run | — | UX02 G20 |
| | 20.5 | The screen shows a failed generation | — | UX02 G20 |
| | EXT-02 | Refund a failed extraction | Mechanism PROPOSED: `wallet.refund()` as for OCR, rather than a credit bucket | backlog EXT02 |
| | 18.13(3) | Enforce plan limits (recorded in migration 033, not enforced) | — | UX02 G18; process_changing_prices |
| | 18.16 | `plans.json` into the API bundle | "a build change" | UX02 G18 |
| | 19.3 | Preselect a plan | — | UX02 G19 |
| | PAY-01 | Whether Paddle amounts belong on our side | Yes — "has not been made" | backlog PAY01 |
| | PAY-02 | Update card; checkout at first sign-in; "plus tax" on pricing; annual pricing; `needs_review` has no reader | Annual blocked on how Paddle price edits behave | backlog PAY02 |
| | 16.12 | Paddle data on the admin page | — | UX02 G16 |

## 2. Trial and signup

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | 19.2 | Trial-ending banner and notice. **"Next up"**; "build the banner before the first paying tenant" | — | UX02 header |
| | ONB-01 | Vetting position; IP retention; disposable-domain list; second-admin invite on lapse; extend FREE_MAIL when public | Yes — "needs a decision and probably counsel" | backlog ONB01; CLAUDE.md open |
| | SIGNUP | `signup_allow` is "a temporary gate, not a product decision about who may buy" | Yes | backlog ONB01 (from HANDOFF 09-19) |
| | 5.2 | Domain refusal at step 1 | Deferred: "revisit when signup opens to the public" | UX02 G5 |
| | TENANT-0 | Tenant 0 has no seat rows (live data, unverified) | — | HANDOFF 09-19 |

## 3. Email

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | 10.4 | Password reset from our SES sender: merged; confirm applied | — | UX02 G10; CLAUDE.md open |
| | 10.6 | Bounce handling: configuration set, SNS, MX | — | UX02 G10; CLAUDE.md open |
| | 10.8 | Invitation token lookup | — | UX02 G10 |
| | 10.9 | Revoked vs accepted invitation | Yes — "a schema decision" | UX02 G10 |
| | 11.5 | Confirm enterprise@ forwarding with a test message | — | UX02 G11 |
| | — | Which product paths send email, per path | Open | CLAUDE.md open |

## 4. Filing and extraction

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | 21.11 / EXT-01 | Filed documents that say "extracting" for ever; find why extraction never ran | — | UX02 G21; backlog EXT01 |
| | 21.5–21.7, 21.9–21.10 | Remaining Group 21 items (21.6 decided) | — | UX02 G21 |
| | OCR-01 | Step 4: a way out of `reading` (removal still refuses a document in `reading`) | — | backlog OCR01 |
| | UP-01 | Confirm before read; charge only what is kept | — | backlog UP01; unreadable spec |
| | UP-02 | Three unverified behaviours: stop polling out of view, fewer reads, block a second submit | — | backlog UP02 |
| | RERUN | `db/rerun_extraction.py:93` DELETEs `extracted_value`, against "read once" and "additive", and can orphan `claim_evidence` | Yes | which_edits_reach_old_documents |
| | UNR | 50-character floor; 88 orphans ("owner's call"); our own OCR (not scheduled) | Orphans: yes | unreadable_documents spec |
| | SA-01 | `set_aside` columns and route; failed extractions behind a link | Parked until real use | backlog SA01 |
| | CP-03 | Measure `locator_kind='none'`, then fix the unit | — (status unknown) | backlog 2026-09-02 |
| | SC-02 | Stop correspondence filling screening fields | — (status unknown) | backlog 2026-09-02; CMP01 |
| | MEMO-01 | Limit persons to those connected to the subject | — (status unknown) | backlog 2026-09-02; CMP01 |
| | CP-04 | Open Items carries no citations | "Arguably a gap statement needs no citation" | backlog 2026-09-02 |

## 5. Memorandum, rewrite and reading

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | UNDO-01 | Undo in the memo | Yes: how far back; is Discard undoable; survives reload | backlog UNDO01 |
| | RW-01 | Rewrite follow-ups: resume after reload (maybe #121), timeout mismatch, test rows, non-`##` sections | Price: "free by decision" | backlog RW01 |
| | HONE-01 | Keep a rewrite prompt | "Decisions pending" | backlog HONE01 |
| | 18.11 | Citation highlight in rewrite mode | — | UX02 G18 |
| | UI-01 | Search within a memo | — | backlog UI01 |
| | UI-03 | Show template and revision on the memo and in Configure | — | backlog UI03 |
| | UI-08 | Check tables on the PDF path (browser path fixed, #124) | — | backlog UI08 |
| | SUBJ-01 | Engagement 29 values; consolidation rule 2; citation placement; one citation per table | Each "a separate decision" | backlog SUBJ01 |
| | CMP-01 | Four residual risks | Item 1: archive memo 120 and engagement 29 | backlog CMP01 |

## 6. Configuration and templates

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | PUB | `registry.publish` still sets `tenant.active_revision`; revision-selection §2 says publishing only makes a revision available | Yes — which is intended | UI_GUIDE_DRAFT step 7; revision_selection |
| | ROLE | Configuring and publishing are admin-only in code; CLAUDE.md's decision says Members do it | Yes — "not settled" | CLAUDE.md correction 17.7 |
| | UX-07 | Configurable section numbering, one global scheme. Held back from UX01, not carried by UX02 | Yes — "agreed against the schema before it is written" | backlog UX01 |
| | TPL-03 | First-run Configure offers bases while calling them memoranda | — | CLAUDE.md open |
| | TPL-02 s5 | Step 5; marketing `PACKS` lists six memoranda where one ships | — | TPL02 spec; CLAUDE.md open |
| | TPL-01 | Section lists for the packs; practitioner validation | Practitioner review | backlog 2026-09-02; CLAUDE.md open |
| | TPL-04 | Steps 3–4; open 1 ("content decision"); open 3 (un-shipping) | Yes | TPL04 spec |
| | REV | Refuse selection while a draft is open (PROPOSED); `pack_key` convention migration (PROPOSED); drop `retired`? | Yes | revision_selection |
| | REFORK | Re-fork restores unbound bindings — "probably wrong" | Yes | TPL02 spec/record |
| | CFG-02 | Dangling `context_sections` keys | — | CFG02 brief |
| | CFG-04 | Config from the client's own file: (a) one memorandum or several; (b) guess composed sections; (c) formats | Yes, a and b | backlog CFG04 ×2 |
| | CFG-rev D | Share the forms between the two config screens | — (depends on UNI-01) | config_consistency_review |
| | CFG-rev E | What `shape_key` is for | Yes | config_consistency_review |
| | UNI-01 | Saving-model decision that unblocks sharing the last two config components. The document was never committed | Yes | HANDOFF 09-09 |
| | STRAY | `configure_screen.tsx` at the repository root, not in the build | — | CLAUDE.md open |

## 7. Sharing and the viewer

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | 12.2 | Free recipient account | — | UX02 G12 |
| | 12.5 | Grant term after registration | "Proposed… awaiting agreement" | UX02 G12 |
| | 12.4 / 12.6 / 21.8 | Viewer, watermark, tables — one design group | Design | UX02 |
| | REG | Recipient registration to download: lead gate, open, or sender's choice; 6-month extension | Yes — "stays as spec until you say" | UX02 conflicts; CLAUDE.md open |
| | SHARE | Share rate-limit number; counsel review | Yes | share_viewer spec |

## 8. Accounts and the admin page

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | 16.10 | Admin reader password rotation — "build before production" | — | UX02 G16 |
| | 16.7 | Sign-in records | "Decide before the admin page shows sign-ins" | UX02 G16 |
| | 18.9 / 18.13(2) / DEL | Account closing and deletion: no deletion path exists; `tenant_domain` is left behind | "Its own design" | UX02 G18; HANDOFF 09-19; CLAUDE.md open |
| | RECOV | Admin recovery policy — "before the first tenant" | Yes | build_index |
| | MFA | Customer pool is `mfa_configuration = "OPTIONAL"`; identity spec says required on every seat | Yes | identity_seats spec |
| | 18.10 | Strip and side icon | — | UX02 G18 |
| | 13.1 | Memo files: drag and drop, filters, folders | — | UX02 G13 |
| | PERM | `signup_attempt.ip` retention and privacy-policy wording | Yes | CLAUDE.md open |

## 9. Infrastructure and operations

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | CRLF | Twelve root `.tf` files and `db/load_pack.py` are CRLF/mixed **on disk** in `c:\terraform\arqedia` (LF in git). Re-check them out before the next plan | — | found 28 Sep; DRIFT01 note |
| | BLD-01 | `__pycache__` excludes on 9 of 12 archive blocks (incl. `admin_api.tf`) | "PROPOSED, and not agreed" | backlog BLD01 |
| | ENV-01 | Dev and prod: state key, workspaces, deploy workflow, migrations record, front-end config | — | backlog ENV01 |
| | DRIFT-01 | `*.js` attribute | — | backlog DRIFT01 |
| | OBS-01 | Declare and import the normalizer log group; retention | — | backlog OBS01 |
| | OBS-02 | Read-only DB user for the reconciler | One identity or several | backlog OBS02 |
| | OBS-03 | One SNS topic and alarms | Who is woken | backlog OBS03 |
| | AUTH-01 | Rewrite the out-of-date `auth.tf` / `admin_auth.tf` comments | — | backlog AUTH01 |
| | X-ROBOTS | No `X-Robots-Tag` anywhere; `/robots.txt` serves the SPA | — | HANDOFF 09-19 |
| | 17.9 | CI test job (the Paddle plans test runs in no workflow) | — | UX02 G17; process_changing_prices |
| | CI | Does CI build the app; `web/` is committed output | Yes | CLAUDE.md open |
| | BR-01 | Migration 013 is on dev only; fallback mixes from the mid colour | "a decision, not a fix" | backlog BR01 |
| | 17.8 | Unused tokens | — | UX02 G17 |

## 10. Product scope, not yet scheduled

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | SC-01 | Screening: OFAC or LSEG; redistribution rights | Yes (A2, E1) | backlog SC01 |
| | AUD-01 | Walk from a fact to its files | A or B | backlog AUD01 |
| | CF-01 | Financial schema as a table | Shape, with a practitioner | backlog CF01 |
| | PACK | Pack domain review, ownership, jurisdictional variants | Yes | plans_starter_packs spec |
| | SEAT-DATA | Seat counts as data in a `plan` table (CLAUDE.md item is stale: `PLAN_SEATS` gone, 18.5) | — | CLAUDE.md open; `seats.py:94` |

## 11. Documentation left over

| Pri | ID | Work | Decision needed | Source |
|---|---|---|---|---|
| | CLAUDE | CLAUDE.md: "Money" no-reversals wording; "Current work" points at a missing UX01 path (should be UX02); stale `PLAN_SEATS` item | Your approval | review 28 Sep |
| | SPECS | Seven specs cited by `build_index.md` were never committed; they exist at `C:\Terraform\terraform_package\docs\build-plans\ARQEDIA DD APP\` | Bring into the repo? | build_index |
| | UX02 | 17.2, 18.2, 18.3, 18.4 built but not marked closed | — | UX02 |
| | PROMPTS | `docs/prompts/` is git-excluded; COMP-01 prompt is done (#164) | Keep, commit or delete? | `.git/info/exclude` |
| | SITE | `docs/Website/` holds two different mocks, `(1)` adds the hero graphic; `SIGNUP_NOTES.md` predates SES, seats, wallet and the allowlist | Which mock is current | Website/ |
| | FOREIGN | `docs/HANDOFF/HANDOFF-parse-first-upload.md` is a Retool/eBL build, not ARQEDIA | Move out? | HANDOFF/ |
| | EOL | `.gitattributes` has no rule for `.md`; the index is LF only because of `core.autocrlf` on this machine | Add `*.md text eol=lf`? | found 28 Sep |
| | GUIDE | `ARQEDIA_UI_GUIDE_DRAFT.md` still a draft | — | backlog-items |
