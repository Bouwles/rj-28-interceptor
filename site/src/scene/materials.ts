// Materials for the model, one recipe per `RJ28_<key>` material name in the GLB.
//
// Base colour, roughness and metalness are read from the GLB material, so the
// exporter stays the source of those numbers. What is added here is what makes
// an all-black object readable: micro-texture as a triplanar detail normal (no
// UVs needed), edge burnish and crevice darkening from the COLOR_0 data
// channels, sheen and clearcoat where the real material has them.

import * as THREE from 'three';

export type MaterialKey =
  | 'alu' | 'armour' | 'braid' | 'cap' | 'cavity' | 'cfrp' | 'decal'
  | 'emissive' | 'fastener' | 'glass' | 'mesh' | 'rubber' | 'steel' | 'ti';

type DetailKind = 'peel' | 'fine' | 'lines' | 'weave' | 'twill';

interface Recipe {
  detail?: DetailKind;
  /** Texture repeats per metre. */
  scale?: number;
  /** Strength of the detail normal. */
  bump?: number;
  /** Roughness swing from the detail height. */
  roughVar?: number;
  /** Roughness drop on convex edges, and how far the edge colour shows through. */
  edgeRough?: number;
  edgeMix?: number;
  edgeColour?: [number, number, number];
  /** Colour multiplier and roughness gain in crevices. */
  cavityDark?: number;
  cavityRough?: number;
  /** Part-to-part spread of roughness and value, as in the offline materials. */
  batchRough?: number;
  batchValue?: number;
  apply?: (m: THREE.MeshPhysicalMaterial) => void;
}

const RECIPES: Record<MaterialKey, Recipe> = {
  armour: {
    detail: 'fine', scale: 85, bump: 0.03, roughVar: 0.05,
    edgeRough: 0.16, edgeMix: 0.3, edgeColour: [0.062, 0.062, 0.064],
    cavityDark: 0.5, cavityRough: 0.12, batchRough: 0.1, batchValue: 0.3,
  },
  cap: {
    detail: 'fine', scale: 70, bump: 0.06, roughVar: 0.04,
    edgeRough: 0.1, edgeMix: 0.3, edgeColour: [0.04, 0.04, 0.042], cavityDark: 0.55, cavityRough: 0.08,
  },
  alu: {
    detail: 'lines', scale: 34, bump: 0.035, roughVar: 0.08,
    edgeRough: 0.08, edgeMix: 0.12, edgeColour: [0.36, 0.36, 0.37],
    cavityDark: 0.55, cavityRough: 0.15, batchRough: 0.1, batchValue: 0.25,
  },
  ti: {
    detail: 'lines', scale: 26, bump: 0.025, roughVar: 0.06,
    edgeRough: 0.08, edgeMix: 0.15, edgeColour: [0.2, 0.19, 0.18],
    cavityDark: 0.6, cavityRough: 0.12, batchRough: 0.08, batchValue: 0.18,
  },
  steel: { cavityDark: 0.6, cavityRough: 0.1 },
  fastener: { edgeRough: 0.1, edgeMix: 0.2, edgeColour: [0.2, 0.2, 0.21], cavityDark: 0.55, cavityRough: 0.1 },
  rubber: {
    detail: 'fine', scale: 55, bump: 0.05, roughVar: 0.05, cavityDark: 0.6, batchRough: 0.06, batchValue: 0.2,
    apply: (m) => {
      m.sheen = 1;
      m.sheenColor.setScalar(0.05);
      m.sheenRoughness = 0.5;
    },
  },
  braid: { detail: 'weave', scale: 90, bump: 0.4, roughVar: 0.1, cavityDark: 0.6 },
  cfrp: {
    detail: 'twill', scale: 55, bump: 0.04, roughVar: 0.04, cavityDark: 0.6, batchRough: 0.06,
    apply: (m) => {
      m.clearcoat = 0.6;
      m.clearcoatRoughness = 0.14;
    },
  },
  glass: {
    apply: (m) => {
      // Smoked glass: dark at a glance, but the emitters and optics behind it show through.
      m.transparent = true;
      m.opacity = GLASS_OPACITY;
      m.depthWrite = false;
      m.clearcoat = 1;
      m.clearcoatRoughness = 0.03;
      m.roughness = Math.max(m.roughness, 0.06);
      m.specularIntensity = 1;
      m.specularColor.setRGB(0.55, 0.7, 1.0); // coated-lens tint in the reflection
    },
  },
  mesh: { cavityDark: 0.5 },
  cavity: {},
  emissive: {},
  decal: {},
};

// ── Detail textures ─────────────────────────────────────────────────────────
// Each is a small tiling height field stored as (dh/du, dh/dv, h). Tiling is
// exact because every wave has a whole number of cycles across the tile.

function buildDetail(kind: DetailKind): THREE.DataTexture {
  const N = 256;
  const h = new Float32Array(N * N);
  const TAU = Math.PI * 2;
  let seed = { peel: 7, fine: 19, lines: 31, weave: 43, twill: 57 }[kind];
  const rnd = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  const waves: [number, number, number, number][] = []; // kx, ky, amplitude, phase
  if (kind === 'peel' || kind === 'fine') {
    const [lo, hi, n] = kind === 'peel' ? [3, 11, 46] : [8, 26, 60];
    for (let i = 0; i < n; i++) {
      const k = lo + rnd() * (hi - lo);
      const a = rnd() * TAU;
      waves.push([Math.round(k * Math.cos(a)), Math.round(k * Math.sin(a)), 1 / k, rnd() * TAU]);
    }
  } else if (kind === 'lines') {
    // Tool marks: many fine ridges along u, with a slow waver so they are not ruled lines.
    for (let i = 0; i < 40; i++) waves.push([Math.round(rnd() * 2), 14 + Math.round(rnd() * 90), 0.3 + rnd(), rnd() * TAU]);
  }
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const u = x / N;
      const v = y / N;
      let s = 0;
      if (kind === 'weave') {
        // Two strand directions crossing over and under each other.
        const a = Math.sin(TAU * 8 * (u + v));
        const b = Math.sin(TAU * 8 * (u - v));
        s = Math.max(a, 0) * (0.6 + 0.4 * Math.cos(TAU * 32 * (u - v))) + Math.max(b, 0) * (0.6 + 0.4 * Math.cos(TAU * 32 * (u + v)));
      } else if (kind === 'twill') {
        const band = Math.floor(v * 16);
        s = 0.5 + 0.5 * Math.sin(TAU * (8 * u + band * 0.25)) * Math.sin(TAU * 16 * v) ** 2;
      } else {
        for (const [kx, ky, amp, ph] of waves) s += amp * Math.cos(TAU * (kx * u + ky * v) + ph);
      }
      h[y * N + x] = s;
    }
  }
  let min = Infinity;
  let max = -Infinity;
  for (const v of h) {
    min = Math.min(min, v);
    max = Math.max(max, v);
  }
  const data = new Uint8Array(N * N * 4);
  const at = (x: number, y: number) => (h[((y + N) % N) * N + ((x + N) % N)]! - min) / (max - min);
  let gmax = 1e-6;
  const gx = new Float32Array(N * N);
  const gy = new Float32Array(N * N);
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const i = y * N + x;
      gx[i] = at(x + 1, y) - at(x - 1, y);
      gy[i] = at(x, y + 1) - at(x, y - 1);
      gmax = Math.max(gmax, Math.abs(gx[i]!), Math.abs(gy[i]!));
    }
  }
  for (let i = 0; i < N * N; i++) {
    data[i * 4] = Math.round((gx[i]! / gmax) * 127 + 128);
    data[i * 4 + 1] = Math.round((gy[i]! / gmax) * 127 + 128);
    data[i * 4 + 2] = Math.round(at(i % N, Math.floor(i / N)) * 255);
    data[i * 4 + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, N, N, THREE.RGBAFormat);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.colorSpace = THREE.NoColorSpace;
  tex.needsUpdate = true;
  return tex;
}

// ── Shader patch ────────────────────────────────────────────────────────────

const VERT_PARS = /* glsl */ `
attribute vec3 aData;
varying vec3 vData;
varying vec3 vObjPos;
varying vec3 vObjNormal;
varying mat3 vObjToView;
varying float vWorldY;
`;
const VERT_WORLD = /* glsl */ `
vWorldY = (modelMatrix * vec4(transformed, 1.0)).y;
`;
const VERT_MAIN = /* glsl */ `
vData = aData;
vObjPos = position;
vObjNormal = normal;
vObjToView = normalMatrix;
`;
const FRAG_PARS = /* glsl */ `
uniform sampler2D uDetail;
uniform vec4 uDet;      // tiles per metre, bump, roughness swing, mesh pitch (0 = solid)
uniform vec4 uWear;     // edge roughness drop, edge colour mix, crevice darkening, crevice roughness
uniform vec3 uEdgeCol;
uniform float uDim;
uniform float uIblDiffuse;
uniform vec2 uEnvFall;
uniform float uScanY;
varying float vWorldY;
varying vec3 vData;
varying vec3 vObjPos;
varying vec3 vObjNormal;
varying mat3 vObjToView;
vec3 rjGrad = vec3(0.0);
float rjHeight = 0.5;
void rjSampleDetail() {
  if (uDet.y <= 0.0 && uDet.z <= 0.0) return;
  vec3 n = normalize(vObjNormal);
  vec3 w = pow(abs(n), vec3(4.0));
  w /= (w.x + w.y + w.z);
  vec3 p = vObjPos * uDet.x;
  vec3 tx = texture2D(uDetail, p.zy).rgb;
  vec3 ty = texture2D(uDetail, p.xz).rgb;
  vec3 tz = texture2D(uDetail, p.xy).rgb;
  vec2 gx = tx.rg * 2.0 - 1.0;
  vec2 gy = ty.rg * 2.0 - 1.0;
  vec2 gz = tz.rg * 2.0 - 1.0;
  vec3 g = w.x * vec3(0.0, gx.y, gx.x) + w.y * vec3(gy.x, 0.0, gy.y) + w.z * vec3(gz.x, gz.y, 0.0);
  rjGrad = g - dot(g, n) * n;
  rjHeight = dot(w, vec3(tx.b, ty.b, tz.b));
}
`;
const FRAG_COLOUR = /* glsl */ `
rjSampleDetail();
if (uDet.w > 0.0) {
  // Woven wire mesh: square holes on the dominant plane, solid where it is too fine to resolve.
  vec3 a = abs(normalize(vObjNormal));
  vec2 q = (a.x > a.y && a.x > a.z ? vObjPos.zy : (a.y > a.z ? vObjPos.xz : vObjPos.xy)) * uDet.w;
  float fw = max(fwidth(q.x), fwidth(q.y));
  vec2 cell = abs(fract(q) - 0.5);
  if (fw < 0.55) { if (max(cell.x, cell.y) < 0.34) discard; }
  else diffuseColor.rgb *= 0.45;
}
diffuseColor.rgb = mix(diffuseColor.rgb, uEdgeCol, vData.r * uWear.y);
diffuseColor.rgb *= mix(1.0, uWear.z, vData.b);
diffuseColor.rgb *= uDim;
`;
const FRAG_ROUGH = /* glsl */ `
roughnessFactor = clamp(roughnessFactor + (rjHeight - 0.5) * uDet.z - vData.r * uWear.x + vData.b * uWear.w, 0.045, 1.0);
`;
const FRAG_NORMAL = /* glsl */ `
normal = normalize(normal - uDet.y * (vObjToView * rjGrad) * faceDirection);
`;
const FRAG_IBL = /* glsl */ `
// Less of the studio reaches the lower half of the figure: the upper body is in the way.
float rjEnv = mix(uEnvFall.x, 1.0, smoothstep(0.0, uEnvFall.y, vObjPos.y));
iblIrradiance *= uIblDiffuse * rjEnv;
radiance *= rjEnv;
#ifdef USE_CLEARCOAT
clearcoatRadiance *= rjEnv;
#endif
`;
// Above the scan plane the part is drawn as on a drawing: a flat fill, no shading. The cut itself is a bright line.
const FRAG_SCAN = /* glsl */ `
if (vWorldY > uScanY) gl_FragColor = vec4(vec3(0.011), gl_FragColor.a);
if (abs(vWorldY - uScanY) < 0.007) gl_FragColor = vec4(vec3(2.5), 1.0);
`;
const FRAG_EMISSIVE = /* glsl */ `
totalEmissiveRadiance *= uDim;
`;

/**
 * Share of the environment's diffuse light the parts take. The HDRI lights
 * every face that looks at it; the real studio's soft box is close overhead
 * and the machine shades itself. The key light carries that part, with shadows,
 * and the environment is left to fill and to reflect.
 */
export const IBL_DIFFUSE = { value: 1 };
export const GLASS_OPACITY = 0.45;
/** Height of the scan plane, metres. Far above the model: everything is rendered. Far below: everything is drawn flat. */
export const SCAN_Y = { value: 100 };

/** Material for the feature-edge lines: off-white, and absent below the scan plane, where the model is still rendered. */
export function edgeMaterial(): THREE.LineBasicMaterial {
  const m = new THREE.LineBasicMaterial({ color: new THREE.Color(1.5, 1.47, 1.42) });
  m.onBeforeCompile = (shader) => {
    shader.uniforms.uScanY = SCAN_Y;
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying float vWorldY;')
      .replace('#include <project_vertex>', '#include <project_vertex>\nvWorldY = (modelMatrix * vec4(transformed, 1.0)).y;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float uScanY;\nvarying float vWorldY;')
      .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\nif (vWorldY < uScanY) discard;');
  };
  return m;
}
/** Environment light at floor level as a share of full, and the height in metres where it reaches full. */
export const ENV_FALL = { value: new THREE.Vector2(1, 1.6) };

export interface PartMaterial extends THREE.MeshPhysicalMaterial {
  userData: { dim: { value: number }; key: MaterialKey };
}

export class MaterialLibrary {
  private details = new Map<DetailKind, THREE.DataTexture>();
  private blank: THREE.DataTexture;

  constructor(private anisotropy: number) {
    this.blank = new THREE.DataTexture(new Uint8Array([128, 128, 128, 255]), 1, 1, THREE.RGBAFormat);
    this.blank.needsUpdate = true;
  }

  private detail(kind: DetailKind): THREE.DataTexture {
    let t = this.details.get(kind);
    if (!t) {
      t = buildDetail(kind);
      t.anisotropy = this.anisotropy;
      this.details.set(kind, t);
    }
    return t;
  }

  /**
   * A material for one part. `source` is the GLB material; `seed` is a number
   * in 0..1 unique to the part, used for the batch-to-batch variation.
   */
  private pool = new Map<string, PartMaterial>();
  /** Brightness of the parts that are not the subject (nothing selected: 1). Shared by the whole pool of dimmed materials. */
  readonly othersDim = { value: 1 };

  /**
   * A material shared by every part of one kind in one batch that is in its plain state.
   * Parts drawn one after another with the same material cost the renderer far less than
   * parts that each bring their own, so only a part that is fading or seen through gets
   * a material of its own (`create`).
   */
  pooled(key: MaterialKey, source: THREE.MeshStandardMaterial, seed: number, dimmed: boolean): PartMaterial {
    const id = `${source.name}|${seed}|${dimmed ? 1 : 0}`;
    let m = this.pool.get(id);
    if (!m) {
      m = this.create(key, source, seed, dimmed ? this.othersDim : undefined);
      this.pool.set(id, m);
    }
    return m;
  }

  create(key: MaterialKey, source: THREE.MeshStandardMaterial, seed: number, sharedDim?: { value: number }): PartMaterial {
    const r = RECIPES[key] ?? {};
    const m = new THREE.MeshPhysicalMaterial({
      color: source.color.clone(),
      roughness: source.roughness,
      metalness: source.metalness,
      side: source.side,
    }) as PartMaterial;
    m.name = source.name;
    const dim = sharedDim ?? { value: 1 };
    m.userData = { dim, key };

    if (key === 'decal') {
      // Printed markings: the atlas with its alpha, sitting just proud of the host surface.
      m.map = source.map;
      if (m.map) m.map.anisotropy = this.anisotropy;
      m.transparent = true;
      m.depthWrite = false;
      m.polygonOffset = true;
      m.polygonOffsetFactor = -2;
      m.polygonOffsetUnits = -2;
      m.roughness = 0.7;
      m.metalness = 0;
    } else {
      // Surfaces sit a hair behind the edge lines drawn over them.
      m.polygonOffset = true;
      m.polygonOffsetFactor = 1;
      m.polygonOffsetUnits = 1;
    }
    if (key === 'emissive') {
      m.emissive.copy(source.emissive.getHex() ? source.emissive : source.color);
      // Enough for the bloom threshold to catch the emitters and nothing else.
      m.emissiveIntensity = 6;
      m.color.multiplyScalar(0.3);
    } else if (key === 'cavity') {
      m.color.setScalar(Math.max(0.004, source.color.r));
    }
    r.apply?.(m);

    // Part-to-part spread: neighbours are never quite the same black.
    const jitter = seed * 2 - 1;
    if (r.batchRough) m.roughness = THREE.MathUtils.clamp(m.roughness + jitter * r.batchRough * 0.5, 0.05, 1);
    if (r.batchValue) m.color.multiplyScalar(1 + (((seed * 7.13) % 1) * 2 - 1) * r.batchValue * 0.5);

    const uniforms = {
      uDetail: { value: r.detail ? this.detail(r.detail) : this.blank },
      uDet: { value: new THREE.Vector4(r.scale ?? 1, r.bump ?? 0, r.roughVar ?? 0, key === 'mesh' ? 420 : 0) },
      uWear: { value: new THREE.Vector4(r.edgeRough ?? 0, r.edgeMix ?? 0, r.cavityDark ?? 1, r.cavityRough ?? 0) },
      uEdgeCol: { value: new THREE.Color(...(r.edgeColour ?? [0, 0, 0])) },
      uDim: dim,
      uIblDiffuse: IBL_DIFFUSE,
      uEnvFall: ENV_FALL,
      uScanY: SCAN_Y,
    };
    m.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>\n${VERT_PARS}`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>\n${VERT_MAIN}`)
        .replace('#include <project_vertex>', `#include <project_vertex>\n${VERT_WORLD}`);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>\n${FRAG_PARS}`)
        .replace('#include <color_fragment>', `#include <color_fragment>\n${FRAG_COLOUR}`)
        .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>\n${FRAG_ROUGH}`)
        .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>\n${FRAG_NORMAL}`)
        .replace('#include <lights_fragment_maps>', `#include <lights_fragment_maps>\n${FRAG_IBL}`)
        .replace('#include <dithering_fragment>', `#include <dithering_fragment>\n${FRAG_SCAN}`)
        .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>\n${FRAG_EMISSIVE}`);
    };
    // One compiled program per recipe, shared by every part that uses it.
    m.customProgramCacheKey = () => 'rj28';
    return m;
  }

  dispose(): void {
    for (const m of this.pool.values()) m.dispose();
    for (const t of this.details.values()) t.dispose();
    this.blank.dispose();
  }
}
