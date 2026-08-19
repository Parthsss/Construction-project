# Assignment — Find the building boundary and the structural framing in a floor plan

**Role:** Software development intern
**Time box:** one working day.
**Tools:** anything. Python, notebooks, Excel, CAD software, ChatGPT / Claude / Copilot, pen and paper. We do not care which.

---

## 0. Read this first

You are given **architects' floor plans** of small houses. Your job is to write a program
(or a clearly described procedure) that reads a plan and works out **where the structural
skeleton goes** — the outline of the building, then the columns, then the beams.

**Scope: the layout grid only.** We want the geometry — the boundary, the column points,
and the beam lines joining them. You do **not** have to reproduce the engineer's drawing.
Dotted and dash-dot lines, grid bubbles, `A` `B` `C` / `1` `2` `3` labels, hatching,
dimension chains and title blocks are all **not required** in your output. A clean set of
lines in the right places is the whole deliverable.

Three things before you start:

1. **You are not expected to know anything about buildings.** Section 1 teaches you
   everything you need. If a word confuses you, check the glossary at the end.
2. **You are not expected to match the engineer's drawing exactly.** Read that again. We
   show you one house solved in full so you can see what the output looks like, but a
   100% match is not the goal and is not achievable in a day. **We evaluate your
   approach** — how you broke the problem down, what you noticed, how you handled the
   parts that are ambiguous, and how honestly you describe what your program gets wrong.
3. **Your program will be run on floor plans you have never seen.** Do not hardcode
   numbers from any single house.

A candidate who gets roughly 60% of the framing right with clear reasoning and an honest
list of failure cases will score **higher** than a candidate who matches 95% by tuning
constants until the picture looked right.

---

## 1. Crash course — everything you need to know about buildings

### 1.1 What a floor plan is

Imagine slicing the house horizontally about four feet above the floor, lifting the top
half away, and looking straight down at what is left. That is a floor plan.

- **Walls** appear as thick bands (a wall is ~4"–9" thick, so it is drawn as two parallel lines).
- **Rooms** are the empty areas between walls, labelled with a name and a size — `BEDROOM 10' - 0" X 10' - 10"`.
- **Doors** are gaps in walls, usually with a quarter-circle arc showing the swing.
- **Windows** are thinner gaps, drawn as parallel lines.
- **Staircase** is the ladder-like set of parallel lines, with steps numbered and `UP` / `DN` arrows.
- A **dash-dot line** running outside the walls is usually the **plot** — the land, not the building.

### 1.2 Reading the dimensions

Indian residential drawings use **feet and inches**. `10' - 6"` means 10 feet 6 inches.
12 inches = 1 foot, so that is 10.5 feet. You will also see `9"` and `31'-8"`.

Dimensions are written in **chains** along the outside edges: a row of numbers where each
measures the gap between two consecutive lines, adding up to the total width or depth.
This is your best friend — it converts "points on a page" into "real feet".

### 1.3 How a house stands up

A concrete house has four structural pieces, and load travels one way through them:

```
        people, furniture, walls
                  │
                  ▼
   SLAB    the flat concrete floor plate you walk on (typically 6" thick)
                  │
                  ▼
   BEAM    concrete ribs under the slab edges, spanning between columns
                  │
                  ▼
   COLUMN  vertical concrete posts, normally running the full height of the house
                  │
                  ▼
   FOOTING a concrete pad in the ground that spreads the load onto the soil
```

The slab cannot span forever without sagging, so it is broken into rectangular **panels**,
each edged by beams. The beams cannot span forever either, so they land on columns.
Columns normally line up vertically floor to floor — though not always, and one of the
test plans will show you an exception.

### 1.4 What "framing" means

**Framing** is the plan-view arrangement of columns and beams at one floor level: where
each column sits, and which columns each beam connects. That is what you must produce.

### 1.5 One naming trap

The engineer's sheet is titled **"Ground Floor Roof"**, but the input plan is the **First
Floor Plan**. These are the same level. The concrete slab that forms the *roof of the
ground floor* is the *floor of the first floor*.

> **First floor plan** (architect's view of the rooms) ⟷ **Ground floor roof framing** (engineer's view of the beams holding that floor up)

### 1.6 Grid lines

Engineers overlay a reference grid: vertical lines lettered **A, B, C…** and horizontal
lines numbered **1, 2, 3…**. Every column sits on a grid intersection, so a column can be
described as "the column at C-3". Grid lines run through column centres, and the chain
dimensions are measured between them.

This is background, so the reference sheets make sense to you. **You do not have to
produce those letters and numbers.** Knowing that columns line up into rows and columns is
useful; naming the rows is not part of the job.

### 1.7 The boundary — your first task

The **boundary** is the outline of the built area at this floor level. It sounds obvious
and is not:

- The **plot** boundary (the land) is bigger than the building — often much bigger.
- The outer face of the outer walls is the usual answer.
- A **balcony** or **chajja** sticks out past the main walls.
- A **lift shaft**, **utility** or **staircase** may be enclosed or open.
- The outline is rarely a plain rectangle. It steps, and the plot corners are not always 90°.

You must decide what "the boundary" means, state your definition in your README, and be
consistent.

---

## 2. What is in this folder

```
ASSIGNMENT.md          ← this file
example/               ← one house, solved in full — study this first
test-plans/            ← the plans your code must run on
```

### 2.1 The worked example

Open **`example/plan_vs_framing.png`**. It shows one real house twice:

- **left** — the architect's first floor plan
- **right** — the framing an engineer produced for that same floor

That pair *is* the assignment, stated as a picture. Study it until the correspondence
makes sense: where the column blocks sit relative to the walls, how beams run column to
column, how the floor ends up divided into rectangular slab panels.

`example/` also holds the full sheets behind that picture:

| File | What it is |
|---|---|
| `first_floor_plan.pdf` | The architectural sheet, untouched |
| `framing.pdf` | The framing sheet — the answer for this house |
| `foundation_and_columns.pdf` | Where every column landed, plus the grid and footing schedule |
| `beam_schedule_no_dimensions.pdf` | Every beam that exists and its size. We erased the dimension numbers on purpose — beam marks and `[8"x18"]` sizes are intact |

For that house: 958 SF, envelope about 31'-8" × 40'-4", grid A–F / 1–6, **14 columns** all
8"×18", **18 beams** (B1–B19 with B17 unused) all 8"×18" except two at 8"×6", slab 6" thick.

### 2.2 The plans you are scored on

`test-plans/` holds three houses. Each folder has one **`first_floor_plan.pdf`** — a
single page, ready to run your code against — and a `notes.md` describing what is
awkward about it.

| CRN | Client | First floor | What it will break |
|---|---|---|---|
| `CRN574114` | Mrs. Parvathi | 649 SF | The plot is skewed — corners 91° / 88° / 87° / 93°, sides 40'-1" vs 39'-6". Not a rectangle. |
| `CRN642050` | Ms. Sapna | 744 SF | The plot is about 40' × 70'-3" but the building fills only part of it. The outermost shape on the page is **not** your boundary. |
| `CRN716485` | Mr. Sachin | 877 SF + 110 SF balcony | The architect annotated structure onto the plan (`CONCEALED BEAM`, `CHAJJA PROJECTION`) — and one note says a column *stops* at the floor below, so columns do not all stack. |

**You do not get the framing sheets for these three.** That is the point. Run your code
on all three and submit the output for each.

Each plan is a vector PDF: lines and text carry real coordinates, so you are not forced
into computer vision. Work in **feet**, and derive the scale from the drawing rather than
typing in a constant.

---

## 3. The task, in stages

Work in this order. If you run out of time, a solid Stage 1 and 2 with an honest write-up
beats five half-finished stages. Stage 5 is not optional at any level of completeness —
whatever you hand in, be ready to explain how it was produced.

### Stage 0 — Get the geometry out of the PDF

Libraries such as **PyMuPDF (`fitz`)**, **pdfplumber** or **pdfminer** give you line
segments and text with positions. Rendering to an image and using OpenCV is also allowed.

You need:
- line segments in page coordinates,
- text strings with their positions (room names, dimensions),
- a **scale factor** — how many page units equal one real foot. Derive it from the
  dimension chain or the room-size labels; do not guess.

### Stage 1 — Find the boundary  *(the core of this assignment)*

Produce the outline of the floor as a closed polygon in **real feet**.

Think about:
- Walls are drawn as *pairs* of lines. Outer face, inner face, or centreline? Say which and why.
- Which line is the plot and which is the building. Two of the three test plans punish getting this wrong.
- Is the balcony inside your boundary? Justify it.
- How do you tell an exterior wall from an interior partition?
- How do you avoid picking up the title block, the door/window schedules, the notes and the north arrow, which are lines on the same page?

Output: an ordered list of `(x, y)` corners in feet, plus the enclosed area. Every plan
states its built-up area in the area statement — compare yours against it. Free self-check.

### Stage 2 — Place the columns

Propose a column position everywhere you think one is needed.

Reasonable starting logic — disagree if you like, but say so:
- Every corner of the boundary polygon wants a column.
- Junctions where an internal wall meets an external wall want a column.
- Columns should line up into rows and columns, forming a grid.
- If the gap between two adjacent columns is very large (say more than ~15 feet), add an intermediate one.
- Columns normally stack floor to floor.

Output: a list of column positions in feet. **No grid labels needed** — an unnamed point
in the right place is a full answer. If your method happens to group columns into rows and
columns internally, that is fine, but we are not marking the naming.

### Stage 3 — Place the beams (the framing)

Connect columns with beams so every slab region is bounded on all sides.

Reasonable starting logic:
- A beam is a straight line between two columns.
- Beams prefer to sit under walls, so the wall above is carried.
- Beams run along the grid lines, most of them fully horizontal or fully vertical.
- The result should divide the floor into closed rectangular panels with no unsupported gaps.
- Openings — lift shaft, stair void, skylight — need beams around them, because there is no slab there to span.

Output: a list of beams, each referencing the two columns it connects, with length in feet.

**All beams as plain solid lines.** On a real sheet some beams are drawn dashed or
dash-dot (concealed beams, beams below, the plot edge). You do not need to distinguish
them or draw them that way — one line style throughout is fine.

### Stage 4 — Show your result

Produce a **drawing of your layout grid** for every test plan — the boundary, the column
points and the beam lines. Anything a human can open is acceptable:

- an **HTML / SVG page you open in a browser** (this is often the easiest to build and the
  easiest for us to read),
- a **PDF**,
- or a plain image (PNG) if you prefer.

Draw it over the original plan or beside it — either is fine. Solid lines throughout. No
grid letters, no dimension chains, no title block.

A **machine-readable file alongside it is welcome but optional** — JSON or CSV, whatever
your code already has in memory. If you produce one, something like this is plenty:

```json
{
  "crn": "CRN574114",
  "units": "feet",
  "scale_source": "dimension chain along the top edge",
  "boundary": [[0,0], [25.08,0], [25.08,40.08], [0,40.08]],
  "boundary_area_sqft": 649.0,
  "columns": [{"x": 0.0, "y": 0.0}],
  "beams":   [{"from": 0, "to": 1, "length_ft": 7.42}],
  "assumptions": ["boundary taken at outer face of external wall"],
  "known_problems": ["balcony edge not detected — see README"]
}
```

### Stage 5 — Be able to walk us through it

This one is not optional, and it carries real weight.

**You must be able to explain every step, and point at the code that produced it.** In the
debrief we will pick a line on your output and ask: which function drew that, what did it
consume, and why did it decide to put a beam there rather than somewhere else. "The
library did it" or "the AI wrote that part" is not an answer.

The cheapest way to be ready is to keep the stages separate in your code — one function
per stage, each with a named input and output — and to say in your README which function
produces which part of the picture. If you used an AI tool to write a function, read it
until you could have written it, and be ready to defend it.

## 4. What to send back

A folder or a git repo containing:

| | |
|---|---|
| `README.md` | **The most important file.** How to run it. Your definition of "boundary". The rules you encoded and why. What works, what does not, and what you would do with another week. |
| your code | Any language. It must run on a machine that is not yours — list the dependencies. |
| one output per CRN | The layout-grid drawing for each of the three test plans, named by CRN — browser page, PDF or image. A data file (JSON/CSV) alongside it is optional. |
| a step → code map | A few lines in the README saying which function does which stage, so we can follow your walkthrough. |

If you did part of it by hand rather than in code, say so plainly and show the working.
An honest manual method with clear logic is worth more than code that silently does the
wrong thing.

---

## 5. How we evaluate

**We are evaluating your approach, not your accuracy score. A 100% match with the
engineer's drawing is not required and is not expected.**

What we actually look at, roughly in order of weight:

| We look for | What a strong answer looks like |
|---|---|
| **Problem decomposition** | You split the job into stages, each with a defined input and output. |
| **Handling ambiguity** | You spotted that "boundary" is ambiguous, picked a definition, and wrote down why. Same for the balcony, the plot line, the lift and the stair. |
| **Self-validation** | You checked your computed area against the area statement on each plan, and noticed when a number was wrong. |
| **Honesty** | Your README lists what your program fails at. We trust this more than a clean demo. |
| **Generalisation** | Nothing hardcoded to one house. Scale derived, not typed in. It runs on all three plans. |
| **You can explain it** | You can point at any line in your output and name the code that drew it, and say why it decided that. This is checked in the debrief. |
| **Code clarity** | Someone else could read it and change it. One function per stage beats one long script. |
| **Domain sense** | Beams land on columns, columns stack unless the drawing says otherwise, slab panels close. |

What does **not** earn marks: matching the engineer exactly by tuning constants; a
beautiful drawing produced by hand tracing; using AI and hiding it.

Using AI tools is fine and expected — but you must be able to explain every line you
submit. We will ask.

---

## 6. FAQ

**I have never seen a construction drawing before. Is that a problem?**
No. That is the normal starting point for this role. Section 1 is the whole prerequisite.

**Is there one correct answer?**
No. Two structural engineers given the same floor plan would produce two slightly
different framings, and both would be built. The sheets in `example/` are *one* valid
answer, not *the* answer.

**Can I use ChatGPT / Claude / Copilot?**
Yes. Tell us where you used them. Be ready to explain your code.

**My boundary is off by a few inches. Does that matter?**
No.

**My program finds 11 columns where an engineer would place 14. Is that a fail?**
No. Explain where the differences are and why you think they happened. That paragraph is
worth more than the three missing columns.

**Do I need to compute steel, loads, or bar bending?**
No. Geometry only — boundary, columns, beams.

**Do I need the grid letters and numbers (A, B, C / 1, 2, 3)?**
No. Column points and beam lines in the right places are the full answer.

**Do I need dotted or dash-dot lines like the engineer's sheet has?**
No. Solid lines throughout is fine.

**What format should the drawing be in?**
Whatever you like, as long as we can open it — a page in the browser, a PDF, or an image.
A browser page is usually the least work.

**Do I have to hand in a JSON file?**
No, it is optional. The drawing is the deliverable. A data file only helps us check
numbers quickly.

**Can I ask questions?**
Yes. Ask. Knowing when to ask instead of guessing is part of the job.

---

## 7. Glossary

| Term | Meaning |
|---|---|
| **Beam** | Horizontal concrete rib that carries the slab and spans between columns. |
| **Boundary** | The outline of the built floor area at one level. |
| **Built-up area** | Total floor area including walls, in square feet (SF). |
| **Cantilever** | A beam or slab supported at one end only — a balcony. |
| **Chajja** | A small slab projecting over a window or door, like a ledge. |
| **Column** | Vertical concrete post carrying load down to the foundation. |
| **c/c** | "Centre to centre" — spacing measured between centres. |
| **Concealed beam** | A beam hidden inside the slab depth, so it does not show below the ceiling. |
| **Footing** | Concrete pad under a column that spreads its load into the soil. |
| **Framing** | The layout of columns and beams for one floor. |
| **Grid** | Reference lines (A, B, C… / 1, 2, 3…) drawn through column centres. |
| **G+2, G+3** | Ground floor plus two or three upper floors. |
| **Panel** | One rectangular patch of slab bounded by beams. |
| **Plan** | A top-down view. |
| **Plot** | The piece of land. Bigger than the building. |
| **Section** | A cut-through side view. |
| **Slab** | The flat concrete floor plate. |
| **Span** | The clear distance a beam or slab covers between supports. |
| **SF** | Square feet. |
