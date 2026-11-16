# Build log

What was done in each phase, what the renders showed, and what was changed because of it. Render paths are relative to the repository root.

## Phase 0 — Environment and toolkit

**Environment.** Blender 4.4.3 portable, Python 3.11, Cycles on OptiX (RTX 4070 SUPER). Node 24.14, git 2.53, GitHub CLI 2.98.

**Toolkit** (`blender/rj28/lib/`):

| Module | Contents |
|---|---|
| `core.py` | Scene setup, placement helpers, object creation, weight-driven bevel and shading policy, applied EXACT booleans |
| `prims.py` | Outlines (rounded, chamfered, superellipse), prism, loft, revolve, tube, torus, lug, dome, thicken, bend, plate, Catmull-Rom paths, tube sweep |
| `mech.py` | Screws (M4, M6, M10; socket head, countersunk, quarter-turn), rows and bolt circles with counterbores, bearing, gear, sector gear, slewing ring, bellows, clevis, pin, linear actuator, rotary actuator |
| `harness.py` | Connector, cable, hose with ferrules, P-clips |
| `fittings.py` | Panel gap cut, vents (slats or mesh), hinge, hatch, lifting eye, decal label |

Plus `materials.py` (twelve procedural materials, first pass), `markings.py` (decal atlas) and `render.py` (cameras, studio rig, contact sheets).

**Test board.** `docs/review/phase0/testboard_{clay,final}_overview.jpg` and six close-up zones each.

Defects found on the first render and fixed:

1. Studio lights about 5× too strong; black materials rendered light grey. Rebalanced the rig.
2. Slewing ring: outer bolt counterbores broke through the gear teeth. Bolt lands are now sized inside the tooth roots and the screw size steps down if the land is too narrow.
3. Panel cut on the dome shell left slivers. The cutter twisted where the path ran onto the rim and the surface normal flipped. Normals are now oriented towards the given path and kept continuous.
4. Countersunk screw sat in the block with no countersink. `fasteners` now cuts one.
5. Rubber read grey. Sheen reduced.

Result: all primitives shade cleanly in clay and in final materials. Six panel seams cut into the test dome confirm the approach for the cap.

## Phase 1 — Reference study

One reference image (`reference/01_concept_front.png`). Findings, the brief-versus-image table and the per-assembly part lists are in `docs/DESIGN.md`.

## Phase 2 — Blockout

Built by `blender/rj28/assemblies/blockout.py`. About 150 simple volumes in the final pose, with the mount posed by exact rotation about its axes (`poses.py`).

**Iterations.**

| Pass | What the render showed | Change |
|---|---|---|
| 1 | Legs slim, hip actuators sticking out as ears, cannon reading as a camera on a box | Legs bulked to the limit of the hip spacing; hip pitch actuator made the top of the thigh |
| 1 | Sweep check: cradle hit the head at +25° traverse, yoke hit the right shoulder | Cradle moved on top of the barrel; yoke reduced to one outboard cheek; right pauldron cut back |
| 2 | Side view: torso behind the feet | Upper body moved 30 mm forward, ankle 10 mm forward in the foot |
| 2 | Rear view: two round hip housings | One rectangular housing |
| 3 | Silhouettes: stowed cannon beside the head hides the cap brim; pauldrons read as hollow hoops; overall 2,300 mm | Mount redesigned as a swing arm (D-014); pauldrons given front and rear cheeks |
| 4 | Stowed side silhouette reads: cap with brim, gap, vertical barrel behind the shoulder | Accepted |

**Measured from the blockout** (`docs/review/phase2/blockout_measure.json`):

| Quantity | Target | Measured |
|---|---|---|
| Height to cap crown | 1,730 | 1,731.7 |
| Span over shoulder armour | 700 | 700.0 |
| Chest front to backpack rear | 460 | 467.0 |
| Overall width (arms) | — | 901.7 |
| Overall height, stowed | about 2,050 | 2,115 |
| Overall height, deployed | — | 1,771 (recoil unit) |

Crown height and chest depth are trimmed to target in Phase 3.

**Swept-volume check** (`docs/review/phase2/mount_sweep.json`): passed. Minimum clearance 15.0 mm against a 15 mm requirement. Tightest places: stowed breech over the slewing ring (15.0, by design), head at +25° traverse and −5° (15.5), right pauldron at −5° (18.7).

**G1 sheets** (`docs/review/phase2/`):

| File | Contents |
|---|---|
| `G1_silhouettes.png` | Black on white: four views stowed, four deployed |
| `G1_turnaround_stowed.jpg`, `G1_turnaround_deployed.jpg` | Clay orthographic front, left, back, right at matched scale |
| `G1_three_quarter_clay.jpg` | Three-quarter front and rear, both states |
| `G1_three_quarter_black.jpg` | Same views in first-pass black materials |
| `G1_vs_reference.jpg` | Front view beside the concept art at matched height |
| `G1_barrel_variants.jpg` | Barrel 440 / 500 / 600 / 750 mm, stowed and deployed |

**Open at G1.** Four places where the brief and the concept art pull apart, each built to the brief:

1. Barrel length. 500 mm built (2,115 mm overall). 440 mm gives the brief's 2,050; 750 mm gives 2,365.
2. Stance. Feet at hip-axis width (240 mm). The concept art stands about 430 mm apart.
3. Feet. 135 mm wide soles look small under 190 mm shins. The concept art is nearer 200 mm.
4. Shoulder armour. 700 mm span. The concept art is nearer 800 mm.
