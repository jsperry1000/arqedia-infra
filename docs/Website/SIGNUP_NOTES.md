# Branch `signup` — read before applying

Four new files, one edited, one migration. Read §1 first: **SES production
access is not granted, and without it no code can be sent.**

| File | |
|---|---|
| `db/migrations/014_signup.sql` | New. Four columns on `tenant`, three new tables |
| `lambda/signup/app.py` | New. The handler |
| `signup.tf` | New. Role, function, integration, two unauthenticated routes |
| `api.tf` | Edited. CORS only — one block, nothing else touched |

---

## 1. BLOCKER — SES

`POST /signup` sends a six-figure code by email. Nothing works without it.

Two things are needed and neither is done:

- **SES production access**, in `us-east-2`. It is on the procurement list in
  the 29 August handoff and has never been requested. Days, not hours, and it
  is per region.
- **A verified sender.** `signup.tf` defaults to `no-reply@arqedia.com`. That
  address needs DKIM records in the Route 53 zone, which now exists, and the
  identity verified.

Until both, `/signup` will reach the SES call and fail. The handler is correct;
it has nothing to send through.

**Request SES access before applying this branch.** Everything else can be
applied and tested in the meantime, because the failure is at the last step and
creates nothing.

---

## 2. Why signup is a separate function

The user pool stays **admin-create-only**. That is deliberate and should not be
changed.

If Cognito accepted registrations directly, anyone could call it and skip every
control in this handler — the domain rule, the disposable list, the rate limit.
They would get a Cognito account carrying no tenant, which signs in to an
application that cannot answer a single request about it. There is one door and
the controls are on it.

The second reason is permissions. This function holds
`AdminCreateUser`, `AdminSetUserPassword`, `AdminGetUser` and
`AdminDeleteUser`. The API holds none of them and must not — a defect in any of
its fifty routes would otherwise be a defect that can create users.

---

## 3. The order of creation, and why

Tenant row, then `tenant_domain`, then the Cognito user, then the password.

If anything after the tenant row fails, the handler deletes the row, the domain
claim and any user it made, and returns a 500 saying nothing was kept.

The reverse order would leave a Cognito account with no tenant. That person can
sign in, reaches an application which cannot answer a single request about
them, and nothing from outside says anything is wrong.

**The password is never stored.** The browser holds what the person typed and
sends it with the code at the verify step. `pending_signup` has no password
column and there is nothing in that table worth stealing.

---

## 4. The controls, in the order the handler runs them

| | Control | Where |
|---|---|---|
| 1 | Disposable domain | A set in the handler |
| 2 | One trial per email domain | `tenant_domain`, with `multi_allowed` as the lift |
| 3 | Rate limit per domain, 3/hour | `signup_attempt` |
| 4 | Rate limit per IP, 5/hour | `signup_attempt` |
| 5 | Address already registered | `AdminGetUser` |

Cheapest first. The domain rule does most of the work; the rate limits stop a
script rather than a person.

**The domain rule is checked twice** — once at `/signup` and again at
`/signup/verify`. Two people at one firm can reach the second step together,
and the first to arrive takes the tenant.

**A second person from a firm that already has a tenant is not turned away.**
They are told to ask an administrator there for a seat, which is what they
wanted. That is better product as well as a better control.

---

## 5. The IP address

Recorded on `signup_attempt` and on `tenant`. **Never used to decide anything
except a rate limit.**

Blocking on an address fails in both directions: a VPN defeats it in seconds,
while a shared office connection blocks strangers with nothing to do with each
other. It is kept so that when an abuse flag fires a person can see nine
attempts came from one connection.

**It is personal data in the EU and the UK.** It needs a lawful basis stated in
the privacy policy and a retention limit — ninety days is the usual answer.
There is no retention job yet. Recorded in ONB-01 and in the migration itself.

The email address on a failed attempt is stored as a sha256 hash, not as an
address. Rate limiting needs to know the same address tried twice; it does not
need to know who they are. A failed attempt is not a customer and we should not
hold a list of people who did not sign up.

---

## 6. What this does not do

**It does not fork the pack.** The chosen pack is recorded on
`tenant.forked_pack` and the fork happens at first run, where a person can see
what they are getting. Doing it here would need `pack.py` and `registry.py`,
which I have not read, and I will not call functions I have not read.

**It does not invite the second administrator.** The address is captured and
recorded on `pending_signup`; sending the invitation needs the seat model,
which is not built.

**It does not open a wallet bucket.** `trial_ends_at` is set on the tenant. The
$5.00 trial credit needs the wallet tables, which do not exist.

All three are follow-ups, and none of them blocks a person getting in.

---

## 7. `api.tf` — one change, and a bug it fixes

CORS listed only the CloudFront hostname and localhost. Since `app.arqedia.com`
was added, a browser on that name has been making cross-origin calls the
gateway refuses.

**Check whether the live app works on its own domain today**, because it may
have been broken since the DNS branch merged:

```powershell
$h = @{ Origin = "https://app.arqedia.com" }
Invoke-WebRequest -Method Options -Uri "https://o4fofn0ez5.execute-api.us-east-2.amazonaws.com/engagements" -Headers $h |
  Select-Object -ExpandProperty Headers
```

Look for `access-control-allow-origin`. Absent means it is broken and this
change fixes it.

`arqedia.com` is in the list for signup only.

---

## 8. Order to apply

1. **Request SES production access in us-east-2**, and verify
   `no-reply@arqedia.com`. Do this first; everything else can proceed while it
   is pending.
2. **Apply the migration.** Additive; the two hand-made tenants stay valid.
   ```powershell
   .\db\migrate.ps1
   ```
3. **Verify by querying, not by the absence of an error.**
   ```powershell
   $sql = "SHOW CREATE TABLE tenant_domain"
   aws rds-data execute-statement --profile arqedia --resource-arn $cluster --secret-arn $secret --database arqedia --sql $sql --output json
   ```
4. **Claim the domains the two existing tenants already hold**, or the first
   person at either firm will be offered a trial:
   ```sql
   INSERT INTO tenant_domain (domain, tenant_id) VALUES ('vmac.com', 1);
   ```
   `gmail.com` for tenant 2 is a test artefact — do **not** claim it, or no
   Gmail address could ever sign up.
5. **Parse the handler before deploying.**
   ```powershell
   python -c "import ast,io; ast.parse(io.open('lambda/signup/app.py', encoding='utf-8').read()); print('parses')"
   ```
6. **Apply.** Expect one function, one role, one policy, one integration, two
   routes, one permission added, and `aws_apigatewayv2_api.main` changed in
   place for CORS.
   ```powershell
   terraform apply
   ```
7. **Read the log, not the screen**, on the first attempt:
   ```powershell
   aws logs tail /aws/lambda/arqedia-dev-signup --profile arqedia --region us-east-2 --since 10m --format short
   ```

---

## 9. Still to do before a person can actually get in

- SES, §1.
- The front end wired to these two routes. `SignUp.tsx` is inert and its
  header says so.
- `ui/src/api.ts` needs two unauthenticated calls, which do not use
  `authHeaders`.

---

## 10. Open

1. **Disposable-domain list.** Sixteen entries held in the handler. A
   maintained list or a third-party service is better. Web-search the options
   rather than assuming — a stale list is worse than none, because it reads as
   working.
2. **Retention job** for `signup_attempt.ip`.
3. **Vetting position**, `frontend_onboarding_spec_v1.md` §11, still
   unanswered: self-serve sanctions tooling at $25 with no check on the buyer.
