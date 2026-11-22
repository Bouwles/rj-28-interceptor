// The engagement that goes with the intercept movement: an incoming missile
// with its smoke trail, the shot, and the burst where the two meet. Everything
// is a function of the clip's clock, so it can be stopped or replayed at will.

import * as THREE from 'three';
import type { Effect } from './animate';

import { AIM, T_FIRE, T_HIT } from './clips';

const DEG = Math.PI / 180;
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const mix = (a: number, b: number, t: number) => a + (b - a) * clamp01(t);
/** Repeatable noise in 0..1 from an index. */
const rnd = (i: number, k = 0) => {
  const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453;
  return x - Math.floor(x);
};
const unit = (i: number) => {
  const z = rnd(i, 1) * 2 - 1;
  const a = rnd(i, 2) * Math.PI * 2;
  const r = Math.sqrt(1 - z * z);
  return new THREE.Vector3(r * Math.cos(a), z, r * Math.sin(a));
};

/** Soft, slightly ragged puff: one texture for fire and smoke alike. */
function puffTexture(): THREE.Texture {
  const size = 128;
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d')!;
  for (let i = 0; i < 26; i++) {
    const r = size * (0.16 + rnd(i, 3) * 0.2);
    const d = size * 0.22 * rnd(i, 4);
    const a = rnd(i, 5) * Math.PI * 2;
    const x = size / 2 + Math.cos(a) * d;
    const y = size / 2 + Math.sin(a) * d;
    const grad = g.createRadialGradient(x, y, 0, x, y, r);
    grad.addColorStop(0, 'rgba(255,255,255,0.22)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, size, size);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// Fire cools from white through yellow and orange to a dull red.
const RAMP: [number, number, number, number][] = [
  [0, 3.2, 3.0, 2.6],
  [0.12, 3.0, 2.1, 0.7],
  [0.4, 2.2, 0.8, 0.12],
  [0.75, 0.6, 0.12, 0.03],
  [1, 0.1, 0.03, 0.02],
];
function fire(u: number, out: THREE.Color): THREE.Color {
  let i = 1;
  while (i < RAMP.length - 1 && RAMP[i]![0] < u) i++;
  const a = RAMP[i - 1]!;
  const b = RAMP[i]!;
  const k = clamp01((u - a[0]) / (b[0] - a[0]));
  return out.setRGB(mix(a[1], b[1], k), mix(a[2], b[2], k), mix(a[3], b[3], k));
}

export interface InterceptHooks {
  /** Muzzle position and bore direction as the cannon stands this frame. */
  muzzle(pos: THREE.Vector3, dir: THREE.Vector3): void;
  camera: THREE.PerspectiveCamera;
}

export class Intercept implements Effect {
  private group = new THREE.Group();
  private tex = puffTexture();
  private missile = new THREE.Group();
  private glow: THREE.Sprite;
  private trail: THREE.Sprite[] = [];
  private fireball: THREE.Sprite[] = [];
  private smoke: THREE.Sprite[] = [];
  private flash: THREE.Sprite;
  private muzzleFlash: THREE.Sprite[] = [];
  private muzzleSmoke: THREE.Sprite[] = [];
  private tracer: THREE.Mesh;
  private sparks: THREE.LineSegments;
  private burstLight = new THREE.PointLight(0xffa25a, 0, 0, 0);
  private shotLight = new THREE.PointLight(0xffd9a0, 0, 6, 2);
  private far: number;
  private hit = new THREE.Vector3();
  private start = new THREE.Vector3();
  private heading = new THREE.Vector3();
  private mPos = new THREE.Vector3();
  private mDir = new THREE.Vector3();
  private fired = false;

  constructor(scene: THREE.Scene, private hooks: InterceptHooks) {
    this.far = hooks.camera.far;
    const sprite = (additive: boolean): THREE.Sprite => {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.tex, transparent: true, depthWrite: false, opacity: 0, blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending, rotation: 0 }));
      s.visible = false;
      this.group.add(s);
      return s;
    };
    // Missile: body, nose, four fins. 2.4 m long, flying along its own +Z.
    const skin = new THREE.MeshStandardMaterial({ color: 0x8a8d90, roughness: 0.55, metalness: 0.4 });
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 1.9, 16), skin);
    body.rotation.x = Math.PI / 2;
    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.11, 0.5, 16), skin);
    nose.rotation.x = Math.PI / 2;
    nose.position.z = 1.2;
    this.missile.add(body, nose);
    for (let i = 0; i < 4; i++) {
      const fin = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.3, 0.34), skin);
      fin.position.set(Math.cos((i * Math.PI) / 2) * 0.2, Math.sin((i * Math.PI) / 2) * 0.2, -0.78);
      fin.rotation.z = (i * Math.PI) / 2 + Math.PI / 2;
      this.missile.add(fin);
    }
    this.group.add(this.missile);
    this.glow = sprite(true);
    for (let i = 0; i < 46; i++) this.trail.push(sprite(false));
    for (let i = 0; i < 12; i++) this.smoke.push(sprite(false));
    for (let i = 0; i < 18; i++) this.fireball.push(sprite(true));
    this.flash = sprite(true);
    for (let i = 0; i < 4; i++) this.muzzleSmoke.push(sprite(false));
    for (let i = 0; i < 3; i++) this.muzzleFlash.push(sprite(true));
    this.tracer = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.012, 5, 8).rotateX(Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(4, 3, 1.6), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }),
    );
    this.sparks = new THREE.LineSegments(
      new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(new Float32Array(44 * 6), 3)),
      new THREE.LineBasicMaterial({ color: new THREE.Color(3, 1.5, 0.4), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }),
    );
    this.sparks.frustumCulled = false;
    this.group.add(this.tracer, this.sparks, this.burstLight, this.shotLight);
    // Layer 1: seen by the main camera, left out of the floor mirror and the shadow passes.
    this.group.traverse((o) => o.layers.set(1));
    this.group.visible = false;
    scene.add(this.group);
  }

  private begin(): void {
    // The meeting point is where the bore will be looking when the cannon fires.
    const yaw = AIM.yaw * DEG;
    const elev = AIM.elev * DEG;
    const dir = new THREE.Vector3(Math.sin(yaw) * Math.cos(elev), Math.sin(elev), Math.cos(yaw) * Math.cos(elev));
    this.hit.set(-0.29, 1.72, -0.1).addScaledVector(dir, AIM.range);
    // It comes in over the robot's right shoulder line, diving.
    this.heading.set(0.18, -0.2, -1).applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw).normalize();
    this.start.copy(this.hit).addScaledVector(this.heading, -34 * T_HIT);
    this.missile.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), this.heading);
    this.hooks.camera.far = 700;
    this.hooks.camera.updateProjectionMatrix();
    this.group.visible = true;
    this.fired = false;
  }

  update(t: number): void {
    if (!this.group.visible) this.begin();
    const place = (s: THREE.Sprite, pos: THREE.Vector3, size: number, opacity: number, spin: number) => {
      s.visible = opacity > 0.003;
      s.position.copy(pos);
      s.scale.setScalar(size);
      s.material.opacity = opacity;
      s.material.rotation = spin;
    };
    const p = new THREE.Vector3();

    // ── missile and trail ────────────────────────────────────────────────────
    const flying = t < T_HIT;
    const along = Math.min(t, T_HIT) / T_HIT;
    this.missile.visible = flying;
    this.missile.position.lerpVectors(this.start, this.hit, along);
    this.glow.material.color.setRGB(3, 1.9, 0.8);
    place(this.glow, p.copy(this.missile.position).addScaledVector(this.heading, -1.1), 1.1 + 0.25 * Math.sin(t * 90), flying ? 1 : 0, 0);
    const len = this.start.distanceTo(this.hit);
    this.trail.forEach((s, i) => {
      // Puffs are left behind every few metres and age where they were dropped.
      const d = len - 1.6 - i * 3.2; // metres from the start along the path
      const born = (d / len) * T_HIT;
      const age = t - born;
      if (d < 0 || age < 0) return void (s.visible = false);
      p.copy(this.start).addScaledVector(this.heading, d);
      p.x += (rnd(i, 6) - 0.5) * 0.5 * age;
      p.y += 0.25 * age + (rnd(i, 7) - 0.5) * 0.4 * age;
      const g = 0.5 + 0.12 * rnd(i, 8);
      s.material.color.setRGB(g, g, g * 1.02);
      place(s, p, 0.7 + 1.5 * (1 - Math.exp(-age * 0.9)) + rnd(i, 9) * 0.5, 0.5 * clamp01(age * 6) * (1 - clamp01((age - 1.5) / 4.5)), rnd(i, 10) * 6.28 + age * 0.2);
    });

    // ── the shot ─────────────────────────────────────────────────────────────
    const sinceFire = t - T_FIRE;
    if (sinceFire >= 0 && !this.fired) {
      this.fired = true;
      this.hooks.muzzle(this.mPos, this.mDir);
    }
    this.muzzleFlash.forEach((s, i) => {
      s.material.color.setRGB(3.2, 2.5 - i * 0.5, 1.4 - i * 0.4);
      const k = sinceFire >= 0 ? 1 - sinceFire / 0.085 : 0;
      place(s, p.copy(this.mPos).addScaledVector(this.mDir, 0.05 + i * 0.26), (0.62 - i * 0.16) * (0.7 + 0.5 * (1 - k)), k > 0 ? k : 0, i * 1.3);
    });
    this.shotLight.position.copy(this.mPos).addScaledVector(this.mDir, 0.3);
    this.shotLight.intensity = sinceFire >= 0 && sinceFire < 0.09 ? 60 * (1 - sinceFire / 0.09) : 0;
    this.muzzleSmoke.forEach((s, i) => {
      const a = sinceFire - i * 0.03;
      p.copy(this.mPos).addScaledVector(this.mDir, 0.25 + (1.3 + i * 0.5) * (1 - Math.exp(-a * 2.2)));
      p.y += 0.12 * a * a + i * 0.03;
      s.material.color.setRGB(0.42, 0.42, 0.43);
      place(s, p, 0.22 + 0.5 * (1 - Math.exp(-a * 1.6)) + i * 0.07, a > 0 ? 0.2 * clamp01(a * 14) * (1 - clamp01(a / 2.0)) : 0, i * 2.1 + a * 0.4);
    });
    const fly = sinceFire / (T_HIT - T_FIRE);
    this.tracer.visible = this.fired && fly >= 0 && fly < 1;
    if (this.tracer.visible) {
      const reach = this.mPos.distanceTo(this.hit);
      this.tracer.position.copy(this.mPos).addScaledVector(this.mDir, Math.max(2.5, fly * reach - 2.5));
      this.tracer.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), this.mDir);
    }

    // ── the burst ────────────────────────────────────────────────────────────
    const a = t - T_HIT;
    this.flash.material.color.setRGB(4, 3.6, 3);
    place(this.flash, this.hit, 3 + 60 * a, a >= 0 ? 1 - a / 0.13 : 0, 0);
    this.burstLight.position.copy(this.hit);
    this.burstLight.intensity = a >= 0 ? 5.5 * Math.exp(-a * 4.5) : 0;
    this.fireball.forEach((s, i) => {
      const life = 0.75 + 0.7 * rnd(i, 11);
      const u = a / life;
      const d = unit(i);
      // Fragments of the missile's fuel carry on along its heading; the rest goes every way.
      p.copy(this.hit).addScaledVector(d, (0.5 + 2.6 * rnd(i, 12)) * (1 - Math.exp(-a * 5))).addScaledVector(this.heading, 2.2 * rnd(i, 13) * (1 - Math.exp(-a * 2)));
      p.y += 0.5 * a;
      fire(u * 0.9 + 0.05, s.material.color);
      place(s, p, (1.3 + 2.2 * rnd(i, 14)) * (0.35 + 0.65 * (1 - Math.exp(-a * 7))) * (1 + 0.3 * u), a >= 0 && u < 1 ? clamp01(a * 40) * (1 - u * u) : 0, rnd(i, 15) * 6.28 + a * (rnd(i, 16) - 0.5));
    });
    this.smoke.forEach((s, i) => {
      const b = a - 0.12 - 0.05 * rnd(i, 17);
      const d = unit(i + 40);
      p.copy(this.hit).addScaledVector(d, (0.8 + 2.4 * rnd(i, 18)) * (1 - Math.exp(-b * 2.6))).addScaledVector(this.heading, 1.6 * (1 - Math.exp(-b * 1.2)));
      p.y += 0.35 * b;
      const g = 0.1 + 0.1 * rnd(i, 19) + 0.25 * Math.exp(-b * 3);
      s.material.color.setRGB(g * 1.25, g, g * 0.9);
      place(s, p, 2 + 3.4 * (1 - Math.exp(-b * 0.9)) + rnd(i, 20), b > 0 ? 0.6 * clamp01(b * 5) * (1 - clamp01((b - 1.4) / 3.6)) : 0, rnd(i, 21) * 6.28 + b * 0.25 * (rnd(i, 22) - 0.5));
    });
    const sp = this.sparks.geometry.getAttribute('position') as THREE.BufferAttribute;
    this.sparks.visible = a >= 0 && a < 1.6;
    if (this.sparks.visible) {
      const at = (time: number, i: number, out: THREE.Vector3) => {
        const v = 9 + 20 * rnd(i, 23);
        const drag = (1 - Math.exp(-time * 1.8)) / 1.8;
        return out.copy(this.hit).addScaledVector(unit(i + 90), v * drag).addScaledVector(this.heading, 6 * drag).setY(out.y - 4.9 * time * time * 0.6);
      };
      for (let i = 0; i < 44; i++) {
        at(a, i, p).toArray(sp.array, i * 6);
        at(Math.max(0, a - 0.045), i, p).toArray(sp.array, i * 6 + 3);
      }
      sp.needsUpdate = true;
      (this.sparks.material as THREE.LineBasicMaterial).opacity = 1 - clamp01((a - 0.5) / 1.1);
    }
  }

  stop(): void {
    if (!this.group.visible) return;
    this.group.visible = false;
    this.burstLight.intensity = this.shotLight.intensity = 0;
    this.hooks.camera.far = this.far;
    this.hooks.camera.updateProjectionMatrix();
  }

  /** Where the camera should look from to see both the robot and the meeting point. */
  static shot(): { pos: THREE.Vector3; target: THREE.Vector3; across: number; up: number } {
    // From behind the right shoulder: the robot low on the left, the sky it is shooting into on the right.
    // `across` and `up` are the angles, in degrees, the free part of the picture has to take in.
    return { pos: new THREE.Vector3(-1.2, 1.6, -5.4), target: new THREE.Vector3(-2.1, 2.38, 4.5), across: 48, up: 47 };
  }
}
