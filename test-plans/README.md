# Test plans — the CRNs a candidate is scored on

The house in `example/` is fully revealed, framing and all. It teaches the task.
**These** are the plans a candidate runs their code against, and they ship without their
framing sheets.

```
test-plans/
  CRN574114/   Mrs. Parvathi — 649 SF — skewed plot, corners 91°/88°/87°/93°
  CRN642050/   Ms. Sapna     — 744 SF — plot ~40'×70'-3", building fills only part of it
  CRN716485/   Mr. Sachin    — 877 SF — structure annotated on the plan; a column stops below
    first_floor_plan.pdf     ← the input, one page
    notes.md                 ← what is awkward about this house
```

Between them these three break the three laziest shortcuts: "assume a rectangle", "take
the bounding box of the page", and "assume every column stacks".

The matching framing sheet for each CRN lives in `internal/<crn>/`, so the answer key
never travels with the question.

## Adding a CRN

1. Pull the architectural set and the structural set for the CRN.
2. Take the **first floor plan** page from the architectural PDF — one page, one floor —
   and save it as `test-plans/<crn>/first_floor_plan.pdf`.
3. Take the **ground floor roof framing** page from the structural set — that is the
   framing for the first floor — and file it as `internal/<crn>/framing.pdf`.
4. Build the side-by-side `internal/<crn>/plan_vs_framing.png` so the house reads the
   same way as the others.
5. Write `notes.md`: what is unusual, and what you expect it to break.

## What makes a good test set

Vary the shape, because that is what separates a real algorithm from one tuned to a
single house: a plain rectangle; an L or a step in plan; a large balcony or cantilever; a
lift shaft or stair void; a plan whose room labels are incomplete so scale must come from
the dimension chain.

Vector PDFs please. A scan turns this into an OCR exercise, which is a different
assignment.
