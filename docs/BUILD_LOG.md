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

## Gate G2 outcome

Paul asked for three fixes and then to carry on: bundle the limb looms, seat the clevis bases, reframe the social card.

- *Looms.* The thigh, knee, ankle, arm and elbow runs are bundles of two to four braided cables bound with ties (D-043).
- *Clevis bases.* Looking closely at "sunk bases" showed the knee anchor was wrong altogether: the actuator bodies passed through the block. The anchor is now a pair of fork ears per actuator machined into the thigh frame (D-041). Ankle clevises sit on raised pads and all clevis bases show their screws (D-044).
- *What that uncovered.* With the larger clash gone the contact check reported the next layer down: knee and ankle power connectors buried in the crosshead and shin beam, the right arm coolant hose through the mount hardpoint, the tracker plug 8 mm inside the breech housing, the knee encoder cable through a fork cheek, and loom clip tabs fouling the right inner knee actuator. All are rerouted or reseated (D-042). The check now takes a `harness` argument that tests cables, hoses and plugs too; it was skipping them.
- *Social card.* Camera pulled back and lowered: the whole cap and muzzle are in frame, the robot sits in the right half, the left 40% is clear for a title.

After the fixes: 926 parts, mount sweep 18.0 mm, mass 185.01 kg. The contact check still reports every lead that enters the shoulder yaw housing region as sunk; in the renders they lie on its surface, and the housing's overlapping fin shells defeat the inside test. The elbow loom ends 6 mm inside the forearm by intent (it passes through the grommet).

## Phase 8: export

**What is exported.** `blender/rj28/export.py` (build target `export`) writes the web model at two levels of detail, a line model of its feature edges, the studio panorama, the mount data and the tour stations. `tools/gltf/optimize.mjs` compresses the three GLBs and writes the manifest; `tools/gltf/verify.mjs` checks them against `parts.json`; `export check` imports the compressed files into an empty scene and renders them. The whole sequence is at the top of `export.py`. A fresh run takes about 160 s in Blender and 5 s in Node.

| File | Size | Content |
|---|---|---|
| `site/public/models/rj28_lod0.glb` | 14.43 MB | 1,318,632 triangles, 1,169,170 vertices, 990 nodes |
| `site/public/models/rj28_lod1.glb` | 3.40 MB | 192,719 triangles, 245,468 vertices, 990 nodes |
| `site/public/models/rj28_edges.glb` | 2.74 MB | 450,441 line segments, 943 nodes |
| `site/public/hdri/studio.hdr` | 1.20 MB | 2,048 x 1,024 equirectangular |

990 nodes are 926 parts under 17 assembly nodes, plus `AXES` and its 46 joint axes. Both levels use the same fourteen materials and the same node names.

**No bake (D-045).** The model goes out as geometry with shared stand-in materials. The exporter cannot read the procedural node trees, so each `RJ28_<key>` material is swapped for a plain one of the same name whose constants are read from the inputs `materials.py` set; glass becomes an opaque dark gloss, and aluminium and mesh are double-sided because they contain open parts.

**LOD0 (D-046).** The triangle count came down from 1.43 M to 1.32 M and stopped there. The two suggestions that looked largest gave nothing: the 243 fastener sets and the harness are built without a bevel modifier, so there was no bevel to turn off. What remained was a coplanar merge (4.6%) and dropping bevels under 0.35 mm (3%). The fasteners are 226,000 triangles, about 190 a screw; they are the place to look if LOD0 has to shrink.

**LOD1 (D-047).** The first version decimated everything, armour at 50%. It read as the robot from a distance, but in the check render a panel between the thighs lit up where LOD0 is dark. It went when armour was left alone, so armour is not decimated and the cut falls on mechanism and fasteners. Collapse decimation loses the sharp-edge marks, so hard edges are marked again by angle and the weighted normals recomputed in a second pass.

**Masks in COLOR_0 (D-048).** The edge mask is taken from the bevel modifier itself, which can tag the faces it creates; parts without a modifier use a width test for modelled chamfers. The cavity mask took three attempts. Cast about vertex normals it painted whole pectoral plates dark, because a corner vertex's normal leans into the gap beside it. Cast about shading normals the open flats came clean, but a plate lapped along two edges still interpolated dark right across, so faces wider than about 70 mm are faded out. It takes 12 million rays and 50 s. It is a crevice mask, not an occlusion bake.

**Compression (D-049).** Positions could not be quantised in the usual way without putting a transform in every part node, so they stay floats on a 0.03 mm grid. That is why LOD0 is 14.4 MB and not under 12: positions are 5.4 MB and normals 5.2 MB. Eight-bit normals would bring it to 11.7 MB; they were not used in LOD0 because their effect on gloss-black curved surfaces can only be judged in the web renderer.

**Mount (D-050).** `mount.json` holds what `poses.py` does: trunnion and traverse pivots and axes, the rule `elev = V * E`, `trav = V`, the 34 and 15 node names, check matrices for both states, the travel lock parts and the energy chain morph. `verify.mjs` compares the node matrices in the GLB with the check matrices.

**What went wrong.**

- *Explode offsets of the cannon.* The first export disagreed with `parts.json` on all 34 elevating parts. `explode.apply()` measures parts in whatever pose the mount is in, against a spine drawn for the level pose; the batch that wrote `parts.json` ran the sweep check first, which leaves the mount level. The export now sets the mount level before it calls `explode.apply()`. `modelrun` still depends on the order of its options.
- *Studio panorama.* `hero.hdri()` produced a file that passed "not black" and contained no lights (D-054).
- *Blender cannot import meshopt.* The check renders use an uncompressed copy that `verify.mjs` writes from the compressed file, so they still show what the compression did.
- *Leftover accessors.* The first compressed files were larger than the raw ones: reorder and quantise leave the accessors they replace in the document, and they were being written out.

**Stations.** Ten cameras are authored in `blender/rj28/stations.py` and rendered with the hero rig at 960 px: `docs/review/phase8/station_NN.jpg`, with `_mid` and `_end` for the four that move. Six were reframed after the first proofs (thorax centred, the whole left arm in frame, knee and foot both in frame, shins and shoulder both in frame for the armour station).

**Checks.** `verify.mjs` passes: 926 part nodes in each file, every `node` of `parts.json` present, extras equal to `parts.json`, COLOR_0 and a material on every primitive, 46 axes with local +Z on the joint axis, sizes inside the budgets. The re-import renders are `docs/review/phase8/check_*.jpg`, including two that show the masks.

**Still weak, said plainly.** LOD0 is 10% over the triangle target and 20% over the size that was hoped for. The line model was checked by count and structure only; nobody has looked at it drawn. The cavity mask is zero on every wide flat, including ones that really are shadowed. The energy chain does not follow the traverse, in the build or in the export. The wire pattern of the `mesh` material and the transmission of the glass are not in the files; the site has to rebuild both from the material names. In the Cycles renders every marking sits in a faintly lighter rectangle, most likely because the dust mask's occlusion node sees the marking's own quad; the web model does not have this, so the two will not match there.

## Phase 8: drawings

Five A1 sheets, generated from the model by `blender/rj28/drawings.py`:

```
blender --background --python blender/build.py -- drawings [sheet=1,3] [cache] [nopng] [nopdf]
```

Output: `site/public/drawings/RJ28-GA-001.svg` to `-005.svg`, `RJ28-GA-set.pdf`, the viewer index `site/src/data/sheets.json`, and previews in `docs/review/phase8/`. A full run takes about 100 s, of which 40 s is building the model; `cache` keeps the built model in `blender/out/` between runs.

**Method.** The line work is projected, not rendered (D-060).

1. Each part gives up its un-bevelled mesh as arrays: vertices, edges, the normals of the two faces on each edge, triangles, and the loose island each edge belongs to.
2. For a view the candidate edges are creases over 32°, open borders, and contour edges, where one face looks at the viewer and the other away. The contour edges are what draw the cap crown, the barrel and every housing.
3. Each candidate is sampled every 0.25 to 0.3 mm on paper. A ray from the sample towards the viewer through a BVH of the scene decides whether it is hidden. The ends of each visible run are found by bisection.
4. Two more rays, one either side of a visible contour sample and away from the viewer, measure how far the surface drops behind the edge. A large drop makes an outline, drawn thick; everything else is thin (D-061).
5. Runs are joined into polylines at shared end points, simplified to 0.012 mm, and written as one SVG path per part and line class, inside one group per view. Coordinates are relative and in hundredths of a millimetre.

Sections cut every mesh with `bisect_plane`, close the cut, and hide what is behind it with the same ray test. The cut loops themselves give the section outline and the lining: a scan line at 45° counts how many solids it is inside, so a part made of overlapping shells is lined once.

Annotation is scripted. Dimensions, tables and notes read `spec.json`, `parts.json` and the mount sweep report; cap, slit and barrel sizes are measured from the parts in the scene; the knee and ankle geometry is computed from the same pivot definitions the model is built from. Text is real text in Archivo and IBM Plex Mono, embedded in each file. Stroke weights and colours are CSS classes in one style block, so the site can restyle a sheet.

`sheets.json` lists, per sheet, the views and where every part and assembly appears: the centre and size of its visible line work in each view, and its balloon if it has one. Balloons carry `data-part` or `data-assembly`; every part's paths sit in a group with `data-part`.

**Sizes.** 1.61, 0.55, 0.59, 0.56 and 0.80 MB; 3,051, 627, 541, 315 and 1,018 paths. Each file carries about 0.16 MB of embedded fonts. The PDF is 3.2 MB, five pages of 841 × 594 mm.

**What went wrong.**

- *Everything was an outline.* The first rule drew every contour edge thick. Each of 926 parts has a silhouette, so the sheet was thick lines throughout. Weight now comes from the depth step behind the edge.
- *Edge-on faces.* A ray that starts on an edge and runs along a face touching it hits or misses by rounding error. Edge-on faces are left out of the occluders (D-062).
- *The cannon came apart in the exploded view.* `explode.pose(0.5)` zeroes each part's location, which removes the translation in the stowed mount pose. The sheet moves the assembly roots itself (D-067). The preview renders made through `explode.pose` have the same fault.
- *False slit dimensions.* The slit glass was first measured along the face rake from `params.py` and came out 11.6 × 6.3 mm. The glass does not lie at that angle. Its section axes are now found from its own vertices: 12 × 1.6 mm.
- *Knee lines of action.* The detail drew the line of action at both ends of the travel. The crank is phased so that the two coincide within 0.3 mm, and the two dimensions landed on each other. One line is drawn and both values are stated.
- *Layout.* The top view above the front view costs 155 mm of height on the head sheet and 128 mm on the general arrangement; both sheets are tight. The mount sheet needed 1:2.5 to keep plan, side and front views in projection (D-064).
- *Diameter sign.* Neither font has U+2300; the PDF fell back to another face. Ø is used.

**Still weak.**

- Layout is set by hand per sheet. Nothing checks for text on text or a dimension over line work, so a change to the model's extents needs the sheets looked at again.
- Text widths are estimated from average advances, not measured. Table columns and the paper masks behind text over line work are sized with margin to cover that.
- Sheet 1: the shoulder armour span is in the data table only; no dimension line reaches it without crossing the mount. Landmark extension lines start at the outline, not at the axis.
- Sheet 2: the section and the row of views share 10 mm of clearance. Balloon leaders cross the section. Where parts interpenetrate in the model their linings overlap. The list names the 30 ballooned parts of 97.
- Sheet 3: the plan is crowded where three phantom positions lie over the thorax and backpack. Clearances are flags and a schedule (D-065). The depression limit is a centre line, not an outline.
- Sheet 4: the view from behind is tilted by the abduction because it is square to the knee axis (D-066). The flexed shin is not drawn; only the crank pin at 110°. Ankle roll is not shown.
- Sheet 5: the harness is displaced forwards and lies over the left leg and pelvis, as the explode data has it. Three leaders pass over the right arm. No trace lines join the assemblies.
- Rebuilding the PNG and PDF needs Microsoft Edge at its usual path; without it the SVG files and the index are still written and a warning is printed.

## Movements on the site

`blender/rj28/rig.py` (target `rig`) writes `site/src/data/rig.json` from `parts.json`, the joint axes and the hand chain: 70 links, 808 rigid parts, 12 actuators, 63 parts that bend. `site/src/scene/rig.ts` turns joint angles into a matrix per part; `animate.ts` plays keyed movements from `clips.ts`; `fx.ts` draws the engagement for the intercept.

Seven movements from the Animations button at the foot of the model: look around, function check, squat, wave, fist bump, fist to palm, intercept. They play at any strip-down stage.

**Checked by looking.** Contact sheets of each movement mid-play (`tests/pose.mjs`), armour on and off; fist contact placed with `tests/reach.mjs`, which searches the right arm's angles for the left palm. Capture run clean.

**Still weak.**

- No collision check while moving: poses were placed by eye and by the reach search. The cannon is only swept in its own two axes.
- Coupling bars of the fingers and the lame guide links ride one link instead of working as linkages.
- Tracker tilt and the toe hinge are not driven. The energy chain follows elevation only.
- The drawing view shows the rest pose; movements stop when the model tab is left.
