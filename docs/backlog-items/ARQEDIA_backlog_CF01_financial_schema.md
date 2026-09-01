# ARQEDIA — Backlog Item

## CF-01 · The financial schema is twenty loose fields, not a table

| | |
|---|---|
| Status | Not fixed |
| Priority | High. The whole group is inert today |
| Type | Configuration, and possibly extraction |
| Raised | 31 August 2026 |

---

### Observation

The financial output schema holds twenty single fields — Gross Revenue, Cost
of Goods, Commissions, Gross Profit, Turnover, Total Assets, Total Equity,
Intercompany Payables and so on. Every one carries a description of the form
"3 years." or "3 years — with whom."

That is not a description of the field. It is shorthand for *give me three
years of this figure*, written by whoever built the eBL schema and perfectly
clear to them. On a screen headed "What it is" it reads as nonsense.

**And every one of the twenty is bound to no memo section.** They appear in
the validator's warnings as extracted and never rendered. The whole group is
inert: it costs extraction on every financial document filed and reaches no
reader.

### Why it is the wrong shape

A financial statement is a table. Line items down one axis, periods across the
other. Twenty fields each answering "three years of this" cannot hold that:

- Nothing binds a figure to its period. Three years of turnover arrive as one
  value, and which year is which is a matter of reading the prose back.
- Nothing binds a figure to its currency. A memo comparing a UGX figure with
  a USD one would not know.
- A line item the schema does not name has nowhere to go. A chart of accounts
  is not a fixed list, and a customer's is not eBL's.
- Adding a period means editing twenty descriptions.

The pack already solves this shape elsewhere: Persons, Suppliers, Buyers and
Financial Counterparties are group fields whose columns repeat as rows. The
financial group was written before that pattern existed, or by someone who did
not reach for it.

### What it should be

One table, something like:

| Line item | Period | Value | Currency | Basis |
|---|---|---|---|---|

with the line item taken from the source rather than from a fixed list, so a
customer's own chart of accounts survives contact with the product.

**It must be configurable.** A trade financier, a property lender and a fund
administrator do not want the same lines, and none of them wants eBL's. The
point of the registry is that they choose; this group should be the first
thing they can shape rather than the last.

### Open questions, for someone who knows the credit side

- Whether "line item" should be free text from the source, or chosen from a
  configurable list the tenant maintains — free text captures anything and
  compares badly; a list compares well and loses what it does not know.
- Whether period should be a column of the table or a repeated table per
  period. Column is simpler; a table per period reads better in a memo.
- Whether derived figures — margins, ratios, coverage — belong here at all,
  or are computed at composition from the values. Composition already computes
  nothing and states only what a source says, deliberately.

### Sequence

1. Decide the shape with a practitioner. This is the open item the handoff has
   carried since the design phase.
2. Author it as a table in the editor, which can already do this.
3. Bind it to the Financial Position section, which currently renders nothing.
4. Retire the twenty fields. Documents already filed keep resolving against
   the revision they were filed under.

### Notes

- Nothing here is broken. It is a design that predates the group-field
  pattern, and the cost is that a whole section of every memo says "no
  material addressing this section was provided" while financial documents sit
  extracted in the file.
- The descriptions being unreadable is a symptom, not the fault. Rewriting
  twenty descriptions would leave the shape wrong.
