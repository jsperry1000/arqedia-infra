# ARQEDIA handoff — 19 September 2026

## Signup is invite-only, temporarily

Signup was open to anyone. The checks in `lambda/signup/app.py` were about
abuse volume and duplication - a disposable-domain list, one trial per email
domain, two rate limits - and none of them asked who somebody was. With SES in
production and the pricing page live, anyone with a real mailbox on an
unclaimed domain could take a tenant, a fourteen-day trial and $5.00 of
metered credit. Migration `027_signup_allow.sql` adds a `signup_allow` table
and `_checks()` refuses any address not in it with `not_invited`; `verify()`
checks again, because a `pending_signup` row lives fifteen minutes and could
otherwise be redeemed after an address was removed. It **fails shut** - an
empty table refuses everyone, which is why the four addresses are seeded in
the same migration - and **grants nothing by domain**: there is no domain
column, because one entry would admit a whole firm, which is the thing being
closed. An allowlisted address is **past the one-trial-per-domain rule**,
since the allowlist is already an individual decision and a second decision by
domain would overrule it; the disposable list and both rate limits still
apply, because an invitation is not a licence to hammer the endpoint. Two of
the four seeded addresses are at domains already claimed (gmail.com by tenant
0, ebl-finance.com by tenant 5), so `verify()` now **looks before it writes**
the claim: present, it logs `[claim-held]` and writes nothing; absent, it
inserts as before. Not `INSERT IGNORE` - MySQL's manual says IGNORE adjusts
invalid values "to the closest values" and inserts them, so it would have
silently written a truncated domain rather than failing. **The Cognito pool
needed no change**: `AllowAdminCreateUserOnly` is already true and
`LambdaConfig` is empty, so the public `SignUp` API is refused and the
allowlist cannot be walked around. This is a temporary gate, not a product
decision about who may buy.

---

## Open items

- **A tenant at an already-claimed domain has no `home_domain`.** Accepted
  deliberately. `verify()` leaves the existing claim alone, so the new tenant
  has no `tenant_domain` row, and `lambda/api/seats.py:141` reads that table
  for `home_domain`. With none, **nobody on that tenant's Seats screen is
  marked as outside the firm's domain** - the marking that exists for outside
  counsel and consultants. It is not a control: outside addresses are allowed
  and merely marked. Two of the four seeded addresses will land here.

- **Tenant 4 (`jspgmail`) is an orphan.** Created 2026-09-16 14:24:44 with
  `signup_ip 68.194.186.38` and a **live trial to 2026-10-16**. It has **no
  Cognito user, no seat row and no domain claim**. Residue of the signup that
  produced tenant 0's user - `jonathanscottperry+t1@gmail.com` carries
  `custom:tenant_id = 0`, not 4, and is disabled. Nobody can reach it and it
  is consuming a trial.

- **Tenant 0 has two Cognito users and no seat rows.** `admin@arqedia.com`
  (the curator) and the disabled `+t1` account both carry
  `custom:tenant_id = 0`, but `seat` holds nothing for tenant 0. The seats
  screen therefore counts nobody there, and the last-administrator rule has
  nobody to protect. Tenant 0 also holds the **`gmail.com` domain claim**,
  which blocks every gmail address from signing up.

- **No `X-Robots-Tag` header on `app.arqedia.com`.** Confirmed by
  `curl -sI`: the only directive is `<meta name="robots" content="noindex,
  nofollow">` in the HTML. That is enough for a crawler that renders the page
  and nothing at all for one that does not. **`/robots.txt` returns 200 with
  the SPA's `index.html`**, because of CloudFront's catch-all rewrite, so a
  crawler asking for directives gets HTML. The CloudFront change to add the
  header is pending.
