"""Every design dimension of the RJ-28, in millimetres and degrees.

Axes: Z up, robot faces -Y, robot's left is +X, origin on the floor between
the feet. These are the targets the model is built to; published numbers come
from measure.py reading the finished mesh, never from this file.
"""
import math

# ── landmark heights (section 2.4) ───────────────────────────────────────────
Z_ANKLE = 95.0
Z_KNEE = 500.0
Z_HIP = 905.0
Z_WAIST = 1060.0
Z_SHOULDER = 1430.0
Z_NECK = 1500.0
Z_SLIT = 1620.0
Z_CROWN = 1730.0

# ── widths and lengths ───────────────────────────────────────────────────────
SHOULDER_SPAN = 520.0            # axis to axis (G1: matched to the concept art; brief 480)
ARMOUR_SPAN = 780.0              # over shoulder armour (G1: concept art; brief 700)
PAULDRON_L_OUT = 398.0           # left armour is the larger one
PAULDRON_R_OUT = ARMOUR_SPAN - PAULDRON_L_OUT
PAULDRON_TOP_Z = 1560.0          # top of the left shoulder armour
PAULDRON_R_DROP = 18.0           # right armour sits lower, under the barrel
HIP_SPAN = 270.0                 # G1: concept art stance; brief 240
CHEST_DEPTH = 330.0
CHEST_TO_PACK = 460.0
UPPER_ARM = 310.0
FOREARM = 280.0
HAND = 195.0
FOOT_L, FOOT_W = 330.0, 195.0    # G1: concept art; brief 310 x 135

# ── pose (section 2.5) ───────────────────────────────────────────────────────
TOE_OUT = 6.0
LEG_ABDUCT = 5.5                 # G1: hip roll that puts the feet about 425 mm apart, as in the concept art
KNEE_FLEX = 4.0
ARM_ABDUCT = 12.0
ELBOW_FLEX = 10.0

TORSO_Y = -30.0                  # waist and everything above it sit forward of the hip axes

SX = SHOULDER_SPAN / 2
HX = HIP_SPAN / 2
_LEG_COS = math.cos(math.radians(KNEE_FLEX / 2)) * math.cos(math.radians(LEG_ABDUCT))
THIGH = (Z_HIP - Z_KNEE) / _LEG_COS
SHIN = (Z_KNEE - Z_ANKLE) / _LEG_COS

# ── knee crank (see assemblies/leg.py) ───────────────────────────────────────
KNEE_RANGE = 110.0               # flexion, degrees
KNEE_CRANK = 70.0                # crank pin radius about the knee axis

# ── torso envelope ───────────────────────────────────────────────────────────
CHEST_FRONT_Y = -190.0           # outer face of the pectoral armour
THORAX_BACK_Y = 140.0
PACK_BACK_Y = CHEST_FRONT_Y + CHEST_TO_PACK      # 270
PACK_HALF_W = 165.0
PACK_Z0, PACK_Z1 = 1150.0, 1480.0

# ── head and cap (section 4.1) ───────────────────────────────────────────────
FACE_RAKE = 12.0
SLIT_W, SLIT_H, SLIT_RECESS = 120.0, 9.0, 6.0
CAP_W, CAP_L = 205.0, 225.0
CAP_FRONT_Z, CAP_REAR_Z = 1637.0, 1613.0         # crown base: sits back on the head
CAP_Y = 2.0
CAP_SHELL = 4.0
CAP_BUTTON_D, CAP_BUTTON_H = 38.0, 9.0
BRIM_L, BRIM_W, BRIM_T, BRIM_RAKE = 72.0, 175.0, 4.0, 12.0
SEAM_W, SEAM_D = 1.5, 2.0

# ── interceptor mount (section 4.6) ──────────────────────────────────────────
# Single main trunnion axis, parallel to X, low behind the right shoulder. The cannon
# rides BORE_RISE above it on a swing arm. Elevation 0 deg = barrel level pointing -Y
# (deployed), 90 deg = barrel vertical behind the shoulder (stowed).
BORE_X = -292.0
TRUNNION_Y = 160.0
TRUNNION_Z = 1515.0
BORE_RISE = 125.0                # bore axis above the trunnion axis when level
ELEV_MIN, ELEV_MAX = -5.0, 90.0
TRAVERSE = 25.0
BARREL_OD = 110.0
BARREL_L = 455.0                 # see docs/DECISIONS.md D-015/D-021 (G1: short barrel as in the concept art, 2,050 overall)
BREECH_W, BREECH_H = 164.0, 176.0
BREECH_FWD, BREECH_AFT = 80.0, 110.0            # breech extent either side of the trunnion
CLEARANCE_MIN = 15.0
SLEW_OD = 170.0
YOKE_DROP = 121.0                # trunnion axis down to the top of the yoke base

# ── engineering targets that cannot be measured (section 3) ──────────────────
MASS_READY_KG = 185.0
MASS_BATTERY_KG = 23.0
MASS_MOUNT_KG = 22.0
PACK_VOLTAGE = 96.0
PACK_KWH = 5.0
AVG_DRAW_KW = 2.0
DOF = dict(legs=12, waist=2, arms=14, hands=12, neck=3, mount=3)
SERIAL = "RJ28-M1-0001"
