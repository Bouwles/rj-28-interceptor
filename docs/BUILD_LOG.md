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

## Gate G1 outcome

Paul approved the blockout and settled the four open points the same way: match the concept art. Hip axes 270 mm apart with the legs abducted 5.5° (about 425 mm between the feet), soles 330 × 195 mm, shoulder armour 780 mm over 520 mm shoulder axes, barrel 455 mm. Stowed height then measures 2,050 mm, which is the brief's figure. Logged as D-021.

On seeing the first detailed parts Paul also raised the bar: the model has to carry the density of the concept art. Every assembly now carries its real mechanism, armour carriers, fasteners and harness, and the part count is allowed past 500 (D-023).

## Phases 3 to 6 — the detailed model

**Method.** One way of building for all seventeen assemblies, written down in `docs/MODELLING_GUIDE.md` with the leg as the worked example. Armour is one rounded-section shell per limb segment, opened where the mechanism should show, sliced into panels by 2 mm gap cuts, lined with carbon ribs on aluminium standoffs, then given counterbored screws, panel lines, hatches and vents where there is something behind them to reach or cool. Structure is machined aluminium with lightening pockets; joints are titanium; only rods, pins and races are polished steel.

**Order of work.** Head and cap first (the signature part), then neck, legs and feet. Arms and hands, mount and backpack, and the three torso assemblies were built in parallel against the interface table in the modelling guide, then joined. Harness and markings last, because they attach to everything else.

**Count.** 930 named parts in 17 assemblies (767 before the review pass below):

| Assembly | Parts | | Assembly | Parts |
|---|---|---|---|---|
| 01 Head and cap | 70 | | 09 / 10 Hands | 34 each |
| 02 Neck | 27 | | 11 / 12 Legs | 85 / 82 |
| 03 Thorax | 85 | | 13 / 14 Feet | 31 each |
| 04 Abdomen and spine | 71 | | 15 Interceptor mount | 60 |
| 05 Pelvis | 35 | | 16 Harness | 81 |
| 06 Backpack | 38 | | 17 Markings | 19 |
| 07 / 08 Arms | 73 / 72 | | | |

**Measured from the mesh** (mm, `measure.py`): crown 1,730; span over shoulder armour 780.0; stowed height 2,050. Mount sweep: 18.0 mm minimum clearance against 15 mm, over elevation −5° to 90° and traverse ±25° at both 0° and −5°.

**Things that went wrong and what fixed them.**

- *Knee.* The first crank put the actuator line through the joint centre near 90°, so the lever arm vanished exactly where a squat needs it. Rebuilt as a fork with an open corridor and a crank phased 13° off the mid-stroke: 40 mm of lever arm at both ends of a 0 to 110° range and 70 mm in the middle. Knee range dropped from 120° to 110° (D-025).
- *Mount against the head.* With the detailed skull the barrel cleared the brow by 13.8 mm at −5° elevation and +25° traverse. The top of the skull was narrowed; clearance is 19.1 mm there now.
- *Booleans that return nothing.* The exact solver gives an empty mesh when a cutter overlaps itself or the target is a merge of overlapping solids. `core.boolean` now refuses an empty result and reports it, `model.build` reports any part with no vertices, and the guide says to union solids before cutting them.
- *Wear on curved armour.* A pointiness mask marked every smoothly curved panel as an edge and blotched the cap. Edge wear now comes from the difference between the bevelled and the true normal, on convex edges only (D-028).
- *Battery.* The mass roll-up pins the battery at 23 kg and reports the fill factor it needed. It came out at 1.98: the enclosure was half the size a 5.0 kWh pack needs. The enclosure is now a stepped casting of 8.3 litres that fills the tub round the waist reaction beam and under the shoulder actuators (D-033). The endurance note states the pack-level density that this still demands.

**Design notes** are computed by `measure.py` from the built model and written to the site data: static knee torque in a 90° squat against the modelled lever arm, endurance from pack energy and draw, and the mass roll-up from part volumes (185.0 kg against 185).

**Known limits, carried forward.** Hip abduction stops about 11° beyond neutral and hip flexion near 90°, where the roll link meets the armour. Shoulder abduction stops about 15° beyond rest (D-038). Knee flexion is limited to 105° (D-039). The energy chain between breech and backpack is a linear morph between its two end shapes. Sector and pinion teeth on the elevation drive are not phase-aligned.

## Review pass before Gate G2

**Fresh eyes.** A reviewer who had seen nothing but the renders and section 5 of the brief was asked for the ten things that most gave the model away as computer-generated. The list, worst first: toy feet; a chest of three coplanar doors; an abdomen of four stacked boxes; a cap that read as a dome; single-hood pauldrons; a bare skeleton at the rear of the legs; a harness of crossing single cables; two uniform materials; clip-art gears and knife-edged bellows; raw boxes inside the chest.

**What changed.**

| Area | Before | After |
|---|---|---|
| Feet | Slab sole with straight sipes, bare ankle cube | Heel, arch and toe pads of rubber on screwed carrier plates with staggered lugs; ankle cross with bolted caps and two encoders; toe shell with a wrapped strike plate |
| Chest | Sternum and two pectorals in one plane | Pectorals set back with a facet break; clavicle and rib plates lapping over them on their own carriers; T-shaped sternum keel |
| Abdomen | Four stepped rings | Four tapered lames lapping 14 mm, rolled lower lips, slotted shoulder screws, two tie-rod links a side |
| Cap | Faceted dome, flat brim, strap bar with hex studs | Six gores with raised seams and eyelet vents, a button, a brim with 12 mm camber and a rolled bead, ladder strap under one latch, mesh in the arch |
| Head | Blank tub, lens bump | Three skull shells with gaps and screws, cheek intake, service door, machined three-lens cluster |
| Pauldrons | One extruded hood | Cap, main plate and hinged skirt on a carrier; left larger with a rear cheek, right cut back |
| Legs, rear | Open mechanism only | Hamstring and calf guards on brackets (hatch on the left, cooling slots on the right), strike plates on the fronts |
| Harness | Leads crossing behind the pelvis | Leads leave the panel in a rank, pass a saddle clip, then fan out; nothing crosses the centreline |
| Materials | Uniform per material | Part-to-part roughness and value variation; decals toned to paint |
| Gears, bellows | Three-chord teeth, sawtooth folds | 20° involutes with relieved roots; rounded crests, beaded cuffs |
| Lighting | Fixed rig | Rig turns with the camera; two strip boxes beside the lens |

**Checks added.** `blender/tools/check_contact.py` reports any part that comes within 1.5 mm of nothing (floating) and any vertex more than 6 mm inside another part. Floating parts went from 19 to 1 (the frameless traverse motor, which has an air gap by design). The same pass caught the arm trunk cable running through the mount hardpoint and the neck connector standing in the yaw motor.

**Still weak, said plainly.** Clevis bases of the knee and ankle actuators are sunk into their anchor blocks, not seated on machined pads. The arm and leg looms are single runs with clips, not bundled trunks. Cables do not sag under gravity. The traverse motor is a plain ring.
