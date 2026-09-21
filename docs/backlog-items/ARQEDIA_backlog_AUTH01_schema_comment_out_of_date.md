# AUTH-01 — `auth.tf`'s schema comment describes a provider that has moved

**Raised 21 September 2026**, building the staff pool in Group 16 stage 1.
Not a defect in the stack. A comment that states a reason which is no longer
the reason, on the one lifecycle block standing between an edit and the loss
of every user in the pool.

---

## What it says

`auth.tf:145-150`, above `lifecycle { ignore_changes = [schema] }`:

> The provider has treated a schema change as forcing replacement since 2018,
> and reports remain open. Replacing this pool would destroy every user and
> every password in it.

## What the pinned provider does

`hashicorp/aws` is pinned at `6.61.0` in `.terraform.lock.hcl`. In that
version's `internal/service/cognitoidp/user_pool.go`, three fields carry
`ForceNew: true` and `schema` is not among them:

```
alias_attributes
username_attributes
username_configuration.case_sensitive
```

A modification or removal inside `schema` is refused at update time instead,
with `cannot modify or remove schema items`; an addition is applied through
the `AddCustomAttributes` API. `Schema` is not a parameter of `UpdateUserPool`
at all, which is why neither path is an in-place edit.

## Why the block is still right

A failed apply in the middle of a run is no better than a replacement, and
the safe route is unchanged: add the attribute to the live pool with
`AddCustomAttributes`, then bring the file into line. `ignore_changes =
[schema]` is what stops an edit to the file becoming either outcome.
`admin_auth.tf` carries the same block from its first line, for the same
reason.

## Why it matters that the words are wrong

The comment is the only record of why the block is there. Somebody reading
"forces replacement", checking the current provider, and finding no
`ForceNew` may conclude the block is obsolete and delete it. The behaviour it
guards against did not go away; only the mechanism did.

## Done when

- `auth.tf`'s comment states the current behaviour, naming the version it was
  checked against and the date.
- `admin_auth.tf`'s equivalent comment says the same thing.
- Both say what to do instead, which neither currently does in one place.

Not done here because `auth.tf` belongs to the customer path and Group 16
stage 1 was to touch nothing that exists.
