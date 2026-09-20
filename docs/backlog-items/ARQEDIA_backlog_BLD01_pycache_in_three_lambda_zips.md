# BLD-01 — Three Lambda zips carry bytecode, and three do not

**Raised 19 September 2026**, out of a `terraform plan` that showed five
changes where one was expected.

---

## The problem

`data "archive_file"` zips a source directory as it finds it. Running the test
suite writes `__pycache__` into `lambda/api`, `lambda/normalizer`,
`lambda/signup`, `lambda/shared`, `lambda/paddle_processor` and
`lambda/paddle_webhook`, because the tests import those modules. Three of the
archive blocks exclude it and the rest do not:

    paddle.tf:134    excludes = ["__pycache__"]    paddle_processor
    paddle.tf:240    excludes = ["__pycache__"]    paddle_webhook
    reconcile.tf:86  excludes = ["__pycache__"]    reconcile

    api.tf:7         no excludes
    normalizer.tf:17 no excludes
    signup.tf:20     no excludes
    composition.tf:10, extraction.tf:9, proposer.tf:16, render.tf:86,
    textract.tf:51   no excludes

So running the tests changes `source_code_hash` on every function whose block
has no `excludes`, and `terraform plan` reports code changes where not one
byte of source differs. On 19 September that was `api` and `normalizer`
planning as changed alongside the one function that had actually been edited.
Every file inside both deployed zips was confirmed identical to `HEAD` by git
blob hash; the only difference was bytecode.

The comment at `paddle.tf:133` already names the trap — "Running the tests
writes bytecode here; it must not change the zip" — and it is guarded in three
places out of eleven.

## Why it matters more than it looks

- **A plan that lies is a plan nobody reads.** A change with no code
  difference trains whoever is applying to skim past the list, which is
  exactly when a real change slips through. On 19 September the noise nearly
  hid something serious: the deployed `signup` function was built from a
  branch that had never been merged, and an apply would have replaced it
  silently.
- **It deploys bytecode to production.** `.pyc` compiled by whatever Python
  ran the tests, shipped beside the source. Python will ignore a stale one
  where the source is newer, so the risk is small, but nothing is gained by
  sending it.
- **It depends on who ran what.** A plan differs depending on whether the
  person last ran the tests, which makes two people disagree about what is
  deployed.

## What would close it

**PROPOSED, and not agreed.** Either:

- **`excludes = ["__pycache__"]` on every `archive_file` block**, matching the
  three that have it. Eight lines, one per block, no behaviour change.
- **Or a single packaging path** — a variable or a local holding the exclude
  list, referenced by every block, so the next function added inherits it
  rather than repeating it.

The second is the one that survives somebody adding a twelfth Lambda.

## Done when

- Running the test suite leaves every `terraform plan` clean.
- A new `archive_file` block cannot be added without the exclusion, or the
  reason it cannot be enforced is recorded.

## Not in scope

`lambda/shared` and the `docprocessing` layer, which `build-layer.ps1` builds
rather than `archive_file`. Whether bytecode reaches the layer zip is a
separate question and has not been checked.
