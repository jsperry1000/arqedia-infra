# ARQEDIA — Backlog Item

## DRIFT-01 · Six Lambdas plan as changed on `main` with no code change behind them

| | |
|---|---|
| Status | Recorded, not fixed |
| Priority | Before the next apply |
| Type | Build, Terraform |
| Raised | 21 September 2026 |

---

### What this is

`terraform plan` on `main`, from a clean checkout with nothing edited, wants to
redeploy six Lambda functions. Two git-ignored things in the long-lived working
copy at `c:\terraform\arqedia` are baked into the deployed zips and are absent
from any fresh checkout. `source_code_hash` differing is therefore **not**
evidence that the source differs, which is the thing that makes this dangerous
rather than merely untidy.

It is the trap CLAUDE.md already names — "a resource that plans as changed with
no code difference is line endings, not code" — wearing a second coat.

---

### The baseline

Both runs from `c:\terraform\arqedia-extraction`, a `git worktree` of this
repository, with `.terraform.lock.hcl` and `build/layer-docprocessing.zip`
copied in and `terraform init` reusing `aws 6.61.0` and `archive 2.8.0`.

```
main (9130d0d)                        Plan: 0 to add, 6 to change, 0 to destroy.
  data.aws_iam_policy_document.api    will be read during apply
  aws_iam_role_policy.api             will be updated in-place
  aws_lambda_function.composition     will be updated in-place
  aws_lambda_function.extraction      will be updated in-place
  aws_lambda_function.normalizer      will be updated in-place
  aws_lambda_function.proposer        will be updated in-place
  aws_lambda_function.render          will be updated in-place

extraction-error (a246254)            Plan: 0 to add, 7 to change, 0 to destroy.
  the same six, plus aws_lambda_function.api
```

Only `aws_lambda_function.api` belongs to the branch. Every other line is
already true of `main`.

```
composition  fs/wpU2YgIkVE/IdvE1ZXgKnypolyOzbtjZcv+zs+J8= -> 80stK5HiYtvaYO+1vcdY5/RdcdKyve/EWsYNszvZHss=
extraction   1aD2Pd9D7yW19RvIBgG9QtRjlTR++NtdGTk2yXH1Qc0= -> UDuuiyyg7aIEvme+dTxRmmKZKutl2ZToOo0BuJEwWTs=   (on main)
normalizer   wPFsnNuGmJoRvb3QyIGBVKSL7CQiqJT59n/D4s3rv2c= -> Z0UAIvWD24H+9Ri4zRL+J2L++CBWgWqkPCU2Vjym3mc=
proposer     guvwiMD9P6cA2kZTo5yx5aG2o6Roo6AHYhMGA7f6mis= -> 0d8HYzV9k60H6cL/3ZUkUBmjZzqIZtfKlfawhaXQcQI=
render       NZBtRqpa9rysvWELUbXseEc7kKcsR+hvLPgMh0H3FEw= -> xNivczNKf8HEh0b7So2AiSfw3qJZ3C6VSEl1CbXiYSQ=
```

`archive_file` is deterministic over content: the same source in two different
trees, checked out at different times, produced the identical hash. So each
difference above is a real difference in what would be shipped.

---

### Cause 1 · CRLF in three Lambda sources

`.gitattributes` says `*.py text eol=lf`. Three working copies have drifted
from it. Counted per directory, `.py` files with CRLF terminators:

```
                 c:\terraform\arqedia   fresh worktree
proposer                            1                0
composition                         1                0
normalizer                          1                0
api                                 0                0
extraction                          0                0
signup, reconcile, render           0                0
```

The deployed zips were built from the first column. Any clean checkout builds
the second, and those three functions plan as changed for ever.

---

### Cause 2 · `lambda/render/sample.pdf`

Present in `c:\terraform\arqedia\lambda\render\`, absent from a clean checkout,
ignored by the `*.pdf` line in `.gitignore` — and sitting inside the
`source_dir` that `render.tf:89` archives. **It is inside the deployed
render.zip.**

Nothing references it:

```
grep -rn "sample.pdf\|sample_pdf" lambda/render/*.py render.tf   →  (no output)
```

So either it is dead weight that should be deleted from the working copy, or it
is needed and must be committed. Applying from a clean tree removes it from the
function either way, without saying so.

---

### Why it is worse than an untidy plan: `-target` does not contain it

`api.tf` builds the API's environment from its neighbours:

```
154:  COMPOSITION_FUNCTION = aws_lambda_function.composition.function_name
162:  RENDER_FUNCTION      = aws_lambda_function.render.function_name
163:  PROPOSER_FUNCTION    = aws_lambda_function.proposer.function_name
```

`-target` includes a target's dependencies. So:

```
terraform apply -target=aws_lambda_function.extraction -target=aws_lambda_function.api

Plan: 0 to add, 5 to change, 0 to destroy.
  aws_lambda_function.api
  aws_lambda_function.composition     ← drift, not asked for
  aws_lambda_function.extraction
  aws_lambda_function.proposer        ← drift, not asked for
  aws_lambda_function.render          ← drift, not asked for
```

**A two-function apply redeploys five**, three of them carrying the drift — and
the render one silently dropping `sample.pdf`. There is no narrower target that
touches the API alone.

---

### Not the same thing: `aws_iam_role_policy.api`

It appears in every plan above and is **not** drift. `data
"aws_iam_policy_document" "api"` ends with a `lambda:InvokeFunction` statement
over `aws_lambda_function.composition.arn` and `aws_lambda_function.proposer.arn`.
A data source depending on a resource scheduled to change is deferred to apply,
so its JSON is unknown at plan time and Terraform prints the whole existing
policy as removed. The content is not changing; the ARNs are stable across an
in-place update. It will stop appearing when composition and proposer stop
appearing.

---

### One control that still holds

`aws_lambda_layer_version.docprocessing` does **not** drift. It refreshes at
version 39 and stays out of every change set, because `normalizer.tf:11-12`
reads `build/layer-docprocessing.zip` by name and hash rather than archiving a
directory. That is also the reason the zip must be copied into any worktree
before a plan will run at all.

---

### Not in scope

Fixing it. Normalising the three files to LF and deciding `sample.pdf` both
touch Lambda sources outside the `extraction-error` branch, and one of them —
`normalizer` — is under active edit in another session.

---

### Applied through, 21 September 2026

SUBJ-01 needed `api`, `extraction` and `composition`. There is no narrower
target that reaches them, for the reason set out above, so the drift was
accepted and applied rather than worked around. The decision was taken by the
user on 21 September; this section records what actually shipped.

Applied from `c:\terraform\arqedia-subject`, a `git worktree` at
`feature/subj-01-engagement-subject`, with `.terraform`, `.terraform.lock.hcl`
and `build/` copied in. **Five functions were deployed, not three.**

```
                  deployed before              deployed after
api          vYlrulwC+sX2gLxjHKahyfrlPn4r6drR1/VeZyCtcUc=  QLoWwGrqYJWqISebrIZCM3xzH7ZjX6Jq0hKCxofVQbk=
extraction   CA37Kxcebvj3T1pB73pyZWnkrc5mCksfScYw1H2V6dY=  WiRcYNg5AVALWxI78BF8wnITRLYR5TvLn7UrMirPYzQ=
composition  AvlEsXURRtpcAuKAdU6v3ltSpcR6amQ7lImY8em2LP4=  wMya551u2scRnO78dXgcxE1XCg7gphwxVPAWWJ2zDV4=
proposer     guvwiMD9P6cA2kZTo5yx5aG2o6Roo6AHYhMGA7f6mis=  0d8HYzV9k60H6cL/3ZUkUBmjZzqIZtfKlfawhaXQcQI=
render       NZBtRqpa9rysvWELUbXseEc7kKcsR+hvLPgMh0H3FEw=  xNivczNKf8HEh0b7So2AiSfw3qJZ3C6VSEl1CbXiYSQ=
```

`api`, `extraction` and `composition` carry SUBJ-01. `proposer` and `render`
carry nothing but this drift: they were pulled in as dependencies of the
targets and their source has not changed since 4 and 20 September.

The three `after` values for `proposer`, `render` and `composition` are the
ones this document predicted in **The baseline**, unchanged. Cause 1 is
therefore closed for `proposer` and `composition`: what is deployed is now
what a clean checkout builds, which is what `.gitattributes` says it should
be. `normalizer` is untouched and still drifts.

### `render` now runs without `sample.pdf`

Cause 2 is resolved by removal, as this document said it would be. Confirmed
by downloading the deployed bundle rather than by inferring it from the hash:

```
aws lambda get-function --function-name arqedia-dev-render  ->  Code.Location
unzip -l  ->  app.py, style.py          (two files; no sample.pdf)
```

And exercised rather than assumed - the branding preview is the one path that
renders a PDF from nothing but a tenant's colours, and is where a missing
sample would have shown:

```
aws lambda invoke arqedia-dev-render  {"tenant_id": 1, "preview": true}
  ->  {"status": "ok", "plan": "business", "url": <presigned>}
```

So `sample.pdf` was dead weight. **It is still present in
`c:\terraform\arqedia\lambda\render\` and is still git-ignored**, so the next
apply from that working copy puts it back into the function. Deleting it there,
or committing it, is the remaining half of Cause 2 and is not done.

### A third cause, found and cleared: `__pycache__`

Running `python -m unittest discover -s tests` creates `__pycache__` in every
`lambda/` directory the tests import - nine of them here. Each sits inside a
`source_dir` that `archive_file` archives with no excludes, so the `.pyc`
files go into the zips and move the hash. Two plans minutes apart disagreed on
`api`, `extraction`, `composition` and `render` for this reason alone, and
agreed again once the directories were removed.

That is **BLD-01**, reached from a new direction: it is not only the long-lived
working copy that can pollute a bundle, it is any tree the tests have been run
in. `archive_file` remains deterministic over content; the content had changed.

Verified clean before this section was written - every deployed bundle
downloaded and listed:

```
api 5 files, extraction 1, composition 2, proposer 1, render 2
pyc or __pycache__ in any of them:  False
```

The durable fix is an `excludes` on each `archive_file`, which belongs to
BLD-01 and is not done here.

---

## Addendum, 21 September 2026 · the same defect in `web/`

Found while building `failed-row-tick`. The Lambda zips are not the only
artefact whose hash a clean checkout cannot reproduce: **the front-end bundle
is not reproducible either, and here the drift is already committed.**

### The four sources

`.gitattributes` names `*.tf`, `*.py` and `*.sql` and nothing else, so these
are stored with CRLF while the committed `web/` output was built from LF
copies of them:

```
brand/logo-deep.svg      CRLF in the repository
brand/logo-white.svg     CRLF in the repository
ui/src/index.css         CRLF in the repository
ui/src/tokens.css        CRLF in the repository
```

Vite hashes an asset by its bytes, and a line ending is a byte. So a build
from a clean checkout emits different filenames for files nobody edited:

```
built from the repository as checked out    built from LF copies
web/assets/logo-deep-C3csgApn.svg           web/assets/logo-deep-Cc-XAy_2.svg   ← committed
web/assets/logo-white-BA7qHUFe.svg          web/assets/logo-white-BjJcKX-d.svg  ← committed
```

The content is identical. `git diff` over the emitted CSS and both SVGs reports
**no changed lines at all** — only `LF will be replaced by CRLF`.

### What it costs

Anyone running `npm run build` on a clean checkout sweeps three unrelated asset
replacements into their commit: two logos added under new names, two deleted
under the old, and `web/index.html` rewritten to match. Nothing warns them, and
the diff looks like real work.

**It has already happened.** `origin/feature/subj-01-engagement-subject`
carries `web/assets/logo-deep-C3csgApn.svg` and
`web/assets/logo-white-BA7qHUFe.svg` — the CRLF-hashed pair — where `main`
carries the LF-hashed ones. Merging it swaps both assets for byte-identical
copies under different names.

CI does not catch it: `.github/workflows/deploy-frontend.yml` runs
`aws s3 sync web/ --delete` on what is committed and never builds, so whatever
hash a person's machine produced is what ships.

### Two more git-ignored files the build needs

A clean checkout cannot build the application at all without:

```
ui/.env          required, no default; the build refuses rather than point a
                 bundle at the wrong Paddle account. Sandbox on dev, and the
                 client-side token is public by Paddle's own documentation.
ui/node_modules  npm ci, from the committed package-lock.json
```

`ui/.env.example` is committed and documents the first. Neither is a defect;
they are recorded here because a worktree needs them before `web/` can be
rebuilt, exactly as a plan needs `build/layer-docprocessing.zip`.

### What was done about it on `failed-row-tick`

The four sources were normalised to LF for the build, so the output reproduced
the committed asset names, and then restored. That branch's `web/` diff is the
bundle and one line of `index.html`, and nothing else. **The normalisation was
not committed** — it is a workaround for one build, not a fix.

### Still not in scope

Fixing it. The honest repair is `.gitattributes` covering `*.svg` and `*.css`,
then one commit that normalises those four files and rebuilds `web/` — which
touches the front end while another session has it open.

---

## Addendum, 22 September 2026 · a fifth source, `ui/index.html`

Found on `ux-cite-links` while building 18.1. The list of four above is
incomplete; nothing in it is wrong.

### The source

```
ui/index.html            CRLF in the working copy, LF in the repository
```

Vite does not hash `index.html` - it is emitted by name - so this one does not
show up as a renamed asset. It is worse than that: **Vite copies the
template's line endings straight into `web/index.html`**, so the whole file is
rewritten rather than the two lines that actually moved.

```
$ git cat-file blob $(git rev-parse origin/main:web/index.html) | count
CRLF 0 LF 17
$ git cat-file blob $(git rev-parse HEAD:web/index.html) | count      # first build here
CRLF 15 LF 17
```

`core.autocrlf` is `true` in this worktree and did **not** normalise it on
add. `.gitattributes` names `*.tf`, `*.py` and `*.sql` and nothing else, so
there is no attribute to fall back on.

### Measured, all five

The list of four above says "CRLF in the repository". Measured on the blobs
rather than on the working copy, it is the other way round - and the defect is
identical either way, because what a build reads is the working copy:

```
$ git cat-file blob $(git rev-parse origin/main:<path>) | count
brand/logo-deep.svg    stored: CRLF 0 LF 9
brand/logo-white.svg   stored: CRLF 0 LF 9
ui/src/index.css       stored: CRLF 0 LF 1587
ui/src/tokens.css      stored: CRLF 0 LF 66
ui/index.html          stored: CRLF 0 LF 16
```

All five are LF in the repository and CRLF on disk, smudged by
`core.autocrlf = true` on checkout. The list stands as written; this is the
measurement behind it.

### Why it hides

`git diff` shows two changed lines, because it compares text. `git show
--stat` shows the truth:

```
web/index.html                        |  34 ++++++-------      first build, LF -> CRLF
web/index.html                        |   4 +--                rebuilt from an LF template
```

A person reading the diff sees the two asset names they expect and commits.
The rest of the file went with it. The CLAUDE.md rule - "a resource that plans
as changed with no code difference is line endings, not code" - has a second
form here: **a file whose stat says every line changed and whose diff says two
did is line endings.**

### What was done about it on `ux-cite-links`

All five sources were normalised to LF for the build and restored afterwards.
The first commit was amended, not left standing: `web/index.html` is now LF
and four lines against `main`, proved with `git cat-file` on the blob rather
than with `git diff`, which hides exactly this. The normalisation was not
committed, for the same reason the addendum above gives.

### Still not in scope

Fixing it. The repair named above - `.gitattributes` covering `*.svg` and
`*.css` - must cover `*.html` as well, and the one normalising commit must
include `ui/index.html`, making it five files and not four.

---

## Addendum, 23 September 2026 · fixed, and three things above superseded

Branch `drift01-normalise`. `.gitattributes` now carries `*.svg`, `*.css` and
`*.html` beside the three lines it always had. Everything above stands as the
record of how this was found; four statements in it are no longer true and are
marked here rather than edited out.

### The repair was not a renormalisation. Nothing in the repository was wrong.

This is the correction that matters, because two sessions got it backwards -
including the audit of 22 September that asked for this branch.

```
                         blob CR bytes    working copy CR bytes
brand/logo-deep.svg                  0                        9
brand/logo-white.svg                 0                        9
ui/src/index.css                     0                     1708
ui/src/tokens.css                    0                       66
ui/index.html                        0                       16
web/index.html                       0                       17
```

Counted as bytes with `od -An -tx1 | grep -c '^0d$'`, on the blob reached
through `git cat-file blob $(git rev-parse HEAD:<path>)`. **Every one is LF in
the repository and CRLF only on disk**, smudged by `core.autocrlf = true` at
checkout. `git add --renormalize .` across the whole tree stages **nothing**:
there is nothing stored wrongly to correct.

So the attribute does not repair the history. It repairs the **checkout**:
`text eol=lf` overrides `core.autocrlf`, so these files now arrive LF and a
build reads LF. Re-checking out the 26 tracked files the new rules cover took
4,193 CR bytes on disk to 0, and `git status` stayed clean throughout, which
is the proof that the stored bytes never moved.

**SUPERSEDED — the 21 September addendum, "The four sources":**

> ```
> brand/logo-deep.svg      CRLF in the repository
> ```

Wrong. CRLF on disk, LF in the repository. The defect it describes is real and
the consequence is exactly as written; only the location is misstated.

**STANDS — the 22 September addendum, "Measured, all five":** it says "All
five are LF in the repository and CRLF on disk, smudged by `core.autocrlf =
true` on checkout", and it is right. The audit of 22 September contradicted it
using `git show`, which applies EOL conversion and cannot be used to measure a
blob. `git cat-file blob` can.

### Proof the fix works

A build from a clean checkout now reproduces what `main` already carries, name
for name and byte for byte:

```
emitted                              committed on main
web/assets/logo-deep-Cc-XAy_2.svg    web/assets/logo-deep-Cc-XAy_2.svg
web/assets/logo-white-BjJcKX-d.svg   web/assets/logo-white-BjJcKX-d.svg
web/assets/index-DhQ35KU1.css        web/assets/index-DhQ35KU1.css
web/assets/index-XhtGmyUp.js         web/assets/index-XhtGmyUp.js
```

`git status` after the rebuild: clean. The whole branch against `main` is
`.gitattributes`, 11 insertions, 0 deletions. **The renames this document was
written about cannot happen again on a checkout that honours the attributes.**

### SUPERSEDED · Cause 1 is closed

> ```
>                  c:\terraform\arqedia   fresh worktree
> proposer                            1                0
> composition                         1                0
> normalizer                          1                0
> ```

and

> `normalizer` is untouched and still drifts.

Neither holds. Counted 23 September across every directory under
`c:\terraform\arqedia\lambda\`: **0 CRLF `.py` files.** `normalizer` included.

### SUPERSEDED · Cause 2 is closed

> **It is still present in `c:\terraform\arqedia\lambda\render\` and is still
> git-ignored**, so the next apply from that working copy puts it back into
> the function.

`lambda/render/` now holds `app.py` and `style.py` and nothing else.
`sample.pdf` is gone from the working copy as well as from the deployed
bundle. Cause 2 is closed at both ends.

### SUPERSEDED · a fifth cause: a stale copied `build/layer-docprocessing.zip`

> `aws_lambda_layer_version.docprocessing` does **not** drift. It refreshes at
> version 39 and stays out of every change set

That control no longer holds, and the reason is the copying this document
recommends. The layer is read by filename and hash from a git-ignored zip, so
a worktree's copy is a snapshot of whenever it was copied:

```
deployed layer version 41, created 2026-09-22T20:29:08Z
build/layer-docprocessing.zip in this worktree, copied 2026-09-20 07:30
its sha256                     Lokj4sbXl4E20E+qJLKmoXb6epCTzsfiKbjE8eOpeTk=
```

A plan run here on 22 September read:

```
# aws_lambda_layer_version.docprocessing must be replaced
~ source_code_hash = "jNJUbq3M6+WZU0JxQU2yJZKRJ+T4HUUROps3SGP47bc="
                  -> "Lokj4sbXl4E20E+qJLKmoXb6epCTzsfiKbjE8eOpeTk="  # forces replacement
```

That second value is this worktree's two-day-old copy. **An apply from here
would have rolled the layer back to the 20 September build**, publishing a new
version over a newer one, silently, from a file nobody edited. It is the same
shape as every other cause in this document - a git-ignored input that a
worktree carries and nobody compares - and it is the most dangerous, because
`filebase64sha256` gives no hint that the zip is old.

Nothing in the standing checks catches it. A worktree that has copied the zip
must re-copy or re-build it before any plan, or not plan at all.

### One thing the new rules still do not cover: `*.js`

`web/assets/index-*.js` is stored LF and is not matched by `*.svg`, `*.css` or
`*.html`, so `core.autocrlf` still smudges it to CRLF on checkout. It does not
produce a rename - vite writes the bundle itself and hashes what it wrote - so
it is not the defect above. What it does mean is that a checkout that is never
rebuilt has a CRLF bundle on disk, and `deploy-frontend.yml` syncs the disk.
**Recorded, not fixed:** adding `*.js` was outside what this branch was asked
to change.
