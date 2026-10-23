# ARQEDIA — Decisions, 20 Oct 2026

Additive to the 19 Oct handoff; nothing there is changed. Captures decisions made in chat today on the four remaining beta-launch items, plus documentation of three items tracked for later and three pre-real-customer-data items. Verification results from CC added below each relevant item (20 Oct, later same day).

---

## 1. Customer-vetting position (ONB-01)

**What it is:** whether self-serve signup opens with no vetting step, or whether a new tenant needs manual approval before gaining access. Matters because ARQEDIA handles counterparty due-diligence/credit data, so an unvetted tenant can self-provision access to that workflow immediately.

**Decision (stated as provisional — "I think this is a pass"):** no additional vetting gate. Self-serve signup proceeds as currently built, with no manual approval step added for beta. Flagged as provisional per your own wording; treat as settled only once you confirm outright.

## 2. First screening provider (OFAC vs LSEG)

**What it is:** SC-01's open item A2 — which sanctions-screening provider integrates first.

**Decision:** pass — deferred, consistent with how the build plan already categorizes it ("First screening provider | Post-launch"). No provider selected for beta; no screening capability ships at launch.

## 3. Starter-pack practitioner review

**What it is:** TPL-01's open item — someone with credit judgement needs to decide which sections each starter-pack memorandum (Credit, KYC, Lender, etc.) carries. Build plan already notes this is practitioner work, not engineering.

**Decision:** assigned to sperry@ebl-finance.com.

## 4. Recipient registration to download/read a shared memo

**Decision:** a recipient does **not** need to register to read or download a shared memo. Registration is required only to retain access after 2 weeks.

**Verified against live code, 20 Oct:** matches, with one undocumented gap.
- Registration is not required to read or download. `GET /view/{grant_id}` and `POST /view/{grant_id}/download` check only the link token and the grant (`lambda/share_viewer/app.py:1153`) — never registration status.
- But the link alone doesn't open anything: both routes also require a *verified browser* (`app.py:1159`, `:1164`, gate at `:623`). Verifying means entering a code emailed to the recipient (`/verify/code`, `/verify`), lasting 6 months per browser — deliberately added so a forwarded link reads nothing (`app.py:575–583`).
- Registration (`/register/code`, `/register`, `/register/confirm`) only extends term: on confirm, every grant the recipient holds recomputes to 6 months from its own send (`app.py:839`, `:926`).
- Term rule: tenant-set expiry wins; otherwise 6 months if registered, else 14 days (`lambda/shared/share_rules.py:163–174`, `VERIFIED_DAYS = 14` at `:29`). Expired grants refused at `:202`. The 2-week/6-month terms match `share_viewer_spec_v1.md` §3 and §6 (`:204–205`).
- **Gap:** §3 (`:88`) defines "verified" as "reached by clicking the link." The code additionally requires the emailed verification code — stricter than the spec, and the spec doesn't record this. Not a functional bug, but the spec is out of date. **Open: update the spec, or was the emailed-code step itself a decision that should be reconciled with §3 — your call.**

## 5. Stale "Documents reviewed" / "Sources cited" counts after an Update

**Issue, as raised in the copy review:** when a memo is updated, the front-matter counts "Documents reviewed" and "Sources cited" are not recalculated — they can show the counts from an earlier revision.

**Verified against live code, 20 Oct: confirmed still broken, not fixed.**
- Counts are written only at generation, by `cleanup.front_matter()` (`lambda/composition/cleanup.py:284–285`), called once in the generation path (`lambda/composition/app.py:1580–1583`).
- Update never reaches the memo head: `_split_saved()` (`app.py:937–949`) splits only at `##` section headings — the title/counts block above the first section belongs to no section, so Update never reads or rewrites it.
- Update itself saves nothing directly — each changed section becomes a `memo_rewrite` proposal, reaching the memo only through `revise`, section by section (`app.py:880–883`).
- Net effect: after an Update brings in newly filed documents, the counts keep their original values. Matches the known open item already in `CLAUDE.md` ("Update leaves a memo's front matter as it was") — confirmed still open, not a new finding.

## 6. Six starter-packs claim vs. four live packs

**Decision (reaffirmed):** hold. Site copy isn't changed until tenant 5's packs are redone; no action until then.

---

## 7. Before taking real customers' data

**#9 — Account deletion doesn't exist.**
- No deletion path currently covers: Aurora rows for the tenant, the `tenant_domain` mapping, or `share.purge_tenant`.
- At minimum, a manual procedure needs to be written down (who runs it, what it touches, in what order) even before any automated deletion is built.
- Blocks taking real customer data because there'd be no way to honor a deletion request.

**#10 — `signup_attempt.ip` retention has no set limit.**
- IP addresses are currently retained with no defined expiry.
- Needs: a retention limit set (a concrete duration), plus privacy wording describing that retention.
- The Terms/Privacy draft from PR #318 is the designated place to add that wording once the limit is decided.

**#11 — EXT-02: failed extraction is charged and not refunded.**
- Filing and generation now refund on failure (per 20.1/20.2, built and verified 19 Oct).
- Extraction does not yet follow the same rule — a failed extraction still consumes the customer's charge.
- Inconsistent with the refund pattern just established elsewhere in the pipeline; worth closing before real customer billing is at stake.

---

## CLAUDE.md merge status
`docs/decisions-2026-10-20` (commit `208622e`) needed no merge — already on main as **#338**, identical 30-line addition. Confirmed docs-only; nothing else touched.
