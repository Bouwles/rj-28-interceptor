# Decisions

One line per decision, newest at the bottom. "Brief" means the master build prompt.

| ID | Phase | Decision | Why |
|---|---|---|---|
| D-001 | 0 | Blender 4.4.3 (the portable build already on this PC), not 5.2 LTS. All scripts target the 4.4 Python API. | The brief says ask before installing software. 4.4.3 does everything needed. |
| D-002 | 0 | The master build prompt stays local and is git-ignored. | The brief's layout puts it in the repo, but it names the inspirations, which rule 5 bans from repo text. |
| D-003 | 0 | Every script-facing number is in millimetres; geometry is stored in metres; the conversion happens once, in `obj_from_bm`. Objects keep identity transforms. | GLB exports at true scale and "apply all transforms" is true by construction. |
| D-004 | 0 | Bevels run on edge weights, not on angle. Panel gaps get their lip chamfer from the cutter profile. | An angle-limited bevel would try to bevel every boolean cut and collapse 1.5 mm grooves. |
| D-005 | 0 | Fasteners: one named part per set (copies of one master mesh joined), not one object per screw. | Keeps the part tree readable and the node count sane. Rules for size, spacing and counterbores live in `mech.fasteners`. |
| D-006 | 0 | The decal atlas is rendered inside Blender from text objects set in Saira Stencil One (OFL). | Reproducible from a clean checkout with no external rasteriser. |
| D-007 | 0 | Review renders use Cycles on OptiX throughout. | A frame takes one to three seconds on the RTX 4070 SUPER, and bevel highlights are trustworthy. |
| D-008 | 2 | Hand has six degrees of freedom: thumb opposition, thumb flexion, three finger flexions, one ganged finger splay. | The brief lists five and counts six. |
| D-009 | 2 | Knee actuators sit behind the thigh, either side of the centreline, driving a crank lug at the top rear of the shin (about 85 mm arm). | "One each side" on the outside of the knee would not fit between the legs at 240 mm hip spacing. |
| D-010 | 2 | The hip pitch actuator is a Ø174 drum forming the top of the thigh. | As outboard discs they read as ears on the pelvis. |
| D-011 | 2 | Thighs 212 mm and shins 190 mm wide, the most the hip spacing allows. | The first blockout had slim legs and read as a lab humanoid. |
| D-012 | 2 | Everything above the waist sits 30 mm forward of the hip axes; the ankle sits 10 mm further forward in the foot. | Backpack and cannon put the mass centre near the heels otherwise. A pure translation keeps the orthographic views square. |
| D-013 | 2 | Cap crown is about 101 mm tall, not 110. | Slit centre (1,620) and crown top (1,730) are fixed, and the cap's front edge has to clear the slit. |
| D-014 | 2 | Mount is a swing arm: trunnion at z = 1,515 mm behind the right shoulder, bore 125 mm above it. | With the trunnion through the breech the stowed cannon stood beside the head, hid the cap brim in side silhouette and was 2,300 mm tall. |
| D-015 | 2 | Barrel 500 mm; stowed overall height measures 2,115 mm. | The brief asks for a 750 mm barrel and about 2,050 mm overall. With the barrel level above the shoulder armour those cannot both hold. 440 mm gives 2,055; 750 gives 2,365. Variants rendered for G1. |
| D-016 | 2 | Yoke has one cheek, outboard. Cradle (guide rods, recoil unit) rides on top of the barrel. Feed box is the only thing inboard of the breech. | Keeps the head side clear through ±25° traverse and the underside clear of the shoulder armour. |
| D-017 | 2 | Right pauldron is 12 mm lower than the left and cut back at the rear to y = −10 mm. Left is larger: 356 mm against 344 mm from the centreline, longer skirt, rear cheek. | Clears the barrel at −5° and the pivot housing in traverse. The brief asks for this asymmetry. |
| D-018 | 2 | Faceplate is 148 mm wide at the brow with 14 mm corner chamfers. | Barrel clearance to the head at full inboard traverse was 3.5 mm with a 160 mm plate. |
| D-019 | 2 | The sweep check covers elevation −5° to 90° at zero traverse and traverse ±25° at both 0° and −5°. | More than the brief asks (it asks for traverse at 0° only). The mount should not need a software interlock to avoid its own robot. |
| D-020 | 2 | GitHub repository created at Phase 2 as private; it goes public at Phase 12 for Pages. | Paul asked for the repository now. The brief schedules publication after G3. |
| D-021 | G1 | Paul approved the blockout with four changes, all "match the concept art": stance about 425 mm between the feet (hip axes 270 mm, legs abducted 5.5°), feet 330 × 195 mm, shoulder armour 780 mm over 520 mm shoulder axes, barrel 455 mm. | Gate G1 outcome. Stowed height now measures 2,050 mm. |
| D-022 | 3 | Breech shortened to 190 × 164 × 176 mm. | With a 455 mm barrel the brief's breech made the cannon read as a box with a lens. |
| D-023 | 3 | After G1 Paul asked for far more intricacy, to the level of the concept art. Detail target raised: every assembly carries its real mechanism, carriers, fasteners and harness; part count is allowed past 500. | Paul's feedback on seeing the blockout. |
| D-024 | 3 | Armour is built as one rounded-section shell per limb segment, opened where mechanism shows, sliced into panels by 2 mm gap cuts, and lined with carbon ribs on aluminium standoffs. | One method for all seventeen assemblies; gives real thickness, even gaps and visible structure behind them. |
| D-025 | 3 | Knee: fork with an open corridor, crank pin 70 mm from the axis, phased so the lever arm is 40 mm at both ends of a 0 to 110° range and 70 mm in the middle; 115 mm stroke. Knee range is 110°, not 120°. | The first crank lost its lever arm near 90° because the actuator line passed through the joint centre. |
| D-026 | 3 | Neck: roll ears hang from the head and swing into the bore of the yaw ring. Ranges: yaw ±70°, pitch ±15°, roll ±12°. | Only 55 mm of height between the thorax deck and the skull. |
| D-027 | 3 | Sensor glass is transmissive (smoked), not opaque. | The slit emitter and the cameras have to be visible behind the window. |
| D-028 | 3 | Edge wear comes from a bevel-normal mask restricted to convex edges, not from pointiness alone. | Pointiness marked every smoothly curved panel as an edge and blotched the cap. |
| D-029 | 3 | The energy chain is one mesh with a shape key between the level and stowed poses; `poses.set_mount` drives it. | It links the elevating breech to the fixed backpack, so it has to deform; a morph target exports to glTF. |
| D-030 | 3 | Hero rig keeps the rim lights off the floor with light linking. | They pooled on the floor in front of the robot. |
| D-031 | 3 | Exploded view is two stages on a parent Empty per assembly: the Empty carries the stage 1 offset, each part its stage 2 offset, radial from the assembly's spine line. | Matches the brief's two stages and gives removal-direction motion instead of a blanket scale-up. |
| D-032 | 3 | Battery service door is on the backpack's left side panel, not the rear. | The rear face is taken by two blowers, two radiator grilles and the sight glass. |
