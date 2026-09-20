# BR-01 · A tenant's palette is three colours and the page needs four

| | |
|---|---|
| Status | Closed on branch `ux-branding`, 20 September 2026 |
| Priority | Medium. Cosmetic, but it is the tenant's own brand |
| Type | Migration, Settings, render |

---

## What is wrong

`tenant` holds `brand_deep`, `brand_mid` and `brand_highlight`. The rendered
memorandum now uses four weights:

| | |
|---|---|
| Section heading | deep band, reversed out |
| Sub-heading | mid band, reversed out |
| Fourth-level heading | a pill, wants a **light** tint |
| Table header rule | highlight |

The pill takes the mid for now, which is darker than it should be and gives a
fourth-level heading more weight than the sub-heading above it. A tenant cannot
choose it because there is nowhere to put it.

---

## What is needed

1. A migration adding `brand_light` to `tenant`, nullable with no default, so
   every existing row stays valid.
2. `style.palette_for` reading a fourth key, falling back per colour as the
   other three already do — a tenant setting only its deep colour still gets a
   coherent page.
3. The Settings screen offering a fourth swatch beside the three.
4. The pill taking `light` instead of `mid`.

---

## The fallback, if no light is set

Mix the tenant's mid towards white. A tenant who sets three colours and never
opens Settings again still gets a pill that reads as the palest member of its
own palette rather than a colour from ours.

---

## Not in scope

The three existing colours, which are working. This adds one, and nothing that
uses the existing three changes.

---

## What was already built, and when (added 20 September 2026)

Three of the four items above were built between 13 and 16 September and this
item was never updated, so it read "Not built" while most of it was live. What
was found on `main` at `f465025`:

| Item | State | Where |
|---|---|---|
| 1. Migration | Built and applied to **dev only** | `db/migrations/013_tenant_brand_light.sql`; `schema_migration` holds the row, `SHOW COLUMNS FROM tenant LIKE 'brand%'` returns `brand_light varchar(9) YES` |
| 2. `palette_for` reads a fourth key | Built, including the mix | `lambda/render/style.py:68-105`, `LIGHT_MIX = 0.7` |
| 3. Settings offers a fourth swatch | Built | `ui/src/Settings.tsx:24`, `lambda/api/app.py` both ways |
| 4. The pill takes `light` | **Not built** — it took `mid` | `lambda/render/app.py:651` |

So the fourth colour could be set, was stored, was resolved on every render -
and was then used by nothing. `grep 'palette\["light"\]' lambda/` returned
nothing. The Settings screen named the pill as the thing Light sets, which was
not true of any memorandum rendered before today.

## What this branch closes

- The pill takes `palette["light"]`, and its text is set in the deep. White on
  a pale tint is not readable, and the two heading levels above it are already
  white on something dark.
- `PREVIEW_MARKDOWN` gains a fourth-level heading. Without one, the only
  colour a tenant can choose was the only one Render a sample never showed.
- Six tests on `palette_for` and one on the pill's style, in
  `tests/test_palette.py`. There were none: the palette was the untested part
  of the renderer, which is how item 4 sat undone through four applies.

## Still open after this branch

- **Migration 013 is on dev only.** There is no prod stack yet; when there is,
  it has to carry 013 or every render there raises on a column that is not
  there. Recorded in ENV-01 as well.
- **The fallback mixes from the MID.** Where a tenant's mid has nothing to do
  with its deep - aubergine deep, blue mid - the pill is a pale blue on a page
  that is otherwise aubergine and gold. It is correct by the rule written
  here, and it looks like a foreign colour. Mixing from the deep instead is a
  decision, not a fix, so it is left as one. See `build/samples/` on branch
  `ux-branding`.
- **No tenant has set a colour.** `SELECT ... FROM tenant` returns NULL in all
  four columns for all five rows on dev, so nothing above is confirmed against
  a tenant's real palette - only against samples rendered by hand.
