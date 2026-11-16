# RJ-28 INTERCEPTOR — Design bible

Written in Phase 1, corrected after the Phase 2 blockout. Numbers here are design intent; the published numbers come from `measure.py` reading the finished model.

## 1. Reference study

One image was supplied: `reference/01_concept_front.png`, a front view of the robot standing in a bright industrial bay. There is no turnaround, so side and rear are designed from the brief.

What the image shows:

- **Overall.** A near-black, matte machine at human scale. Big smooth armour blocks with broad chamfers, and dense, bright mechanism wherever two blocks meet. The read is "armour bolted onto a machine".
- **Head.** A small helmet-like head with one thin cyan slit across the upper face and a two-lens cluster on the robot's left cheek. A rigid cap sits on top with its brim swung round to the rear-left.
- **Shoulders.** The largest masses on the figure: faceted pauldrons sitting over ribbed cylindrical actuators, which stay visible below the armour.
- **Chest.** One broad plate, hexagonal with chamfered corners, spanning shoulder to shoulder with a few fine panel splits. Below it the torso opens into a spine of stacked rings and short struts, ending in a bright waist ring.
- **Arms.** Finned actuator drums at the top, then a single very large armour block around the forearm, a mechanical wrist and a blocky hand.
- **Pelvis and legs.** An exposed pelvis with diagonal struts, large tapered thigh shells, round knee housings with bright bearing races, flared shin shells with polished rods showing in a front slot, and heavy boots with a thick sole.
- **Cannon.** A thick short tube over the right shoulder with a small box breech beside the head carrying a cyan-lit optic.

Shape language taken from it:

1. Large calm surfaces, single curvature or flat, with wide chamfers. No compound organic curves.
2. Mechanism concentrated at the joints and the waist, where it is bright against the black.
3. Round joint housings (shoulder, elbow, knee) set against angular armour.
4. A deep, wide chest over a waist that is all mechanism.
5. The cap as a clean geometric object, not a soft one.

## 2. Where the image and the brief disagree

| Topic | Image | Brief | Resolution |
|---|---|---|---|
| Cannon direction | Points to the robot's right | Level, pointing forward | Brief. Hard requirement. |
| Cap brim | Swung to the rear-left | Straight back, raked down 12° | Brief. Hard requirement. |
| Stance | Wide A-stance, feet about 430 mm apart | Feet at hip-axis width (240 mm) | Brief. Open question at G1. |
| Shoulder armour | About 800 mm over the pauldrons | 700 mm | Brief. Open question at G1. |
| Feet | About 200 mm wide | 310 × 135 mm | Brief. Open question at G1. |
| Knee | Reads as a rotary joint | Crank driven by two linear actuators | Both: round bearing housings stay on the knee axis, the linear actuators sit behind the thigh. |
| Barrel | About 400 mm long | About 750 mm, and about 2,050 mm overall when stowed | These two brief numbers conflict with each other. See 4.6 and D-007. |
| Warning labels | Yellow triangles | White and ice cyan only | Brief. |
| Setting | Bright factory | Dark studio | Brief. |

## 3. Proportion scheme

Height 1,730 mm to the cap crown, about 8 heads. Legs are half the height (hip axis 905 mm). Shoulder armour 700 mm against 240 mm between the hip axes. The chest is 330 mm deep before the backpack.

Bulk comes from components, and each bulky volume is designed around what is inside it:

| Volume | Outside | What fills it |
|---|---|---|
| Shoulder | Ø150–176 housings, 700 mm armour span | Three rotary actuators: pitch (in the thorax flank), roll (on the joint centre), yaw (top of the upper arm) |
| Forearm | 192 × 198 mm | Hand drive: six motors with their screw drives and linkages |
| Chest | 320 × 330 mm frame under 15 mm panels | Battery pack, two compute modules, power distribution, shoulder pitch actuators |
| Backpack | 330 × 128 × 330 mm | Two radiator cores, two blowers, coolant reservoir, mount hardpoint |
| Hip | Ø174 drum | Hip pitch actuator, forming the top of the thigh |
| Thigh | 212 × 206 mm, plus actuators behind | Structural frame; two knee actuators outside the armour at the rear |
| Shin | 190 × 196 mm | Structural member, two ankle actuators at the rear, cable channel |

Stance: upright, knees flexed 4°, toes out 6°. Everything above the waist sits 30 mm forward of the hip axes so the mass of the backpack and cannon stays over the feet (D-012).

## 4. Assemblies

Part numbers are `RJ28-AA-NNN`. Counts are intent for Phases 3 to 5 and total about 430.

### 01 Head and cap (about 40 parts)

Skull frame; faceplate, raked 12° with the top forward, 124 mm wide at the jaw and 148 mm at the brow; slit bezel, slit glass, emitter strip, stereo camera pair on a bracket; lens cluster bezel on the left cheek with thermal imager, lidar window and spotter camera; jaw guard with two louvred intakes; lidar unit; processing board and heat spreader; neck connector and wiring.

Cap: crown shell (4 mm, six panels separated by real 1.5 × 2 mm seams), sweatband ring with four countersunk screws, antenna puck at the button position, snapback arch with mesh backing, strap bar with seven hex studs, brim (175 × 72 × 4 mm, raked 12° down, edges curved down 9 mm), three rear sensor windows and two status LEDs under the brim lip, "28" stencil.

The cap base sits at 1,613 mm at the rear and 1,637 mm at the front, so the cap sits back on the head and its front edge clears the slit. The crown's high point is shifted 14 mm towards the brim, which is what makes it read as a cap and not as a dome.

### 02 Neck (about 16 parts)

Neck ring on a crossed-roller bearing (yaw); two-axis gimbal; two linear actuators with bellows, clevises and pins (pitch, roll); cable loom of four braided runs and one coolant line with slack loops; connector plate.

### 03 Thorax (about 60 parts)

Frame (welded and bolted aluminium); sternum panel, two pectoral panels, two flank panels with mesh intakes, collar guard; armour carriers; two front service hatches with hinges and quarter-turn fasteners; two shoulder yokes with lifting eyes; data plate. Inside: battery enclosure with busbars, service disconnect and coolant ports; two compute modules on cold plates; power distribution unit; two shoulder pitch actuators.

### 04 Abdomen and spine (about 28 parts)

Spine column; waist slewing ring (yaw); two pitch actuators with bellows and clevises; flexible conduit across the joint; four overlapping lames with their carriers, open at the rear; side bellows.

### 05 Pelvis (about 26 parts)

Pelvis keel and upper block; two hip yaw actuators; hip roll housing at the rear; groin plate; two side plates with tie-down rings; lower race of the waist joint.

### 06 Backpack (about 34 parts)

Shell; two radiator cores behind slatted grilles; two axial blowers with guards; coolant reservoir with sight window; battery service door with over-centre latches; mount hardpoint bracket and gusset; travel lock.

### 07 / 08 Arms (about 34 parts each)

Shoulder roll actuator; pauldron shell with front and rear cheeks, on a carrier; shoulder yaw actuator; upper-arm structural member; outer half-shell; elbow housing with dust cover and hard stop; forearm shell in two halves with two access panels, a vent and a wear plate; forearm roll bearing; wrist joint with bellows.

Left and right are not mirror images. The left pauldron reaches 356 mm from the centreline, has a longer skirt and a rear cheek, and carries the unit number. The right reaches 344 mm, sits 12 mm lower and is cut back at the rear to clear the cannon (D-011).

### 09 / 10 Hands (about 28 parts each)

Palm frame; knuckle plate; thumb in two segments; three fingers in three segments each; linkage bars on each finger; palm and fingertip pads. Six degrees of freedom: thumb opposition and flexion, one driven flexion per finger, and a ganged splay (D-013).

### 11 / 12 Legs (about 36 parts each)

Hip pitch drum and cap; thigh frame; thigh armour in two pieces with a gap showing the frame; two knee actuators (body, rod, bellows, clevises, pins, clips); knee barrel, outer and inner bearing housings, crank lug; knee guard on a linkage; shin member; front shin panel with vent slots, two side panels, rear cable channel and cover; two ankle actuators.

### 13 / 14 Feet (about 14 parts each)

Ankle universal joint; machined frame; armoured upper; hinged toe section; heel block; replaceable sole with straight sipes.

### 15 Interceptor mount (about 46 parts)

See 4.6.

### 16 Harness (about 30 parts) and 17 Markings (about 24 parts)

As the brief: runs with real sag, P-clips every 80 to 120 mm, connectors with backshells at both ends, service loops at every moving joint. Markings in white and ice cyan only, set in Saira Stencil One.

### 4.6 Interceptor mount — geometry as built in the blockout

A swing-arm mount with one main axis.

| Item | Value |
|---|---|
| Trunnion axis | Parallel to X at y = +160, z = 1,515 mm, behind the right shoulder joint |
| Bore axis | 125 mm above the trunnion when level; x = −292 mm |
| Level (deployed, 0°) | Bore at z = 1,640 mm, over the right shoulder armour, muzzle 219 mm ahead of the chest |
| Vertical (stowed, 90°) | Bore at y = +285 mm, behind the shoulder; breech between z = 1,385 and 1,615 mm |
| Working range | −5° to +90° |
| Traverse | ±25° on a Ø170 slewing ring directly under the trunnion |
| Barrel | Ø110 × 500 mm, reinforce at the breech, plain muzzle ring |
| Breech | 230 × 170 × 190 mm |
| Overall height, stowed | 2,115 mm (blockout measurement) |

How it is carried, from the body outwards:

1. **Hardpoint**: a titanium bracket from the right side of the backpack, with a gusset below.
2. **Slewing ring** (traverse) on the hardpoint.
3. **Yoke**: a base on the ring, flat at the rear so the breech can swing down past it, and a single cheek on the outboard side carrying the pivot housing. One cheek, so nothing stands between the breech and the head.
4. **Swing arm** (elevating): a plate from the trunnion up to the outboard flank of the breech, with the gear sector on its lower edge.
5. **Elevation drive**: a motor inboard of the swing arm, forward of and below the trunnion. That is the one quadrant the cannon never sweeps.
6. **Cradle**: two guide rods and the recoil unit on top of the barrel. Nothing is below the barrel (shoulder armour) or inboard of it (head).
7. **Feed box** on the inboard flank of the breech, facing the backpack. **Tracking head** outboard, beside the barrel root.

Why a swing arm: with the trunnion through the breech, the stowed cannon stood beside the head. It hid the cap brim in side view and stood 2,300 mm tall. Lowering the trunnion and carrying the cannon above it puts the stowed barrel behind the shoulder with a visible gap to the brim, and brings the height down (D-008).

Swept-volume check (`poses.sweep_check`, report in `docs/review/phase2/mount_sweep.json`): 60 poses covering elevation −5° to 90° at zero traverse, and traverse ±25° at both 0° and −5°. Minimum clearance to the body is 15.0 mm (stowed breech over the slewing ring, by design) and 15.5 mm to the head at full inboard traverse.

## 5. Joints

All 46 degrees of freedom get real hardware in Phase 4. Axes and drives:

| Joint | Axis | Drive |
|---|---|---|
| Hip yaw / roll / pitch | Z / Y / X at the hip centre | Three rotary actuators |
| Knee pitch | X | Two linear actuators behind the thigh on an 85 mm crank |
| Ankle pitch, roll | X, Y | Two parallel linear actuators on a universal joint |
| Waist yaw | Z | Slewing ring |
| Waist pitch | X | Two linear actuators beside the spine |
| Shoulder pitch / roll / yaw | X / Y / along the arm | Three rotary actuators |
| Elbow pitch | X (arm frame) | Cycloidal rotary |
| Forearm roll, wrist pitch, wrist yaw | Along the forearm, then two crossed | Rotary |
| Hand (6) | See 09/10 | Motors in the forearm, linkage drive |
| Neck yaw | Z | Rotary ring |
| Neck pitch, roll | X, Y | Two linear actuators |
| Mount elevation / traverse / tracker tilt | X / Z / X | Sector gear and pinion / slewing ring / small rotary |
