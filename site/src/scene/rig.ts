// The kinematic rig: joint angles in, a matrix for every part out.
//
// rig.json (written from the model) says which link each part rides, where the
// pivots are, which actuators span two links, and which cables and boots bend
// across joints. Angles are degrees in the sense of the specification's ranges.
// Everything here is relative to the rest pose, so a rig at rest is all identity.

import * as THREE from 'three';
import data from '../data/rig.json';

const DEG = Math.PI / 180;
const BUCKETS = 24;
type Vec3 = number[];
/** Model millimetres (Z up, faces −Y) → scene metres (Y up, faces +Z). */
const point = (a: Vec3) => new THREE.Vector3(a[0]! / 1000, a[2]! / 1000, -a[1]! / 1000);
const direction = (a: Vec3) => new THREE.Vector3(a[0]!, a[2]!, -a[1]!).normalize();
const smooth = (v: number) => {
  const t = Math.min(1, Math.max(0, v));
  return t * t * (3 - 2 * t);
};

interface Link {
  name: string;
  parent: number;
  joint: string | null;
  gain: number;
  pivot: THREE.Vector3;
  axis: THREE.Vector3;
  world: THREE.Matrix4;
}
interface Act {
  a: number;
  b: number;
  pa: THREE.Vector3;
  pb: THREE.Vector3;
  d0: THREE.Vector3;
  len0: number;
  len: number;
  body: THREE.Matrix4;
  rod: THREE.Matrix4;
}
interface FlexDef {
  part: string;
  base?: number;
  dir?: Vec3;
  spans?: { links: number[]; u: number[] }[];
  act?: number;
  nearest?: { link: number; at: Vec3 }[];
}
interface FlexMesh {
  mesh: THREE.Mesh;
  inv: THREE.Matrix4 | null;
  rest: Float32Array;
  restN: Float32Array | null;
  bucket: Uint8Array;
}
interface Flex {
  def: FlexDef;
  meshes: FlexMesh[];
  mats: THREE.Matrix4[];
  last: Float32Array;
}

/** How one part is carried. */
export interface Bound {
  link: number;
  act: number;
  /** 1 body, 2 rod, 3 bellows. */
  role: 0 | 1 | 2 | 3;
  flex: boolean;
  recoil: boolean;
  /** Bellows: the end fixed to the actuator body, and the length along the actuator. */
  anchor?: THREE.Vector3;
  span?: number;
}

const raw = data as unknown as {
  links: { name: string; parent: number; joint: string | null; gain: number; pivot?: Vec3; axis?: Vec3 }[];
  joints: Record<string, [number, number]>;
  parts: Record<string, number>;
  actuators: { a: number; b: number; pa: Vec3; pb: Vec3; body: string[]; rod: string[]; bellows: string[] }[];
  flex: FlexDef[];
  recoil: string[];
  feet: Record<string, Vec3>;
};

const _m = new THREE.Matrix4();
const _t = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _v = new THREE.Vector3();

export class Rig {
  readonly links: Link[] = raw.links.map((l) => ({
    name: l.name,
    parent: l.parent,
    joint: l.joint,
    gain: l.gain,
    pivot: l.pivot ? point(l.pivot) : new THREE.Vector3(),
    axis: l.axis ? direction(l.axis) : new THREE.Vector3(0, 1, 0),
    world: new THREE.Matrix4(),
  }));
  readonly joints = Object.keys(raw.joints);
  /** Degrees per joint; missing means zero. */
  angles: Record<string, number> = {};
  /** Extra travel of the pelvis, metres, on top of what keeps the feet where they are. */
  offset = new THREE.Vector3();
  /** Barrel recoil along the bore, metres. */
  recoil = 0;
  /** False while every joint is at rest: the scene can skip the rig altogether. */
  active = false;

  private acts: Act[] = raw.actuators.map((a) => {
    const pa = point(a.pa);
    const pb = point(a.pb);
    return { a: a.a, b: a.b, pa, pb, d0: pb.clone().sub(pa).normalize(), len0: pa.distanceTo(pb), len: pa.distanceTo(pb), body: new THREE.Matrix4(), rod: new THREE.Matrix4() };
  });
  private role = new Map<string, { act: number; role: 1 | 2 | 3 }>();
  private flexDef = new Map<string, FlexDef>();
  private flexes: Flex[] = [];
  private feet = Object.values(raw.feet).map(point);
  private footLinks = ['foot_L', 'foot_R'].map((n) => raw.links.findIndex((l) => l.name === n));
  private recoilSet = new Set(raw.recoil);
  /** Part number of the muzzle ring: where the shot leaves. */
  readonly muzzle = raw.recoil[raw.recoil.length - 1]!;

  constructor() {
    raw.actuators.forEach((a, i) => {
      for (const p of a.body) this.role.set(p, { act: i, role: 1 });
      for (const p of a.rod) this.role.set(p, { act: i, role: 2 });
      for (const p of a.bellows) this.role.set(p, { act: i, role: 3 });
    });
    for (const f of raw.flex) this.flexDef.set(f.part, f);
  }

  /** Limits of a joint, degrees. Fingers may also open flat from their relaxed curl. */
  range(joint: string): [number, number] {
    const r = raw.joints[joint] ?? [-180, 180];
    return /finger\d_flexion|thumb_flexion/.test(joint) ? [-34, r[1]] : r;
  }

  /** The joint's own turn, scaled by `w`, about its rest-pose pivot. */
  private local(l: Link, w: number, out: THREE.Matrix4): THREE.Matrix4 {
    const a = (this.angles[l.joint!] ?? 0) * l.gain * w * DEG;
    out.makeRotationAxis(l.axis, a);
    _v.copy(l.pivot).applyMatrix4(out);
    return out.setPosition(l.pivot.x - _v.x, l.pivot.y - _v.y, l.pivot.z - _v.z);
  }

  private chain(): void {
    for (const l of this.links) {
      if (l.parent < 0) continue;
      const parent = this.links[l.parent]!.world;
      if (l.joint) l.world.multiplyMatrices(parent, this.local(l, 1, _m));
      else l.world.copy(parent);
    }
  }

  /** Angles → link, actuator and cable matrices. */
  solve(): void {
    const root = this.links[0]!.world.identity();
    this.active = this.recoil !== 0 || this.offset.lengthSq() > 0;
    for (const j of this.joints) if (Math.abs(this.angles[j] ?? 0) > 1e-4) this.active = true;
    if (!this.active) {
      for (const l of this.links) l.world.identity();
    } else {
      // Feet stay where they stand: whatever the legs do moves the pelvis instead.
      this.chain();
      const d = new THREE.Vector3();
      this.footLinks.forEach((li, i) => d.add(_v.copy(this.feet[i]!).applyMatrix4(this.links[li]!.world).sub(this.feet[i]!)));
      d.multiplyScalar(-1 / this.footLinks.length).add(this.offset);
      root.makeTranslation(d);
      this.chain();
    }
    for (const a of this.acts) {
      const A = this.links[a.a]!.world;
      const pa = a.pa.clone().applyMatrix4(A);
      const pb = a.pb.clone().applyMatrix4(this.links[a.b]!.world);
      const ra = new THREE.Quaternion().setFromRotationMatrix(A);
      const dn = pb.clone().sub(pa);
      a.len = dn.length();
      _q.setFromUnitVectors(a.d0.clone().applyQuaternion(ra), dn.normalize()).multiply(ra);
      a.body.makeRotationFromQuaternion(_q);
      _v.copy(a.pa).applyMatrix4(a.body);
      a.body.setPosition(pa.x - _v.x, pa.y - _v.y, pa.z - _v.z);
      a.rod.makeRotationFromQuaternion(_q);
      _v.copy(a.pb).applyMatrix4(a.rod);
      a.rod.setPosition(pb.x - _v.x, pb.y - _v.y, pb.z - _v.z);
    }
    for (const f of this.flexes) this.deform(f);
  }

  /** Forget the meshes of a model that is being replaced. */
  reset(): void {
    this.flexes = [];
  }

  bind(number: string, node: THREE.Object3D, meshes: THREE.Mesh[]): Bound {
    const b: Bound = { link: raw.parts[number] ?? -1, act: -1, role: 0, flex: false, recoil: this.recoilSet.has(number) };
    const r = this.role.get(number);
    if (r) {
      b.act = r.act;
      b.role = r.role;
      if (r.role === 3) {
        // Bellows: measured along the actuator, fixed at the end nearer the body pin.
        const a = this.acts[r.act]!;
        let lo = Infinity;
        let hi = -Infinity;
        for (const mesh of meshes) {
          const pos = mesh.geometry.getAttribute('position');
          for (let i = 0; i < pos.count; i += 3) {
            _v.fromBufferAttribute(pos, i);
            if (mesh !== node) _v.applyMatrix4(mesh.matrix);
            const u = _v.sub(a.pa).dot(a.d0);
            lo = Math.min(lo, u);
            hi = Math.max(hi, u);
          }
        }
        b.anchor = a.pa.clone().addScaledVector(a.d0, lo);
        b.span = Math.max(0.005, hi - lo);
      }
    }
    const def = this.flexDef.get(number);
    if (def) {
      b.flex = true;
      this.flexes.push(this.bindFlex(def, node, meshes));
    }
    return b;
  }

  private bindFlex(def: FlexDef, node: THREE.Object3D, meshes: THREE.Mesh[]): Flex {
    const dir = def.dir ? direction(def.dir) : null;
    const at = def.nearest?.map((n) => point(n.at));
    const out: FlexMesh[] = [];
    let lo = Infinity;
    let hi = -Infinity;
    for (const mesh of meshes) {
      // The geometry gets its own plain float buffers: they are rewritten as the part bends.
      const g = mesh.geometry;
      const plain = (name: string): Float32Array => {
        const src = g.getAttribute(name);
        const arr = new Float32Array(src.count * 3);
        for (let i = 0; i < src.count; i++) {
          arr[i * 3] = src.getX(i);
          arr[i * 3 + 1] = src.getY(i);
          arr[i * 3 + 2] = src.getZ(i);
        }
        g.setAttribute(name, new THREE.BufferAttribute(arr, 3));
        return arr;
      };
      const local = mesh !== node ? mesh.matrix : null;
      const rest = plain('position').slice();
      const restN = g.hasAttribute('normal') ? plain('normal').slice() : null;
      if (local) {
        const n = new THREE.Matrix3().getNormalMatrix(local);
        for (let i = 0; i < rest.length; i += 3) {
          _v.fromArray(rest, i).applyMatrix4(local).toArray(rest, i);
          if (restN) _v.fromArray(restN, i).applyMatrix3(n).toArray(restN, i);
        }
      }
      const bucket = new Uint8Array(rest.length / 3);
      for (let i = 0; i < bucket.length; i++) {
        _v.fromArray(rest, i * 3);
        if (dir) {
          const u = _v.dot(dir);
          lo = Math.min(lo, u);
          hi = Math.max(hi, u);
        } else if (at) {
          let best = 0;
          for (let k = 1; k < at.length; k++) if (_v.distanceToSquared(at[k]!) < _v.distanceToSquared(at[best]!)) best = k;
          bucket[i] = best;
        }
      }
      mesh.frustumCulled = false;
      out.push({ mesh, inv: local ? local.clone().invert() : null, rest, restN, bucket });
    }
    if (dir) {
      for (const fm of out) {
        for (let i = 0; i < fm.bucket.length; i++) {
          const u = (_v.fromArray(fm.rest, i * 3).dot(dir) - lo) / Math.max(1e-6, hi - lo);
          fm.bucket[i] = Math.round(u * (BUCKETS - 1));
        }
      }
    }
    const count = at ? at.length : BUCKETS;
    return { def, meshes: out, mats: Array.from({ length: count }, () => new THREE.Matrix4()), last: new Float32Array(count * 16) };
  }

  private deform(f: Flex): void {
    const d = f.def;
    f.mats.forEach((M, k) => {
      if (d.nearest) return M.copy(this.links[d.nearest[k]!.link]!.world);
      const u = k / (BUCKETS - 1);
      M.copy(this.links[d.base!]!.world);
      for (const s of d.spans ?? []) {
        const w = smooth((u - s.u[0]!) / (s.u[1]! - s.u[0]!));
        for (const li of s.links) M.multiply(this.local(this.links[li]!, w, _m));
        if (d.act !== undefined) {
          // Far end plugged into an actuator body: blend towards it.
          const to = this.acts[d.act]!.body.elements;
          for (let i = 0; i < 16; i++) M.elements[i] = M.elements[i]! + (to[i]! - M.elements[i]!) * w;
        }
      }
      return M;
    });
    let changed = false;
    f.mats.forEach((M, k) => {
      for (let i = 0; i < 16; i++) {
        if (Math.abs(f.last[k * 16 + i]! - M.elements[i]!) > 1e-7) changed = true;
        f.last[k * 16 + i] = M.elements[i]!;
      }
    });
    if (!changed) return;
    for (const fm of f.meshes) {
      const mats = fm.inv ? f.mats.map((M) => _t.multiplyMatrices(fm.inv!, M).clone()) : f.mats;
      const pos = fm.mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
      const nor = fm.restN ? (fm.mesh.geometry.getAttribute('normal') as THREE.BufferAttribute) : null;
      const p = pos.array as Float32Array;
      const n = nor ? (nor.array as Float32Array) : null;
      for (let i = 0, j = 0; i < fm.bucket.length; i++, j += 3) {
        const e = mats[fm.bucket[i]!]!.elements;
        const x = fm.rest[j]!;
        const y = fm.rest[j + 1]!;
        const z = fm.rest[j + 2]!;
        p[j] = e[0]! * x + e[4]! * y + e[8]! * z + e[12]!;
        p[j + 1] = e[1]! * x + e[5]! * y + e[9]! * z + e[13]!;
        p[j + 2] = e[2]! * x + e[6]! * y + e[10]! * z + e[14]!;
        if (n) {
          const a = fm.restN![j]!;
          const b = fm.restN![j + 1]!;
          const c = fm.restN![j + 2]!;
          n[j] = e[0]! * a + e[4]! * b + e[8]! * c;
          n[j + 1] = e[1]! * a + e[5]! * b + e[9]! * c;
          n[j + 2] = e[2]! * a + e[6]! * b + e[10]! * c;
        }
      }
      pos.needsUpdate = true;
      if (nor) nor.needsUpdate = true;
    }
  }

  /** After a movement: bounds of the bent parts, so they can be picked where they now are. */
  settle(): void {
    for (const f of this.flexes) for (const fm of f.meshes) fm.mesh.geometry.computeBoundingSphere();
  }

  /** Matrix that carries a part from its rest place; false when it stays there. */
  matrix(b: Bound, out: THREE.Matrix4): boolean {
    if (!this.active || b.flex) return false;
    if (b.role) {
      const a = this.acts[b.act]!;
      out.copy(b.role === 2 ? a.rod : a.body);
      if (b.role === 3) {
        // Stretch along the actuator about the fixed end.
        const k = 1 + (a.len - a.len0) / b.span! - 1;
        const d = a.d0;
        const e = _t.elements;
        e[0] = 1 + k * d.x * d.x; e[4] = k * d.x * d.y; e[8] = k * d.x * d.z; e[12] = 0;
        e[1] = k * d.y * d.x; e[5] = 1 + k * d.y * d.y; e[9] = k * d.y * d.z; e[13] = 0;
        e[2] = k * d.z * d.x; e[6] = k * d.z * d.y; e[10] = 1 + k * d.z * d.z; e[14] = 0;
        e[3] = 0; e[7] = 0; e[11] = 0; e[15] = 1;
        _v.copy(b.anchor!).applyMatrix4(_t);
        _t.setPosition(b.anchor!.x - _v.x, b.anchor!.y - _v.y, b.anchor!.z - _v.z);
        out.multiply(_t);
      }
      return true;
    }
    if (b.link < 0) return false;
    out.copy(this.links[b.link]!.world);
    return true;
  }

  /** Where the pivot of link `of` is now, carried by link `on` (diagnostics). Scene metres. */
  probe(on: string, of: string): number[] {
    const p = this.links.find((l) => l.name === of)!.pivot.clone().applyMatrix4(this.link(on));
    return [p.x, p.y, p.z];
  }

  /** World matrix of a named link, for effects that hang off the robot. */
  link(name: string): THREE.Matrix4 {
    return this.links.find((l) => l.name === name)?.world ?? this.links[0]!.world;
  }
}
