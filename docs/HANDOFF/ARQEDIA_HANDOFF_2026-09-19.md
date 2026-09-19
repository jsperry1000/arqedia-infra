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

## Free-mail domains are never claimed

A `tenant_domain` row means "this domain's workspace", and `gmail.com` is not
a workspace. Before this, the first person to sign up from a free-mail address
would have claimed it for their own tenant, after which every later address at
that domain would have been told to ask an administrator there for a seat - an
administrator who is a stranger to them. `verify()` now skips the claim for a
fixed set held as `FREE_MAIL` in `lambda/signup/app.py`: **gmail.com,
googlemail.com, outlook.com, hotmail.com, live.com, yahoo.com, icloud.com,
me.com, aol.com, proton.me, protonmail.com**. It is skipped the same way a
domain somebody already holds is skipped, and it is **not a refusal** - the
tenant, the seat, the trial and the credit are created exactly as before. The
list is deliberately short, by the same argument as `DISPOSABLE`: a stale list
is worse than none, because it reads as working. **It is to be extended when
signup opens to the public**, which is when addresses outside it start
arriving. Deployed 19 September 2026, CodeSha256
`F58XoiEzOIhPNEnIQttu5pSagN4qALNvYByHNmk1ub8=`.

## The 16 September `LAST_INSERT_ID` incident, and its cleanup

One bug explained three separately-reported open items. On 16 September at
14:24:44 a signup created tenant 4 (`jspgmail`) and then lost its own id: the
Data API's `LAST_INSERT_ID()` returned 0, so everything after the `tenant`
insert was written against tenant **0** or not at all. It left a `gmail.com ->
tenant 0` domain claim **thirty hours before tenant 0's row existed** (tenant 0
was created 17 September 21:00:52), a Cognito user
`jonathanscottperry+t1@gmail.com` carrying `custom:tenant_id = 0` rather than
4, and tenant 4 itself with `active_revision` and `forked_pack` both NULL, no
user, no seat, no claim and a live trial to 16 October. The bogus claim was
blocking every gmail address at signup, which is what made it look like three
faults instead of one. **`arqedia.com` was never claimed by anybody** - that
was an assumption, not a row. Cleaned up on 19 September, dev data, no record
kept beyond this paragraph: the claim deleted (1 row), the disabled `+t1` user
deleted, and tenant 4 removed after a read-only inventory found it held
**exactly one row in the whole database** - its own - and **zero objects** under
`tenants/4/` in all seven buckets. `tenant` went 6 rows to 5; the remaining ids
are 0, 1, 2, 5, 9. The gaps in that sequence (3, 6, 7, 8) are auto-increment
values consumed by signups that failed the same way or were removed by hand.

---

## Open items

- **Tenants 1 and 2 hold no domain claim, and that is correct.**
  `tenant_domain` was created by `014_signup.sql` on 15 September; TESTCO A and
  TESTCO B were made by hand on 26 and 28 August, seventeen days earlier, and
  nothing backfills. `vmac.com -> 1` was inserted by hand two minutes after
  that migration ran; nobody did the same for tenant 2, whose users are at
  gmail.com and now never could be claimed. The only consequence is that
  `_home_domain()` returns null for them, so nobody on those Seats screens is
  marked as outside the firm - which `lambda/api/seats.py:132` anticipates in
  its own docstring. **It has nothing to do with signing in**: the tenant comes
  from `custom:tenant_id` on the Cognito user, and no authentication path reads
  this table.

- **A tenant at an already-claimed domain has no `home_domain`.** Accepted
  deliberately. `verify()` leaves the existing claim alone, so the new tenant
  has no `tenant_domain` row, and `lambda/api/seats.py:141` reads that table
  for `home_domain`. With none, **nobody on that tenant's Seats screen is
  marked as outside the firm's domain** - the marking that exists for outside
  counsel and consultants. It is not a control: outside addresses are allowed
  and merely marked. Two of the four seeded addresses will land here.

- **CLOSED 19 September: tenant 4, the `+t1` user and the `gmail.com` claim.**
  All three were one bug. See the incident above.

- **Tenant 0 has no seat rows.** `admin@arqedia.com` (the curator) carries
  `custom:tenant_id = 0` and is now the only user that does, but `seat` holds
  nothing for tenant 0. The seats screen counts nobody there, and the
  last-administrator rule has nobody to protect. Unchanged by the cleanup:
  removing the `+t1` user took away a second user, not a seat that never
  existed.

- **There is no account-deletion path in the code.** Removing tenant 4 was
  done by hand, statement by statement, because there is nothing to call. It
  is specified - `wallet_entitlement_spec_v1.md:266` says deletion "scrubs
  tenant rows, storage prefix, derived artifacts, and revokes every
  outstanding share grant", and `build_index.md:116` calls it "the only
  destructive action" - and it is not built. The known gap that it would
  forget `tenant_domain` (CLAUDE.md) is why step one of the cleanup was a
  manual `DELETE` too.

- **No `X-Robots-Tag` header on `app.arqedia.com`.** Confirmed by
  `curl -sI`: the only directive is `<meta name="robots" content="noindex,
  nofollow">` in the HTML. That is enough for a crawler that renders the page
  and nothing at all for one that does not. **`/robots.txt` returns 200 with
  the SPA's `index.html`**, because of CloudFront's catch-all rewrite, so a
  crawler asking for directives gets HTML. The CloudFront change to add the
  header is pending.
