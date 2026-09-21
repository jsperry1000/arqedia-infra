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
