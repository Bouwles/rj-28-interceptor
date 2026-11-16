# Modelling guide

How every assembly of the RJ-28 is built, so that seventeen assemblies read as one machine. `blender/rj28/assemblies/leg.py` is the worked example; read it before writing an assembly.

## The bar

Paul's verdict on the blockout: nowhere near as intricate as the concept art. The finished model has to hold up beside `reference/01_concept_front.png`: layered armour with visible thickness, and dense, legible mechanism wherever two armour blocks meet. Intricate where things move, calm where they don't. Every part still has a job; no decoration.

## Build and look

```
blender --background --python blender/build.py -- model only=<mods> noctx sheets close   # alone
blender --background --python blender/build.py -- model only=<mods> robot tag=<name>     # in context
```

- `only=arm,hand` builds those modules in detail. Without `noctx` the blockout fills in everything else.
- `sheets` writes `docs/review/phase3/<AA>_<name>_clay.jpg` (four orthographic views and a three-quarter). `close` calls the module's `review(asm, out, tag)` for close-ups. `robot` renders the whole figure. `sweep` runs the mount clearance check.
- Send the log to `blender/out/<name>.log` and grep it for `ASM|COUNTS|Traceback|Error`.
- Open every render. Write down specific defects, fix them, render again.

## Module shape

```python
def build(s):                      # sided assemblies take s = +1 (left) / -1 (right); others take no argument
    a = Asm("11" if s > 0 else "12")
    ...
    return a

def review(a, out, tag=""):        # optional close-ups
```

Register the module in `model.PLAN` (already listed for all seventeen).

## Parts

- `a.add(short_name, bm, function, material, matrix, bevel, seg)` makes and registers a part from a bmesh.
- `raw(bm, matrix, material, bevel, seg)` makes a working object to cut and split; adopt the results with `a.take(obj, short_name, function)`.
- `a.take_actuator`, `a.take_rotary`, `a.take_slew` adopt the dicts returned by `mech.linear_actuator`, `mech.rotary_actuator`, `mech.slewing_ring`.
- The function is one plain sentence, capital first letter, full stop. It appears in the inspector.
- Numbers are assigned in creation order. Do not reorder calls casually once drawings exist.
- Mount parts need `group="elev"` or `group="trav"`; other parts near the mount keep their default zone so the sweep check sees them.

## Frames and units

Millimetres everywhere. Z up, robot faces −Y, robot's left is +X. `frames.py` gives the joint frames: `FR.leg(s)`, `FR.arm(s)`, `FR.cannon()`, `FR.torso()`. Everything above the waist is built in body coordinates and placed with `FR.torso() @ ...` (`FR.arm` frames need the same). Dimensions live in `params.py`.

The blockout is the approved envelope. Stay inside it to within a few millimetres unless there is a reason, and say so in the report.

## Armour

1. Design one shell with `A.rsec` sections (rounded rectangles; flat faces joined by 30 to 50 mm radii) and `A.shell(sections, 10)`. Use `A.csec` only for machined structure.
2. Open it where the mechanism should show: boolean cuts with `lip=0.6`. Wrap the cuts in a local function so the carrier gets the same ones.
3. Slice it into panels with `A.gap_cut` (2 mm) and split with `A.islands`. Classify the pieces by their centre in the limb frame, not by list order.
4. Line it with `A.hoops` in `cfrp`, cut like the shell, on `alu` standoffs from the frame.
5. Add what a real panel has: counterbored M6 screws from `D.seats_on` + `mech.fasteners(target=panel)`, one or two panel lines with `F.panel_cut`, a hatch (`F.hatch`) or vent (`F.vent`, `A.slots`) where there is something behind it to reach or cool.

About 70% of the armour surface stays calm. Detail clusters at joints, hatches and connectors.

## Structure and mechanism

- Frames are `alu`: lofted `A.csec` beams, `P.lug` hangers and forks merged into one part, lightened with `D.pocket_grid`.
- Rotary joints: `mech.rotary_actuator` (finned housing, flange, bolts, connector), or a hub with bolted covers (`D.bolted_cover_profile`), a polished retainer ring and an encoder (`D.encoder_bm`).
- Linear joints: `mech.linear_actuator` between two pivot points. Give it `base_dir0` / `base_dir1` pointing at the structure each fork bolts to, and make sure that structure is really there.
- Kinematics must be honest: forks straddle eyes, shafts pass through bores, nothing sits inside the swept disc of the part it rotates against. Check the neighbours' radii before placing a block.
- Materials by key: `armour`, `cap`, `alu`, `ti` (joints, forks, links), `steel` (rods, pins, races only), `fastener`, `rubber`, `braid`, `cfrp`, `glass`, `mesh`, `emissive`, `cavity`.
- Bevels: armour 1.2 mm with 3 segments; machined parts 0.8 to 1.0 with 2; small parts 0.3 to 0.5 with 1; revolved parts that carry their own chamfers 0.

## Left and right

Built by one function looped over `s`. They are separate parts with their own numbers, and they differ where the design says so: the left pauldron is larger, the right is lower and cut back for the mount, the lens cluster is on the left cheek, hatches are one-sided.

## Interfaces between assemblies

| Between | Agreement |
|---|---|
| Thorax and arm | Thorax owns the shoulder pitch actuator; its output face is at x = ±(SX − 77). Arm owns the roll actuator on the shoulder centre and everything outboard. |
| Arm and hand | Forearm ends 262 mm below the elbow. Hand owns the wrist joint at the `FR.arm` hand frame origin. |
| Pelvis and leg | Leg owns the hip pitch actuator: Ø174, spanning x = −67s to +83s in the hip frame, with thigh hangers at x = +93s and −74s. The pelvis grips the housing between those hangers. |
| Leg and foot | Shin fork cheeks at x = ±72 (14 thick) with a Ø32 bore on the ankle axis. Ankle actuator forks land at foot-frame (±40, 104, −40): the foot provides a heel bridge there. Foot owns the ankle joint. |
| Abdomen and pelvis | Abdomen owns the waist slewing ring at z = 1,060; pelvis provides its lower seat. |
| Thorax and neck / head | Neck ring sits on the thorax top deck at z = 1,490, centre (0, 4) before the torso offset. Skull base at z = 1,538. |
| Thorax and backpack | Backpack bolts to the thorax back plane, y = THORAX_BACK_Y before the torso offset. |
| Backpack and mount | Mount hardpoint bolts to the right side of the backpack (x = −PACK_HALF_W). Travel lock sits on the backpack's top right rear corner. |

## Before calling an assembly done

- Builds with no error; part count printed.
- Every sheet and close-up opened and criticised against section 5 of the brief: bevel on every edge, real thickness, even gaps, fasteners by rule, nothing floating, nothing intersecting that should not.
- In-context render checked against the neighbours.
- If the assembly is near the mount (head, right arm, backpack, thorax top): `sweep` still reports at least 15 mm.
