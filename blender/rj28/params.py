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
SHOULDER_SPAN = 480.0            # axis to axis
ARMOUR_SPAN = 700.0              # over shoulder armour
PAULDRON_L_OUT = 356.0           # left armour is the larger one
PAULDRON_R_OUT = ARMOUR_SPAN - PAULDRON_L_OUT
HIP_SPAN = 240.0
CHEST_DEPTH = 330.0
CHEST_TO_PACK = 460.0
UPPER_ARM = 310.0
FOREARM = 280.0
HAND = 195.0
FOOT_L, FOOT_W = 310.0, 135.0

# ── pose (section 2.5) ───────────────────────────────────────────────────────
TOE_OUT = 6.0
KNEE_FLEX = 4.0
ARM_ABDUCT = 12.0
ELBOW_FLEX = 10.0

TORSO_Y = -30.0                  # waist and everything above it sit forward of the hip axes
FOOT_SHIFT = 10.0                # ankle sits this much further forward in the foot

SX = SHOULDER_SPAN / 2
HX = HIP_SPAN / 2
THIGH = (Z_HIP - Z_KNEE) / math.cos(math.radians(KNEE_FLEX / 2))
SHIN = (Z_KNEE - Z_ANKLE) / math.cos(math.radians(KNEE_FLEX / 2))

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
BARREL_L = 500.0                 # see docs/DECISIONS.md D-015 (brief says 750 and ~2,050 overall; they conflict)
BREECH_W, BREECH_H = 170.0, 190.0
BREECH_FWD, BREECH_AFT = 100.0, 130.0            # breech extent either side of the trunnion
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
