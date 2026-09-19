# ARQEDIA — Code prompt

## COMP-01 · Composition: Bedrock client timeout, and a log line per model call

Working directory `c:\terraform\arqedia`. Branch `comp01-bedrock-timeout-logging`
from an up-to-date `main`.

Apply the Rules of Engagement in `CLAUDE.md` throughout.

---

### Why

On 18 September a memo on tenant 1, template `credit-memorandum-2`, timed out at
600 seconds and was retried by Lambda. Eleven sections consolidated in about five
minutes. The twelfth, `industry-market-overview`, then produced nothing for five
minutes until the timeout. No memo row was written.

`_bedrock` (line 52) is created with no `Config`. Public reports give botocore's
defaults as a 60-second read timeout and legacy retries of up to 5 attempts, each
one re-sending and re-billing the model call. Two sections in the same run already
took about 50 seconds. This is the likely mechanism, but it is unverified: the
Lambda died before any error was logged.

The code logs nothing about a model call except dropped citations. That is why
the cause could not be read from the log.

---

### Decisions (do not reopen)

- **D1** Bedrock client: `read_timeout=300`, `retries={"mode": "standard", "max_attempts": 2}`.
- **D2** One client for generation and rewrite. `_rewrite` gets the same config.
- **D3** One log line per model call, from draft, consolidate and rewrite, in this form:
  `[model-call] stage=<draft|consolidate|rewrite> section=<key or rewrite id> chars_in=<n> truncated=<yes|no> seconds=<s> tokens_in=<n> tokens_out=<n> hit_max=<yes|no> retries=<n>`
  - `chars_in` is the length **before** the 40,000-character slice.
  - `truncated` is `yes` when that length is over `_SECTION_INPUT_CHARS`.
  - `hit_max` is `yes` when `tokens_out >= _MAX_TOKENS`.
- **D4** No change to prompts, citations, section handling or what is written to
  the database. Logging and client configuration only.
- **D5** `lambda/composition/app.py` only. Nothing in `lambda/shared`.

---

### Part 1 · Read and report. Write nothing.

1. Read `lambda/composition/app.py` in full.
2. Confirm that the deployed file matches the one described here: `_bedrock` at
   line 52 with no config, `_invoke` at line 238, and the slices at lines 281 and 386.
3. Verify, against the installed botocore, whether `invoke_model`'s response carries
   `ResponseMetadata.RetryAttempts`. Report what you find. Do not assume it.
4. Report the exact diff you propose for D1 to D3.

**Stop and wait for approval.**

---

### Part 2 · Build, after approval

1. Make the change.
2. Parse-check: `python -c "import ast,io; ast.parse(io.open('lambda/composition/app.py', encoding='utf-8').read())"`
3. `terraform plan`. The summary must name `arqedia-dev-composition` and nothing
   else. If it says "No changes", stop.
4. `terraform apply -auto-approve`. No layer rebuild is needed; `lambda/shared` is untouched.
5. Commit, push, and give a short push summary.

---

### Part 3 · Verify

The user re-runs the memo for tenant 1, `credit-memorandum-2`, from the screen.
Then:

```powershell
aws logs tail /aws/lambda/arqedia-dev-composition --profile arqedia --region us-east-2 --since 15m --format short
```

Report every `[model-call]` line as a table, and whether `[composed]` printed.
Draw no conclusions beyond what the lines show.

---

### Not in scope, recorded

- **A failed call still fails the whole memo.** With D1, a call that exceeds 300
  seconds twice raises, and Lambda retries the entire memo twice. That behaviour is
  unchanged here.
- **The 600-second function limit** still caps the whole memo.
- **All sections are `kind = extract`** in every template, so stage 2 never runs.
  This is a separate item.
