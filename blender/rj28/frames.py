"""Joint frames of the neutral pose, derived from params. Everything in mm.

Shared by the blockout and by every assembly module so that limbs, armour
and mechanisms all hang off the same axes.
"""
import math

from mathutils import Matrix, Vector

from . import params as PR
from .lib.core import T, R, frame


def torso():
    """Offset of everything above the waist."""
    return T(0, PR.TORSO_Y, 0)


def leg(s):
    """(hip, thigh, knee, shin, ankle, foot) frames for side s (+1 left, -1 right).

    hip:   at the hip centre, yawed by toe-out and rolled by the leg abduction.
    thigh: hip pitched forward by half the knee flexion; -Z runs down the thigh.
    knee:  at the knee axis (local X), thigh orientation.
    shin:  knee flexed; -Z runs down the shin.
    ankle: at the ankle centre, shin orientation.
    foot:  at the ankle centre, level, yawed by toe-out; -Y is foot-forward.
    """
    hip = T(s * PR.HX, 0, PR.Z_HIP) @ R("Z", s * PR.TOE_OUT) @ R("Y", -s * PR.LEG_ABDUCT)
    thigh = hip @ R("X", -PR.KNEE_FLEX / 2)
    knee = thigh @ T(0, 0, -PR.THIGH)
    shin = knee @ R("X", PR.KNEE_FLEX)
    ankle = shin @ T(0, 0, -PR.SHIN)
    foot = T(*ankle.translation) @ R("Z", s * PR.TOE_OUT)
    return hip, thigh, knee, shin, ankle, foot


def arm(s):
    """(shoulder point, upper arm, forearm, hand) for side s, before the torso offset.

    upper: origin at the shoulder centre, +Z up the arm, X lateral, Y back.
    fore:  origin at the elbow, -Z down the forearm.
    hand:  origin at the wrist, forearm orientation.
    """
    a = math.radians(PR.ARM_ABDUCT)
    d_u = Vector((s * math.sin(a), 0, -math.cos(a)))
    sv = Vector((s * PR.SX, 0, PR.Z_SHOULDER))
    upper = frame(sv, -d_u, (1, 0, 0))
    fore = upper @ T(0, 0, -PR.UPPER_ARM) @ R("X", -PR.ELBOW_FLEX)
    hand = fore @ T(0, 0, -PR.FOREARM)
    return sv, upper, fore, hand


def cannon():
    """Frame on the bore axis above the trunnion, level pose: +Z forward along
    the bore, +Y up, +X inboard."""
    return T(PR.BORE_X, PR.TRUNNION_Y, PR.TRUNNION_Z + PR.BORE_RISE) @ R("X", 90)


def side_plate():
    """Rotation for plates drawn in (forward, up) and extruded outboard (-X)."""
    return R("Z", -90) @ R("X", 90)
