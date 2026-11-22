// Plays a movement on the rig: keyed joint angles, eased from key to key the
// way a servo drive ramps (minimum jerk), always ending back at rest.

import type { Rig } from './rig';

/** Channel → value. Joints in degrees; `drop`, `sway`, `surge` and `recoil` in millimetres. */
export type Pose = Record<string, number>;

export interface Clip {
  id: string;
  label: string;
  /** [seconds, pose]. A channel holds its last keyed value until it is keyed again. */
  keys: [number, Pose][];
  /** Effects that run on the clip's clock. */
  fx?: 'intercept';
}

/** Something that runs alongside a clip (the missile and the shot). */
export interface Effect {
  update(t: number, dt: number): void;
  stop(): void;
}

const MOUNT = ['mount_elevation', 'mount_traverse'];
const jerk = (u: number) => u * u * u * (10 - 15 * u + 6 * u * u);

export class Player {
  /** Mount angles while a clip drives the cannon; null leaves it to the controls. */
  mount: { elev: number; trav: number } | null = null;
  effect: Effect | null = null;
  onEnd: (() => void) | null = null;

  private tracks = new Map<string, [number, number][]>();
  private values: Pose = {};
  private t = 0;
  private end = 0;
  private playing: Clip | null = null;
  private held = false;

  constructor(private rig: Rig) {}

  get current(): string | null {
    return this.playing?.id ?? null;
  }

  /** Start a clip from wherever the robot is now. */
  play(clip: Clip, mount: { elev: number; trav: number }): void {
    this.effect?.stop();
    const last = clip.keys[clip.keys.length - 1]![0];
    this.end = last + 1.0;
    this.tracks.clear();
    const from: Pose = { ...this.values, mount_elevation: mount.elev, mount_traverse: mount.trav };
    clip.keys.forEach(([t, pose], n) => {
      // A key is a move that starts when the key before it has been reached.
      const prev = n > 0 ? clip.keys[n - 1]![0] : 0;
      for (const [ch, v] of Object.entries(pose)) {
        let tr = this.tracks.get(ch);
        if (!tr) this.tracks.set(ch, (tr = [[0, from[ch] ?? 0]]));
        const at = tr[tr.length - 1]!;
        if (at[0] < prev - 1e-6) tr.push([prev, at[1]]);
        tr.push([t, v]);
      }
    });
    // Whatever was left over from a movement that was cut short goes home too.
    for (const ch of Object.keys(this.values)) if (!this.tracks.has(ch) && !MOUNT.includes(ch)) this.tracks.set(ch, [[0, this.values[ch]!]]);
    for (const [ch, tr] of this.tracks) if (!MOUNT.includes(ch)) tr.push([last, tr[tr.length - 1]![1]], [this.end, 0]);
    this.t = 0;
    this.playing = clip;
    this.held = false;
  }

  /** Cut the movement short and ease home. */
  stop(): void {
    if (!this.playing && !this.held) return;
    this.effect?.stop();
    this.play({ id: '', label: '', keys: [[0.1, {}]] }, this.mount ?? { elev: 0, trav: 0 });
    this.tracks.delete('mount_elevation');
    this.tracks.delete('mount_traverse');
    this.mount = null;
  }

  /** Drop everything and stand at rest, at once. */
  reset(): void {
    this.effect?.stop();
    this.playing = null;
    this.held = false;
    this.mount = null;
    this.values = {};
    this.apply();
    this.rig.settle();
  }

  /** Freeze in a given pose (diagnostics). */
  hold(pose: Pose): void {
    this.playing = null;
    this.held = true;
    this.values = { ...pose };
    this.apply();
  }

  /** Advance; true while something is moving. */
  step(dt: number): boolean {
    const clip = this.playing;
    if (!clip) return false;
    this.t += dt;
    for (const [ch, tr] of this.tracks) {
      let i = 1;
      while (i < tr.length - 1 && tr[i]![0] < this.t) i++;
      const a = tr[i - 1]!;
      const b = tr[i] ?? a;
      const u = b[0] > a[0] ? Math.min(1, Math.max(0, (this.t - a[0]) / (b[0] - a[0]))) : 1;
      this.values[ch] = a[1] + (b[1] - a[1]) * jerk(u);
    }
    if (clip.fx) this.effect?.update(this.t, dt);
    const drives = this.tracks.has('mount_elevation');
    this.mount = drives && this.t < this.end ? { elev: this.values.mount_elevation ?? 0, trav: this.values.mount_traverse ?? 0 } : null;
    this.apply();
    if (this.t >= this.end) {
      this.playing = null;
      this.mount = null;
      this.values = {};
      this.apply();
      this.rig.settle();
      if (clip.fx) this.effect?.stop();
      if (clip.id) this.onEnd?.();
    }
    return true;
  }

  private apply(): void {
    const v = this.values;
    const rig = this.rig;
    rig.angles = {};
    for (const j of rig.joints) {
      if (v[j] === undefined) continue;
      const [lo, hi] = rig.range(j);
      rig.angles[j] = Math.min(hi, Math.max(lo, v[j]!));
    }
    // Model axes to scene axes: forward is +Z, the robot's left is +X.
    rig.offset.set((v.sway ?? 0) / 1000, -(v.drop ?? 0) / 1000, (v.surge ?? 0) / 1000);
    rig.recoil = (v.recoil ?? 0) / 1000;
    rig.solve();
  }
}
