// The movements the robot can be asked to make. Angles are degrees in the
// sense of the specification's joint ranges; a value keyed without a side
// suffix through `both` goes to the left and the right joint alike.

import type { Clip, Pose } from './animate';

/** Intercept, clip seconds: the shot leaves the muzzle, the shot arrives. */
export const T_FIRE = 4.6;
export const T_HIT = T_FIRE + 0.24;
/** Where the cannon points when it fires: degrees to the robot's left, degrees up; metres to the meeting point. */
export const AIM = { yaw: -24, elev: 21, range: 34 };

const side = (s: 'L' | 'R', p: Pose): Pose => Object.fromEntries(Object.entries(p).map(([k, v]) => [`${k}_${s}`, v]));
const L = (p: Pose) => side('L', p);
const R = (p: Pose) => side('R', p);
const both = (p: Pose) => ({ ...L(p), ...R(p) });

const fingers = (v: number): Pose => ({ finger1_flexion: v, finger2_flexion: v, finger3_flexion: v });
const FIST: Pose = { ...fingers(72), thumb_flexion: 42, thumb_opposition: 46, finger_splay: 0 };
const OPEN: Pose = { ...fingers(-30), thumb_flexion: -22, thumb_opposition: 0, finger_splay: 6 };
const RELAXED: Pose = { ...fingers(0), thumb_flexion: 0, thumb_opposition: 0, finger_splay: 0 };
/** Knees bent by `k` degrees with the feet flat and the pelvis level. */
const stance = (k: number): Pose => both({ hip_pitch: -k / 2, knee_pitch: k, ankle_pitch: -k / 2 });

// Fingers drumming: each one a beat behind its neighbour.
const flutter = (from: number, to: number, beat: number): [number, Pose][] => {
  const keys: [number, Pose][] = [];
  for (let i = 0, t = from; t < to; i++, t += beat) {
    const f = (n: number) => ((i + n) % 3 === 0 ? 22 : -30);
    keys.push([t, both({ finger1_flexion: f(0), finger2_flexion: f(1), finger3_flexion: f(2), thumb_flexion: i % 2 ? 10 : -22 })]);
  }
  return keys;
};

export const CLIPS: Clip[] = [
  {
    id: 'look',
    label: 'Look around',
    keys: [
      [0.9, { neck_yaw: 48, neck_pitch: 4, waist_yaw: 14, ...both({ shoulder_pitch: 4 }) }],
      [1.9, { neck_yaw: 48, neck_roll: 6 }],
      [3.3, { neck_yaw: -52, neck_pitch: 8, neck_roll: 0, waist_yaw: -18 }],
      [4.3, { neck_yaw: -52, neck_roll: -6 }],
      [5.4, { neck_yaw: 0, neck_pitch: -14, neck_roll: 0, waist_yaw: 0, waist_pitch: -6 }],
      [6.3, { neck_pitch: -14 }],
      [7.2, { neck_pitch: 12, waist_pitch: 8 }],
      [8.0, { neck_pitch: 12 }],
    ],
  },
  {
    id: 'check',
    label: 'Function check',
    keys: [
      [1.0, both({ shoulder_roll: 45 })],
      [1.9, both({ elbow_pitch: 110, forearm_roll: 70 })],
      [2.7, both({ forearm_roll: -70, ...FIST })],
      [3.4, both({ ...OPEN, wrist_pitch: 40 })],
      [4.0, both({ wrist_pitch: -40 })],
      [4.8, both({ wrist_pitch: 0, forearm_roll: 0, elbow_pitch: 0, shoulder_roll: 0, shoulder_pitch: -90, ...RELAXED })],
      [5.7, both({ shoulder_pitch: 0 })],
      [6.5, { waist_yaw: 38, neck_yaw: 20 }],
      [7.7, { waist_yaw: -38, neck_yaw: -20 }],
      [8.5, { waist_yaw: 0, neck_yaw: 0, waist_pitch: 24 }],
      [9.3, { waist_pitch: -10 }],
      [9.9, { waist_pitch: 0, ...stance(0) }],
      [11.2, { ...stance(100), waist_pitch: 14, ...both({ shoulder_pitch: -50, elbow_pitch: 25 }) }],
      [11.9, stance(100)],
      [13.1, { ...stance(0), waist_pitch: 0, ...both({ shoulder_pitch: 0, elbow_pitch: 0 }) }],
    ],
  },
  {
    id: 'squat',
    label: 'Squat',
    keys: [
      [1.3, { ...stance(105), waist_pitch: 16, neck_pitch: -8, ...both({ shoulder_pitch: -62, elbow_pitch: 28 }) }],
      [1.9, stance(105)],
      [3.0, { ...stance(12), waist_pitch: 2, ...both({ shoulder_pitch: -10, elbow_pitch: 10 }) }],
      [4.3, { ...stance(105), waist_pitch: 16, ...both({ shoulder_pitch: -62, elbow_pitch: 28 }) }],
      [5.2, stance(105)],
      [6.4, { ...stance(0), waist_pitch: 0, neck_pitch: 0, ...both({ shoulder_pitch: 0, elbow_pitch: 0 }) }],
    ],
  },
  {
    id: 'wave',
    label: 'Wave',
    keys: [
      [1.1, { ...L({ shoulder_roll: 78, shoulder_yaw: 88, elbow_pitch: 88, ...OPEN }), neck_yaw: 14, neck_roll: -5, waist_yaw: 6 }],
      [1.5, L({ elbow_pitch: 112 })],
      [1.9, L({ elbow_pitch: 68 })],
      [2.3, L({ elbow_pitch: 112 })],
      [2.7, L({ elbow_pitch: 68 })],
      [3.1, L({ elbow_pitch: 112 })],
      [3.5, L({ elbow_pitch: 88 })],
      [3.8, L({ elbow_pitch: 88 })],
    ],
  },
  {
    id: 'fistbump',
    label: 'Fist bump',
    keys: [
      // fists up in front of the chest
      [1.0, { ...both({ shoulder_pitch: -45, shoulder_yaw: -30, elbow_pitch: 88, ...FIST }), neck_pitch: 9 }],
      [1.3, both({ shoulder_yaw: -22 })],
      [1.45, both({ shoulder_yaw: -53 })],
      [1.6, both({ shoulder_yaw: -49 })],
      [1.95, both({ shoulder_yaw: -49, ...FIST })],
      // and apart: hands burst open and the fingers flutter as they fall away
      [2.3, { ...both({ shoulder_yaw: -18, shoulder_roll: 30, shoulder_pitch: -52, elbow_pitch: 72, forearm_roll: 30, ...OPEN, finger_splay: 8 }), neck_pitch: 2 }],
      ...flutter(2.42, 4.3, 0.13),
      [4.3, both({ shoulder_yaw: 4, shoulder_roll: 46, shoulder_pitch: -34, elbow_pitch: 56 })],
      [4.5, both(OPEN)],
    ],
  },
  {
    id: 'fistpalm',
    label: 'Fist to palm',
    keys: [
      // settle into a stance, left palm out in front, right fist drawn back
      [1.1, {
        ...stance(26),
        waist_pitch: 5,
        neck_pitch: 7,
        ...L({ shoulder_pitch: -40, shoulder_roll: 4, shoulder_yaw: -46, elbow_pitch: 100, ...OPEN, finger_splay: 3 }),
        ...R({ shoulder_pitch: -30, shoulder_roll: 40, shoulder_yaw: -10, elbow_pitch: 110, ...FIST }),
      }],
      [1.5, { ...R({ shoulder_yaw: -4 }), ...L(fingers(-30)) }],
      // the fist lands in the palm
      [1.66, { ...R({ shoulder_pitch: -49, shoulder_roll: -8, shoulder_yaw: -68, elbow_pitch: 88 }), ...L(fingers(-30)), waist_yaw: 4 }],
      [1.78, { ...L({ shoulder_yaw: -49, ...fingers(10), thumb_flexion: 8 }), ...R({ shoulder_yaw: -70 }), waist_yaw: 2 }],
      [2.4, R({ forearm_roll: 16 })],
      [3.0, R({ forearm_roll: -12 })],
      [3.5, R({ forearm_roll: 0 })],
      [3.9, { neck_pitch: 0 }],
    ],
  },
  {
    id: 'intercept',
    label: 'Intercept',
    fx: 'intercept',
    keys: [
      // head finds it first, then the cannon comes down and the body turns to bring it on
      [0.5, { neck_yaw: -26, neck_pitch: -11 }],
      [2.8, {
        mount_elevation: AIM.elev + 9,
        mount_traverse: 0,
        waist_yaw: AIM.yaw + 5,
        neck_yaw: -8,
        ...stance(30),
        ...both({ elbow_pitch: 22, shoulder_roll: 8, ...FIST }),
      }],
      [T_FIRE - 0.5, { mount_elevation: AIM.elev, waist_yaw: AIM.yaw, neck_yaw: -4, neck_pitch: -12 }],
      [T_FIRE, { mount_elevation: AIM.elev, recoil: 0, waist_pitch: 0, ...stance(30) }],
      // the shot: barrel runs back in its cradle, the body takes the rest
      [T_FIRE + 0.06, { recoil: 75, mount_elevation: AIM.elev + 2.5, waist_pitch: -4.5, ...stance(38) }],
      [T_FIRE + 0.75, { recoil: 0, mount_elevation: AIM.elev, waist_pitch: 0, ...stance(30) }],
      [T_FIRE + 3.0, { neck_pitch: -12 }],
      [T_FIRE + 4.8, { mount_elevation: 90, waist_yaw: 0, neck_yaw: 0, neck_pitch: 0, ...stance(0), ...both({ elbow_pitch: 0, shoulder_roll: 0, ...RELAXED }) }],
    ],
  },
];
