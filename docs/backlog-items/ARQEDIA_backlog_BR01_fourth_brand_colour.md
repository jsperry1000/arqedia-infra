# BR-01 · A tenant's palette is three colours and the page needs four

| | |
|---|---|
| Status | Not built |
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
