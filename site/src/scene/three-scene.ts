// The live model: WebGL 2 through three.js, rendered only when something changes.
//
// Everything the visitor can do to the robot (mount pose, strip-down, explode,
// x-ray, dimming, hiding) is expressed as a small set of numbers, and one
// function, `applyPose`, turns those numbers into node transforms and material
// opacities. Nothing is animated by mutating the scene piecemeal, which is
// what lets every action compose with every other and survive the LOD swap.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { GLTFLoader, type GLTF } from 'three/addons/loaders/GLTFLoader.js';
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';
import { Reflector } from 'three/addons/objects/Reflector.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { FullScreenQuad, Pass } from 'three/addons/postprocessing/Pass.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import type { BlueprintView, Isolation, MountState } from '../app/store';
import type { Part, Station, Vec3 } from '../data/types';
import { ENV_FALL, IBL_DIFFUSE, MaterialLibrary, type MaterialKey, type PartMaterial } from './materials';
import type {
  CameraReadout,
  SceneAssets,
  SceneController,
  SceneEvents,
  SceneInsets,
  SceneMode,
  SceneStats,
} from './types';

const DEG = Math.PI / 180;
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const smooth = (v: number) => {
  const t = clamp01(v);
  return t * t * (3 - 2 * t);
};
const ramp = (v: number, a: number, b: number) => smooth((v - a) / (b - a));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

// ── Look ────────────────────────────────────────────────────────────────────
// Tuned against the offline hero renders from the same cameras (tests/shots/lookdev_*).
const LOOK = {
  exposure: 1.0,
  envIntensity: 0.9,
  iblDiffuse: 0.3,
  envFloor: 0.2,
  envFullHeight: 2.0,
  /**
   * Key light: the soft box of the offline rig, overhead, a little in front and
   * to the robot's left. A spot at its real height, so the light falls off down
   * the figure as it does in the renders, and it casts the shadows the HDRI cannot.
   */
  keyDirection: [0.08, 0.97, 0.23],
  keyHeight: 2.4,
  keyIntensity: 95,
  shadows: true,
  /** The HDRI is authored with its centre on +Z; three puts an equirect centre on +X. */
  envRotationY: -Math.PI / 2,
  rimIntensity: 0.25,
  background: 0x111213,
  floor: 0x222324,
  gamma: 1.3,
  grain: 0.012,
  bloom: { strength: 0.3, radius: 0.3, threshold: 1.1 },
  ao: { radius: 0.09, intensity: 1.0 },
  reflect: 0.16,
  fov: 26,
};

// `?look={"exposure":0.9}` overrides a constant for one page load, for tuning against the offline renders.
try {
  const override = new URLSearchParams(location.search).get('look');
  if (override) {
    const merge = (into: Record<string, unknown>, from: Record<string, unknown>) => {
      for (const [k, v] of Object.entries(from)) {
        if (v && typeof v === 'object' && typeof into[k] === 'object') merge(into[k] as Record<string, unknown>, v as Record<string, unknown>);
        else if (k in into) into[k] = v;
      }
    };
    merge(LOOK as unknown as Record<string, unknown>, JSON.parse(override) as Record<string, unknown>);
  }
} catch {
  // A malformed override is ignored.
}

const HOME = { azimuth: 28, elevation: 7 };
const STRIP_SECONDS = 1.5;
const XRAY_ALPHA = 0.07;

interface PartRec {
  number: string;
  node: THREE.Object3D;
  meshes: THREE.Mesh[];
  /** Per mesh: the GLB material it came with and its material key. */
  sources: THREE.MeshStandardMaterial[];
  keys: MaterialKey[];
  /** Batch number, quantised so that parts of a batch can share a material. */
  batch: number;
  /** Materials of its own, made the first time the part needs one. */
  own: PartMaterial[] | null;
  /** Which materials are on the meshes now: 0 shared, 1 shared and dimmed, 2 its own. */
  matState: number;
  assembly: string;
  cls: string;
  key: MaterialKey;
  strip: number;
  group: '' | 'elev' | 'trav';
  /** Stage-2 explode offset, in the part's own frame. */
  explode: THREE.Vector3;
  /** Direction a panel leaves along, and the axis a fastener backs out along. */
  dir: THREE.Vector3;
  axis: THREE.Vector3;
  fastener: boolean;
  lift: number;
  /** 0 at the head, 1 at the feet: order of removal within a stage. */
  delay: number;
  /** Order within the assembly, 0 to 1, for the explode stagger. */
  order: number;
  centre: THREE.Vector3;
  radius: number;
  host: PartRec | null;
  decal: boolean;
  // Current presentation.
  alpha: number;
  dim: number;
  gone: boolean;
  transparent: boolean;
}

interface AsmRec {
  id: string;
  node: THREE.Object3D;
  offset: THREE.Vector3;
  centre: THREE.Vector3;
  index: number;
}

interface Model {
  lod: 0 | 1;
  root: THREE.Object3D;
  parts: Map<string, PartRec>;
  list: PartRec[];
  assemblies: AsmRec[];
  chain: THREE.Mesh | null;
  triangles: number;
  pick: THREE.Mesh[];
}

/** Toggles a flag between passes, so the floor mirror renders once per frame and not once per pass. */
class FlagPass extends Pass {
  constructor(private fn: (read: THREE.WebGLRenderTarget) => void) {
    super();
    this.needsSwap = false;
  }
  override render(_renderer: THREE.WebGLRenderer, _write: THREE.WebGLRenderTarget, read: THREE.WebGLRenderTarget): void {
    this.fn(read);
  }
}

const GradeShader = {
  uniforms: {
    tDiffuse: { value: null },
    tMask: { value: null as THREE.Texture | null },
    uTexel: { value: new THREE.Vector2(1, 1) },
    uOutline: { value: 0 },
    uEdge: { value: new THREE.Color(0x5fd8f2).convertLinearToSRGB() },
    uEdgeHidden: { value: new THREE.Color(0x1d5361).convertLinearToSRGB() },
    uGamma: { value: 1 },
    uGrain: { value: 0 },
  },
  vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse; uniform sampler2D tMask; uniform vec2 uTexel; uniform float uOutline;
    uniform vec3 uEdge; uniform vec3 uEdgeHidden; uniform float uGamma; uniform float uGrain; varying vec2 vUv;
    float hash(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
    void main() {
      vec3 c = texture2D(tDiffuse, vUv).rgb;
      c = pow(max(c, 0.0), vec3(uGamma));
      // Fixed grain: breaks up banding in the dark floor falloff and costs no re-render.
      c += (hash(gl_FragCoord.xy) - 0.5) * uGrain;
      if (uOutline > 0.5) {
        // Selection outline: the edge of the mask of the picked parts, in the interface accent,
        // dimmer where the part is behind something. Drawn after tone mapping so the colour is exact.
        vec2 o = uTexel * 1.25;
        vec2 lo = texture2D(tMask, vUv).rg;
        vec2 hi = lo;
        for (int i = 0; i < 8; i++) {
          float a = float(i) * 0.7853982;
          vec2 t = texture2D(tMask, vUv + o * vec2(cos(a), sin(a))).rg;
          lo = min(lo, t);
          hi = max(hi, t);
        }
        c = mix(c, mix(uEdgeHidden, uEdge, hi.g), clamp(hi.r - lo.r, 0.0, 1.0));
      }
      gl_FragColor = vec4(c, 1.0);
    }`,
};

/** Mask of the outlined parts: red where a part is, green where it is also in front of everything else. */
const MaskShader = {
  uniforms: { tDepth: { value: null as THREE.Texture | null }, uRes: { value: new THREE.Vector2(1, 1) } },
  vertexShader: /* glsl */ `
    #include <common>
    #include <morphtarget_pars_vertex>
    void main() {
      #include <begin_vertex>
      #include <morphtarget_vertex>
      #include <project_vertex>
    }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDepth; uniform vec2 uRes;
    void main() {
      float scene = texture2D(tDepth, gl_FragCoord.xy / uRes).r;
      gl_FragColor = vec4(1.0, step(gl_FragCoord.z, scene + 0.0004), 0.0, 1.0);
    }`,
};

const BlurShader = {
  uniforms: { tDiffuse: { value: null as THREE.Texture | null }, uDir: { value: new THREE.Vector2(1, 0) } },
  vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse; uniform vec2 uDir; varying vec2 vUv;
    void main() {
      float a = texture2D(tDiffuse, vUv).a * 0.227;
      a += (texture2D(tDiffuse, vUv + uDir * 1.385).a + texture2D(tDiffuse, vUv - uDir * 1.385).a) * 0.316;
      a += (texture2D(tDiffuse, vUv + uDir * 3.231).a + texture2D(tDiffuse, vUv - uDir * 3.231).a) * 0.0703;
      gl_FragColor = vec4(0.0, 0.0, 0.0, a);
    }`,
};

const SHADOW_SPAN = 3.4; // metres of floor the contact shadow covers

const FloorShader = {
  name: 'RJ28Floor',
  uniforms: {
    color: { value: null },
    tDiffuse: { value: null },
    textureMatrix: { value: null },
    uFloor: { value: new THREE.Color(LOOK.floor) },
    uBg: { value: new THREE.Color(LOOK.background) },
    uReflect: { value: 0 },
  },
  vertexShader: /* glsl */ `
    uniform mat4 textureMatrix; varying vec4 vUvR; varying vec3 vWorld;
    void main() {
      vUvR = textureMatrix * vec4(position, 1.0);
      vWorld = (modelMatrix * vec4(position, 1.0)).xyz;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse; uniform sampler2D tShadow; uniform vec3 uFloor; uniform vec3 uBg; uniform float uReflect;
    varying vec4 vUvR; varying vec3 vWorld;
    void main() {
      float r = length(vWorld.xz);
      // The lit patch of floor fades into the void, which leaves a horizon that is only just there.
      vec3 col = mix(uFloor, uBg, smoothstep(0.3, 3.4, r));
      if (uReflect > 0.0) col += texture2DProj(tDiffuse, vUvR).rgb * uReflect * (1.0 - smoothstep(1.0, 4.0, r));
      vec2 s = vWorld.xz / ${SHADOW_SPAN.toFixed(1)} + 0.5;
      float sh = (s.x > 0.0 && s.x < 1.0 && s.y > 0.0 && s.y < 1.0) ? texture2D(tShadow, s).a : 0.0;
      col *= 1.0 - min(sh, 1.0) * 0.9;
      gl_FragColor = vec4(col, 1.0);
    }`,
};

function hash01(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return ((h >>> 0) % 100000) / 100000;
}

/** Critically damped follow with a speed limit: accelerates, travels, settles, never overshoots. */
function smoothDamp(cur: number, target: number, vel: { v: number }, smoothTime: number, maxSpeed: number, dt: number): number {
  const omega = 2 / smoothTime;
  const x = omega * dt;
  const exp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const maxChange = maxSpeed * smoothTime;
  const change = Math.min(maxChange, Math.max(-maxChange, cur - target));
  const goal = cur - change;
  const temp = (vel.v + omega * change) * dt;
  vel.v = (vel.v - omega * temp) * exp;
  let out = goal + (change + temp) * exp;
  if (target - cur > 0 === out > target) {
    out = target;
    vel.v = 0;
  }
  return out;
}

export async function createThreeScene(canvas: HTMLCanvasElement): Promise<SceneController> {
  return new ThreeScene(canvas);
}

class ThreeScene implements SceneController {
  readonly backend = 'webgl2' as const;

  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(LOOK.fov, 1, 0.05, 80);
  private controls: OrbitControls;
  private composer!: EffectComposer;
  private grade!: ShaderPass;
  private gtao: GTAOPass | null = null;
  private maskRT = new THREE.WebGLRenderTarget(2, 2, { depthBuffer: false });
  private maskMat = new THREE.ShaderMaterial({
    ...MaskShader,
    uniforms: THREE.UniformsUtils.clone(MaskShader.uniforms),
    depthTest: false,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.CustomBlending,
    blendEquation: THREE.MaxEquation,
    blendSrc: THREE.OneFactor,
    blendDst: THREE.OneFactor,
  });
  private outlineParts: PartRec[] = [];
  private library: MaterialLibrary;
  private model: Model | null = null;
  private floor!: Reflector;
  private mirrorOn = false;
  private shadowRT = [new THREE.WebGLRenderTarget(512, 512), new THREE.WebGLRenderTarget(512, 512)];
  private shadowCam = new THREE.OrthographicCamera(-SHADOW_SPAN / 2, SHADOW_SPAN / 2, SHADOW_SPAN / 2, -SHADOW_SPAN / 2, 0, 1.3);
  private shadowDepth = new THREE.MeshDepthMaterial();
  private blur = new FullScreenQuad(new THREE.ShaderMaterial(BlurShader));
  private shadowDirty = true;
  private labels: HTMLElement;
  private listeners: { [K in keyof SceneEvents]?: Set<SceneEvents[K]> } = {};

  // Requested state.
  private mode: SceneMode = 'model';
  private assets: SceneAssets | null = null;
  private stations: Station[] = [];
  private tourU = 0;
  private selected: string | null = null;
  private hovered: string | null = null;
  private hidden: ReadonlySet<string> = new Set();
  private isolated: Isolation | null = null;
  private mountState: MountState = 'stowed';
  private wantTrav = 0;
  private wantElev = 0;
  private stripTarget = 0;
  private explodeAmt = 0;
  private xray = false;
  private measuring = false;
  private reduced = false;
  private light = false;
  private insets: SceneInsets = { top: 0, right: 0, bottom: 0, left: 0 };

  // Animated state.
  private elev = 90;
  private trav = 0;
  private elevVel = { v: 0 };
  private travVel = { v: 0 };
  private lockDwell = 0;
  private stripP = [0, 0, 0, 0, 0];
  private xrayT = 0;
  private shift = new THREE.Vector2();
  private tween: { t: number; dur: number; from: [THREE.Vector3, THREE.Vector3]; to: [THREE.Vector3, THREE.Vector3] } | null = null;
  private tourCam = { pos: new THREE.Vector3(), target: new THREE.Vector3(), fov: LOOK.fov, ready: false };
  private tourDim: Set<string> | null = null;
  private tourXray = false;
  private measurePts: THREE.Vector3[] = [];
  private measureLine: THREE.Line | null = null;
  private frozenCamera = false;

  // Loop.
  private dirty = true;
  private poseDirty = true;
  private raf = 0;
  private last = 0;
  /** Pixel ratio while the picture is moving; at rest it is always the full one. */
  private pixelRatio = 0;
  private maxPixelRatio = 1;
  private bufferRatio = 0;
  /** Set when frames ran slow: the floor mirror is left out while the picture is moving. */
  private lite = false;
  private needRefine = false;
  private blobDirty = false;
  private lastBlob = 0;
  private drawCalls = 0;
  private intervals: number[] = [];
  private cpu: number[] = [];
  private lastRender = 0;
  private pointer = { x: 0, y: 0, cx: 0, cy: 0, inside: false, moved: false, downX: 0, downY: 0, downT: 0 };
  private raycaster = new THREE.Raycaster();
  private interacted = false;
  private disposed = false;
  private resizeObserver: ResizeObserver;

  // Mount geometry from mount.json.
  private mountDef = {
    ep: new THREE.Vector3(), ea: new THREE.Vector3(-1, 0, 0), tp: new THREE.Vector3(), ta: new THREE.Vector3(0, 1, 0),
    elevRange: [-5, 90] as [number, number], travRange: [-25, 25] as [number, number],
  };
  private extents: [number, number][] = [[0.62, 1.08], [1.2, 1.5], [1.4, 1.6]];
  private centreY = [1.03, 1.03, 1.03];
  private poseElev = new THREE.Matrix4();
  private poseTrav = new THREE.Matrix4();

  constructor(private canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, stencil: false, powerPreference: 'high-performance' });
    this.renderer.toneMapping = THREE.AgXToneMapping;
    this.renderer.toneMappingExposure = LOOK.exposure;
    this.renderer.setClearColor(LOOK.background, 1);
    this.renderer.info.autoReset = false; // counted per frame, across every pass
    // Shadows are drawn again only when the pose changes, not every frame.
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.VSMShadowMap;
    this.renderer.shadowMap.autoUpdate = false;
    this.library = new MaterialLibrary(Math.min(8, this.renderer.capabilities.getMaxAnisotropy()));
    this.scene.background = new THREE.Color(LOOK.background);

    // Layer 1 holds the small parts (screws, clips, markings). The main camera sees them;
    // the floor mirror and the shadow cameras do not, which spares them a third of the draw calls.
    this.camera.layers.enable(1);
    this.raycaster.layers.enableAll();

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.085;
    this.controls.rotateSpeed = 0.75;
    this.controls.zoomSpeed = 0.9;
    this.controls.minDistance = 0.35;
    this.controls.maxDistance = 16;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.035; // never under the floor
    this.controls.addEventListener('change', () => this.invalidate());
    this.controls.addEventListener('start', () => {
      this.tween = null;
      this.touch();
    });

    this.labels = document.createElement('div');
    this.labels.className = 'scene-labels';
    this.labels.hidden = true;
    canvas.parentElement?.appendChild(this.labels);

    canvas.addEventListener('pointermove', this.onPointerMove);
    canvas.addEventListener('pointerdown', this.onPointerDown);
    canvas.addEventListener('pointerup', this.onPointerUp);
    canvas.addEventListener('pointerleave', this.onPointerLeave);
    canvas.addEventListener('dblclick', this.onDoubleClick);
    canvas.addEventListener('wheel', () => this.touch(), { passive: true });
    canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      this.emit('lost');
    });
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas);
  }

  // ── Events ────────────────────────────────────────────────────────────────
  on<K extends keyof SceneEvents>(type: K, fn: SceneEvents[K]): () => void {
    const set = (this.listeners[type] ??= new Set() as never) as Set<SceneEvents[K]>;
    set.add(fn);
    return () => set.delete(fn);
  }
  private emit<K extends keyof SceneEvents>(type: K, ...args: Parameters<SceneEvents[K]>): void {
    for (const fn of (this.listeners[type] ?? []) as Set<(...a: unknown[]) => void>) fn(...args);
  }
  private touch(): void {
    if (this.interacted) return;
    this.interacted = true;
    this.emit('interact');
  }

  // ── Loading ───────────────────────────────────────────────────────────────
  async load(assets: SceneAssets): Promise<void> {
    this.assets = assets;
    this.light = assets.light;
    this.stations = assets.stations ?? [];
    this.readMount(assets.mount);
    const files = (assets.manifest as { files?: Record<string, { url?: string }>; hdri?: { url?: string } }) ?? {};
    const path = (key: string, fallback: string) => files.files?.[key]?.url ?? fallback;
    const hdrPath = files.hdri?.url ?? 'hdri/studio.hdr';
    const lod1 = path('lod1', 'models/rj28_lod1.glb');
    const lod0 = path('lod0', 'models/rj28_lod0.glb');

    const [hdr, glb] = await Promise.all([
      assets.loader.bytes(hdrPath, assets.url(hdrPath)),
      assets.loader.bytes(lod1, assets.url(lod1)),
    ]);
    this.setEnvironment(hdr);
    this.buildStage();
    this.buildComposer();
    this.model = this.buildModel(await this.parse(glb), 1);
    this.scene.add(this.model.root);
    this.applyPose(0);
    this.measureExtents(this.model);
    this.resize();
    this.goHome(false);
    this.poseDirty = true;
    this.renderer.compile(this.scene, this.camera);
    this.frame_();
    this.start();
    this.emit('lod', 1);

    if (!this.light) {
      // The full model streams in behind the first frame and replaces the light one in place.
      void fetch(assets.url(lod0))
        .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(String(r.status)))))
        .then((buf) => this.parse(new Uint8Array(buf)))
        .then((gltf) => {
          if (this.disposed) return;
          const next = this.buildModel(gltf, 0);
          const old = this.model;
          this.scene.add(next.root);
          this.model = next;
          if (old) {
            this.scene.remove(old.root);
            old.root.traverse((o) => (o as THREE.Mesh).geometry?.dispose());
            for (const p of old.list) for (const m of p.own ?? []) m.dispose();
          }
          this.poseDirty = true;
          this.shadowDirty = true;
          this.syncOutline();
          this.invalidate();
          this.emit('lod', 0);
        })
        .catch(() => undefined); // LOD1 stays on screen: the page is complete without the swap
    }
  }

  private parse(bytes: Uint8Array): Promise<GLTF> {
    const loader = new GLTFLoader();
    loader.setMeshoptDecoder(MeshoptDecoder);
    const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
    return loader.parseAsync(buffer, '');
  }

  private setEnvironment(bytes: Uint8Array): void {
    const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
    const d = new HDRLoader().parse(buffer) as { data: Float32Array | Uint16Array; width: number; height: number; type: THREE.TextureDataType };
    const tex = new THREE.DataTexture(d.data, d.width, d.height, THREE.RGBAFormat, d.type);
    tex.colorSpace = THREE.LinearSRGBColorSpace;
    tex.mapping = THREE.EquirectangularReflectionMapping;
    tex.minFilter = tex.magFilter = THREE.LinearFilter;
    tex.generateMipmaps = false;
    tex.flipY = true;
    tex.needsUpdate = true;
    this.scene.environment = tex;
    this.scene.environmentIntensity = LOOK.envIntensity;
    this.scene.environmentRotation.y = LOOK.envRotationY;
  }

  private readMount(raw: unknown): void {
    const m = raw as { elevation?: { pivot: Vec3; axis: Vec3 }; traverse?: { pivot: Vec3; axis: Vec3 }; limits?: { elevation: [number, number]; traverse: [number, number] } } | null;
    if (!m?.elevation || !m.traverse) return;
    this.mountDef.ep.fromArray(m.elevation.pivot);
    this.mountDef.ea.fromArray(m.elevation.axis).normalize();
    this.mountDef.tp.fromArray(m.traverse.pivot);
    this.mountDef.ta.fromArray(m.traverse.axis).normalize();
    if (m.limits) {
      this.mountDef.elevRange = m.limits.elevation;
      this.mountDef.travRange = m.limits.traverse;
    }
  }

  private buildStage(): void {
    IBL_DIFFUSE.value = LOOK.iblDiffuse;
    ENV_FALL.value.set(LOOK.envFloor, LOOK.envFullHeight);
    const key = new THREE.SpotLight(0xffffff, LOOK.keyIntensity, 0, 0.95, 1, 2);
    key.position.fromArray(LOOK.keyDirection).multiplyScalar(LOOK.keyHeight).add(new THREE.Vector3(0, 1, 0));
    key.target.position.set(0, 0.9, 0);
    key.castShadow = LOOK.shadows;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.near = 0.6;
    key.shadow.camera.far = 7;
    key.shadow.bias = -0.0005;
    key.shadow.normalBias = 0.01;
    key.shadow.radius = 5;
    key.shadow.blurSamples = 12;
    this.scene.add(key, key.target);
    // Two rims behind the robot, left and right, as in the offline rig.
    for (const x of [-1, 1]) {
      const rim = new THREE.DirectionalLight(0xdfe9ff, LOOK.rimIntensity);
      rim.position.set(x * 3.2, 3.0, -3.6);
      this.scene.add(rim);
    }
    this.floor = new Reflector(new THREE.PlaneGeometry(60, 60), {
      shader: FloorShader,
      textureWidth: 1024,
      textureHeight: 1024,
      clipBias: 0.002,
      multisample: 0,
    });
    this.floor.rotation.x = -Math.PI / 2;
    const fm = this.floor.material as THREE.ShaderMaterial;
    fm.uniforms.tShadow = { value: this.shadowRT[0]!.texture };
    fm.uniforms.uReflect!.value = 0;
    // The mirror pass is expensive: run it for the beauty pass only.
    const mirror = this.floor.onBeforeRender;
    this.floor.onBeforeRender = (...args) => {
      if (this.mirrorOn && fm.uniforms.uReflect!.value > 0) mirror.apply(this.floor, args);
    };
    this.scene.add(this.floor);

    this.shadowCam.rotation.x = Math.PI / 2; // looking up from the floor
    this.shadowDepth.depthTest = false;
    this.shadowDepth.depthWrite = false;
    this.shadowDepth.onBeforeCompile = (shader) => {
      shader.fragmentShader = shader.fragmentShader.replace(
        'gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );',
        'gl_FragColor = vec4( vec3( 0.0 ), ( 1.0 - fragCoordZ ) * 0.55 );',
      );
    };
  }

  private buildComposer(): void {
    const size = new THREE.Vector2(2, 2);
    const target = new THREE.WebGLRenderTarget(2, 2, {
      type: THREE.HalfFloatType,
      samples: this.light ? 2 : 4,
      depthTexture: new THREE.DepthTexture(2, 2),
    });
    this.composer = new EffectComposer(this.renderer, target);
    this.composer.addPass(new FlagPass(() => (this.mirrorOn = true)));
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    // The scene's own depth, resolved from the multisampled buffer, serves both the ambient
    // occlusion and the selection outline, so neither has to draw the model a second time.
    this.composer.addPass(
      new FlagPass((read) => {
        this.mirrorOn = false;
        const depth = read.depthTexture;
        if (this.gtao) {
          const g = this.gtao as unknown as { gtaoMaterial: THREE.ShaderMaterial; pdMaterial: THREE.ShaderMaterial };
          g.gtaoMaterial.uniforms.tDepth!.value = depth;
          g.pdMaterial.uniforms.tDepth!.value = depth;
        }
        this.renderMask(depth);
      }),
    );
    if (!this.light) {
      this.gtao = new GTAOPass(this.scene, this.camera, 2, 2, { depthTexture: target.depthTexture ?? undefined });
      this.gtao.blendIntensity = LOOK.ao.intensity;
      this.gtao.updateGtaoMaterial({ radius: LOOK.ao.radius, distanceExponent: 1.4, thickness: 1, scale: 1, samples: 12, screenSpaceRadius: false });
      this.gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 6, rings: 2, samples: 12 });
      this.composer.addPass(this.gtao);
    }
    const bloom = new UnrealBloomPass(size, LOOK.bloom.strength, LOOK.bloom.radius, LOOK.bloom.threshold);
    // Only saturated light blooms: the cyan emitters do, a white glint on polished steel does not.
    const highPass = (bloom as unknown as { materialHighPassFilter: THREE.ShaderMaterial }).materialHighPassFilter;
    highPass.fragmentShader = highPass.fragmentShader.replace(
      /float alpha = ([^;]+);/,
      'float rjMax = max(texel.r, max(texel.g, texel.b)); float rjMin = min(texel.r, min(texel.g, texel.b)); float alpha = ($1) * smoothstep(0.3, 0.55, (rjMax - rjMin) / max(rjMax, 1e-4));',
    );
    highPass.needsUpdate = true;
    this.composer.addPass(bloom);
    this.composer.addPass(new OutputPass());
    this.grade = new ShaderPass(GradeShader);
    this.grade.uniforms.uGamma!.value = LOOK.gamma;
    this.grade.uniforms.uGrain!.value = LOOK.grain;
    this.grade.uniforms.tMask!.value = this.maskRT.texture;
    this.composer.addPass(this.grade);
  }

  /** Draw the outlined parts into the mask, tested against the depth of the frame just rendered. */
  private renderMask(depth: THREE.DepthTexture | null): void {
    const parts = this.outlineParts.filter((p) => !p.gone && p.node.visible);
    this.grade.uniforms.uOutline!.value = parts.length && depth ? 1 : 0;
    if (!parts.length || !depth) return;
    const r = this.renderer;
    this.maskMat.uniforms.tDepth!.value = depth;
    const colour = r.getClearColor(new THREE.Color());
    const alpha = r.getClearAlpha();
    const auto = r.autoClear;
    r.setRenderTarget(this.maskRT);
    r.setClearColor(0x000000, 1);
    r.clear();
    r.autoClear = false;
    for (const p of parts) {
      const saved = p.meshes.map((mesh) => mesh.material);
      for (const mesh of p.meshes) mesh.material = this.maskMat;
      r.render(p.node, this.camera);
      p.meshes.forEach((mesh, i) => (mesh.material = saved[i]!));
    }
    r.autoClear = auto;
    r.setClearColor(colour, alpha);
  }

  private buildModel(gltf: GLTF, lod: 0 | 1): Model {
    const root = gltf.scene;
    const info = new Map<string, Part>();
    for (const p of this.assets?.parts ?? []) info.set(p.number, p);
    const parts = new Map<string, PartRec>();
    const list: PartRec[] = [];
    const assemblies: AsmRec[] = [];
    const byNode = new Map<string, PartRec>();
    const pick: THREE.Mesh[] = [];
    let chain: THREE.Mesh | null = null;
    let triangles = 0;
    const box = new THREE.Box3();
    const tmp = new THREE.Box3();

    root.traverse((o) => {
      const u = o.userData as { number?: string; assembly?: string; explode_stage?: number; explode_offset?: Vec3; material_key?: string; material_class?: string; mount_group?: string; host?: string };
      if (o.name === 'AXES') o.visible = false;
      if (u.explode_stage === 1 && u.assembly && !u.number) {
        assemblies.push({ id: u.assembly, node: o, offset: new THREE.Vector3().fromArray(u.explode_offset ?? [0, 0, 0]), centre: new THREE.Vector3(), index: 0 });
        return;
      }
      if (!u.number) return;
      const meshes: THREE.Mesh[] = [];
      o.traverse((c) => (c as THREE.Mesh).isMesh && meshes.push(c as THREE.Mesh));
      box.makeEmpty();
      const sources: THREE.MeshStandardMaterial[] = [];
      const keys: MaterialKey[] = [];
      const batch = (Math.floor(hash01(u.number) * 4) + 0.5) / 4;
      for (const mesh of meshes) {
        const g = mesh.geometry;
        if (g.hasAttribute('color')) {
          g.setAttribute('aData', g.getAttribute('color'));
          g.deleteAttribute('color');
        }
        if (!g.boundingBox) g.computeBoundingBox();
        box.union(tmp.copy(g.boundingBox!).applyMatrix4(mesh === o ? new THREE.Matrix4() : mesh.matrix));
        triangles += (g.index ? g.index.count : g.getAttribute('position').count) / 3;
        const src = mesh.material as THREE.MeshStandardMaterial;
        const key = (src.name.replace(/^RJ28_/, '') || u.material_key || 'alu') as MaterialKey;
        sources.push(src);
        keys.push(key);
        mesh.material = this.library.pooled(key, src, batch, false);
        mesh.castShadow = key !== 'decal';
        mesh.receiveShadow = key !== 'decal';
        mesh.userData.part = u.number;
        if (mesh.morphTargetInfluences?.length) chain = mesh;
      }
      const centre = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const key = (u.material_key ?? 'alu') as MaterialKey;
      const rec: PartRec = {
        number: u.number,
        node: o,
        meshes,
        sources,
        keys,
        batch,
        own: null,
        matState: 0,
        assembly: u.assembly ?? '',
        cls: u.material_class ?? '',
        key,
        strip: info.get(u.number)?.strip ?? 0,
        group: u.mount_group === 'elev' || u.mount_group === 'trav' ? u.mount_group : '',
        explode: new THREE.Vector3().fromArray(u.explode_offset ?? [0, 0, 0]),
        dir: new THREE.Vector3(),
        axis: new THREE.Vector3(),
        fastener: key === 'fastener',
        lift: THREE.MathUtils.clamp(0.08 + Math.max(size.x, size.y, size.z) * 0.3, 0.08, 0.2),
        delay: 0,
        order: 0,
        centre,
        radius: Math.max(0.02, size.length() / 2),
        host: null,
        decal: key === 'decal',
        alpha: 1,
        dim: 1,
        gone: false,
        transparent: false,
      };
      // Smallest extent of a screw set is along the screws.
      rec.axis.set(size.x <= size.y && size.x <= size.z ? 1 : 0, size.y < size.x && size.y <= size.z ? 1 : 0, size.z < size.x && size.z < size.y ? 1 : 0);
      if (rec.group) o.matrixAutoUpdate = false;
      if (rec.fastener || rec.decal || rec.radius < 0.03) for (const mesh of meshes) mesh.layers.set(1);
      parts.set(rec.number, rec);
      byNode.set(o.name, rec);
      list.push(rec);
      if (!rec.decal) pick.push(...meshes);
      (o.userData as { hostName?: string }).hostName = u.host;
    });

    assemblies.sort((a, b) => a.id.localeCompare(b.id));
    assemblies.forEach((a, i) => (a.index = i));
    const asmBox = new Map<string, THREE.Box3>();
    for (const p of list) {
      const b = asmBox.get(p.assembly) ?? new THREE.Box3();
      b.expandByPoint(p.centre);
      asmBox.set(p.assembly, b);
    }
    for (const a of assemblies) asmBox.get(a.id)?.getCenter(a.centre);
    const counts = new Map<string, number>();
    for (const p of list) counts.set(p.assembly, (counts.get(p.assembly) ?? 0) + 1);
    const seen = new Map<string, number>();
    for (const p of list) {
      const n = seen.get(p.assembly) ?? 0;
      seen.set(p.assembly, n + 1);
      p.order = n / Math.max(1, (counts.get(p.assembly) ?? 1) - 1);
      p.delay = 1 - clamp01(p.centre.y / 1.75);
      // Removal direction: the way the part leaves in the exploded view, else outwards.
      if (p.explode.lengthSq() > 1e-8) p.dir.copy(p.explode).normalize();
      else {
        const c = asmBox.get(p.assembly)?.getCenter(new THREE.Vector3()) ?? new THREE.Vector3();
        p.dir.subVectors(p.centre, c).setY(0);
        if (p.dir.lengthSq() < 1e-6) p.dir.set(0, 0, 1);
        p.dir.normalize();
      }
      if (p.axis.dot(p.dir) < 0) p.axis.negate();
      if (Math.abs(p.axis.dot(p.dir)) < 0.05) {
        const c = asmBox.get(p.assembly)?.getCenter(new THREE.Vector3()) ?? new THREE.Vector3();
        if (p.axis.dot(new THREE.Vector3().subVectors(p.centre, c)) < 0) p.axis.negate();
      }
    }
    // A marking travels with the panel it is printed on.
    for (const p of list) {
      const hostName = (p.node.userData as { hostName?: string }).hostName;
      const host = hostName ? byNode.get(hostName) : undefined;
      if (!host) continue;
      p.host = host;
      p.dir.copy(host.dir);
      p.lift = host.lift;
      p.delay = host.delay;
      p.fastener = false;
      p.strip = host.strip || p.strip;
    }
    return { lod, root, parts, list, assemblies, chain, triangles: Math.round(triangles), pick };
  }

  // ── Queries ───────────────────────────────────────────────────────────────
  partCount(): number {
    return this.model?.list.length ?? 0;
  }
  partNumbers(): string[] {
    return this.model?.list.map((p) => p.number) ?? [];
  }
  pickable(part: string): boolean {
    const p = this.model?.parts.get(part);
    return !!p && !p.decal && this.canPick(p);
  }
  private canPick(p: PartRec): boolean {
    if (p.gone || !p.node.visible) return false;
    if (p.strip > 0 && this.stripP[p.strip]! > 0.02) return false;
    if (this.effectiveXray() && p.cls === 'armour') return false;
    return true;
  }
  stats(): SceneStats {
    const n = this.intervals.length || 1;
    return {
      lod: this.model?.lod ?? 1,
      triangles: this.model?.triangles ?? 0,
      drawCalls: this.drawCalls,
      pixelRatio: this.pixelRatio,
      reduced: this.lite,
      frameMs: this.intervals.reduce((a, b) => a + b, 0) / n,
      worstMs: this.intervals.reduce((a, b) => Math.max(a, b), 0),
      cpuMs: this.cpu.reduce((a, b) => a + b, 0) / (this.cpu.length || 1),
    };
  }

  // ── State setters ─────────────────────────────────────────────────────────
  setMode(mode: SceneMode): void {
    if (mode === this.mode) return;
    const was = this.mode;
    this.mode = mode;
    this.controls.enabled = mode === 'model';
    this.tourCam.ready = false;
    this.setHover(null);
    this.syncOutline();
    if (mode === 'model' && was === 'dossier') {
      this.camera.fov = LOOK.fov;
      this.camera.updateProjectionMatrix();
      this.goHome(false);
    }
    this.poseDirty = true;
    this.shadowDirty = true;
    if (mode !== 'idle') this.start();
    this.invalidate();
  }
  setTour(u: number): void {
    this.tourU = u;
    if (this.mode === 'dossier') this.invalidate();
  }
  setSelection(part: string | null): void {
    this.selected = part;
    this.poseDirty = true;
    this.syncOutline();
    this.invalidate();
  }
  setVisibility(hidden: ReadonlySet<string>, isolated: Isolation | null): void {
    this.hidden = hidden;
    this.isolated = isolated;
    this.poseDirty = true;
    this.shadowDirty = true;
    this.invalidate();
  }
  setMount(state: MountState, traverseDeg: number, elevationDeg: number, animate: boolean): void {
    const [e0, e1] = this.mountDef.elevRange;
    const [t0, t1] = this.mountDef.travRange;
    if (state !== this.mountState && state === 'deployed' && this.elev > 89.5) this.lockDwell = 0.3; // travel lock releases first
    this.mountState = state;
    this.wantElev = Math.min(e1, Math.max(e0, elevationDeg));
    this.wantTrav = Math.min(t1, Math.max(t0, traverseDeg));
    if (!animate || this.reduced) {
      this.elev = state === 'stowed' ? e1 : this.wantElev;
      this.trav = state === 'stowed' ? 0 : this.wantTrav;
      this.elevVel.v = this.travVel.v = 0;
      this.lockDwell = 0;
      this.poseDirty = true;
      this.shadowDirty = true;
    }
    this.invalidate();
  }
  setStrip(stage: number, animate: boolean): void {
    this.stripTarget = Math.min(4, Math.max(0, Math.round(stage)));
    if (!animate) {
      for (let s = 1; s <= 4; s++) this.stripP[s] = s <= this.stripTarget ? 1 : 0;
      this.poseDirty = true;
      this.shadowDirty = true;
    }
    this.invalidate();
  }
  setExplode(amount: number): void {
    const next = clamp01(amount);
    if (next === this.explodeAmt) return;
    // Keep the whole explosion in frame: the camera backs off in step with it.
    if (this.mode === 'model' && !this.frozenCamera) {
      const k = this.explodeReach(next) / this.explodeReach(this.explodeAmt);
      const off = this.camera.position.clone().sub(this.controls.target).multiplyScalar(k);
      if (off.length() < this.controls.maxDistance) this.camera.position.copy(this.controls.target).add(off);
    }
    this.explodeAmt = next;
    this.poseDirty = true;
    this.shadowDirty = true;
    this.invalidate();
  }
  /** Half width and half height of the model at an explode amount, from the offsets in the data. */
  private extent(a: number): [number, number] {
    const t = this.extents;
    const [lo, hi, k] = a <= 0.5 ? [t[0]!, t[1]!, smooth(a / 0.5)] : [t[1]!, t[2]!, smooth((a - 0.5) / 0.5)];
    return [lerp(lo[0], hi[0], k), lerp(lo[1], hi[1], k)];
  }
  private explodeReach(a: number): number {
    const [w, h] = this.extent(a);
    return Math.max(w / this.extents[0]![0], h / this.extents[0]![1]);
  }
  private measureExtents(m: Model): void {
    const asm = new Map(m.assemblies.map((x) => [x.id, x]));
    const v = new THREE.Vector3();
    this.extents = [0, 1, 2].map((stage) => {
      const box = new THREE.Box3();
      for (const p of m.list) {
        if (p.decal) continue;
        v.copy(p.centre);
        if (p.group === 'elev') v.applyMatrix4(this.poseElev);
        if (stage >= 1) v.add(asm.get(p.assembly)?.offset ?? v.clone().set(0, 0, 0));
        if (stage >= 2) v.add(p.explode);
        box.expandByPoint(v);
      }
      const size = box.expandByScalar(0.1).getSize(new THREE.Vector3());
      this.centreY[stage] = (box.min.y + box.max.y) / 2;
      return [Math.max(size.x, size.z) / 2, size.y / 2] as [number, number];
    });
  }
  setXray(on: boolean): void {
    this.xray = on;
    this.invalidate();
  }
  setMeasure(active: boolean): void {
    this.measuring = active;
    this.measurePts = [];
    if (this.measureLine) {
      this.scene.remove(this.measureLine);
      this.measureLine.geometry.dispose();
      this.measureLine = null;
    }
    this.canvas.style.cursor = active ? 'crosshair' : '';
    this.invalidate();
  }
  setInsets(insets: SceneInsets): void {
    this.insets = insets;
    // Until the visitor takes the camera, keep the opening view fitted to the free area.
    if (!this.interacted && this.mode === 'model' && !this.frozenCamera && this.model) this.goHome(false);
    this.invalidate();
  }
  setReducedMotion(on: boolean): void {
    this.reduced = on;
  }
  setBlueprintView(_view: BlueprintView | null, _animate: boolean): void {
    // Blueprint treatment arrives with the feature-edge model.
  }
  setHiddenLines(_on: boolean): void {
    // As above.
  }

  // ── Commands ──────────────────────────────────────────────────────────────
  frame(target: { part: string } | { assembly: string } | null): void {
    if (!this.model || this.mode !== 'model') return;
    const sphere = new THREE.Sphere();
    if (target && 'part' in target) {
      const p = this.model.parts.get(target.part);
      if (!p) return;
      this.scene.updateMatrixWorld();
      sphere.center.copy(p.centre).applyMatrix4(p.node.matrixWorld);
      sphere.radius = Math.max(0.07, p.radius * 1.15);
    } else {
      const box = new THREE.Box3();
      const v = new THREE.Vector3();
      this.scene.updateMatrixWorld();
      for (const p of this.model.list) {
        if (p.gone || !p.node.visible || p.decal) continue;
        if (target && 'assembly' in target && p.assembly !== target.assembly) continue;
        box.expandByPoint(v.copy(p.centre).applyMatrix4(p.node.matrixWorld));
      }
      if (box.isEmpty()) return;
      box.expandByScalar(0.1);
      const size = box.getSize(v);
      const dir = this.camera.position.clone().sub(this.controls.target).normalize();
      this.flyTo(box.getCenter(new THREE.Vector3()), dir, this.fitDistance(Math.max(size.x, size.z) / 2, size.y / 2));
      return;
    }
    const dir = this.camera.position.clone().sub(this.controls.target).normalize();
    this.flyTo(sphere.center, dir, this.fitDistance(sphere.radius));
  }
  resetView(): void {
    this.goHome(true);
  }

  /** Distance at which a box of the given half width and half height fills the area the panels leave free. */
  private fitDistance(halfWidth: number, halfHeight = halfWidth): number {
    const w = Math.max(200, this.canvas.clientWidth - this.insets.left - this.insets.right);
    const h = Math.max(200, this.canvas.clientHeight - this.insets.top - this.insets.bottom);
    // Tangent of the half angle the free area subtends, vertically and horizontally.
    const tv = Math.tan((this.camera.fov * DEG) / 2) * (h / this.canvas.clientHeight);
    const th = tv * (w / h);
    return Math.max(halfHeight / tv, halfWidth / th) * 1.03 + halfWidth * 0.6;
  }

  private goHome(animate: boolean): void {
    const dir = new THREE.Vector3().setFromSphericalCoords(1, (90 - HOME.elevation) * DEG, HOME.azimuth * DEG);
    const [halfW, halfH] = this.extent(this.explodeAmt);
    const a = this.explodeAmt;
    const y = a <= 0.5 ? lerp(this.centreY[0]!, this.centreY[1]!, smooth(a / 0.5)) : lerp(this.centreY[1]!, this.centreY[2]!, smooth((a - 0.5) / 0.5));
    const centre = new THREE.Vector3(-0.03, y, 0.02);
    const dist = Math.min(this.controls.maxDistance, this.fitDistance(halfW, halfH));
    if (animate && !this.reduced) this.flyTo(centre, dir, dist);
    else {
      this.controls.target.copy(centre);
      this.camera.position.copy(centre).addScaledVector(dir, dist);
      this.controls.update();
      this.invalidate();
    }
  }

  private flyTo(target: THREE.Vector3, dir: THREE.Vector3, distance: number): void {
    const to: [THREE.Vector3, THREE.Vector3] = [target.clone().addScaledVector(dir, distance), target.clone()];
    if (to[0].y < 0.1) to[0].y = 0.1;
    if (this.reduced) {
      this.camera.position.copy(to[0]);
      this.controls.target.copy(to[1]);
      this.controls.update();
    } else {
      this.tween = { t: 0, dur: 0.75, from: [this.camera.position.clone(), this.controls.target.clone()], to };
    }
    this.invalidate();
  }

  // ── Pointer ───────────────────────────────────────────────────────────────
  private onPointerMove = (e: PointerEvent): void => {
    const r = this.canvas.getBoundingClientRect();
    this.pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    this.pointer.y = -((e.clientY - r.top) / r.height) * 2 + 1;
    this.pointer.cx = e.clientX;
    this.pointer.cy = e.clientY;
    this.pointer.inside = e.pointerType === 'mouse' && e.buttons === 0;
    this.pointer.moved = true;
    if (this.mode === 'model') this.invalidate();
  };
  private onPointerLeave = (): void => {
    this.pointer.inside = false;
    this.setHover(null);
  };
  private onPointerDown = (e: PointerEvent): void => {
    this.pointer.downX = e.clientX;
    this.pointer.downY = e.clientY;
    this.pointer.downT = performance.now();
    this.touch();
  };
  private onPointerUp = (e: PointerEvent): void => {
    if (this.mode !== 'model' || e.button !== 0) return;
    const still = Math.hypot(e.clientX - this.pointer.downX, e.clientY - this.pointer.downY) < 5;
    if (!still || performance.now() - this.pointer.downT > 450) return;
    this.onPointerMove(e);
    const hit = this.cast();
    if (this.measuring) {
      if (hit) this.addMeasurePoint(hit.point);
      return;
    }
    this.emit('pick', { part: hit?.part ?? null, clientX: e.clientX, clientY: e.clientY });
  };
  private onDoubleClick = (e: MouseEvent): void => {
    if (this.mode !== 'model' || this.measuring) return;
    const hit = this.cast();
    if (hit) this.emit('activate', { part: hit.part, clientX: e.clientX, clientY: e.clientY });
  };

  private cast(): { part: string; point: THREE.Vector3 } | null {
    if (!this.model) return null;
    this.raycaster.setFromCamera(new THREE.Vector2(this.pointer.x, this.pointer.y), this.camera);
    const hits = this.raycaster.intersectObjects(this.model.pick, false);
    for (const h of hits) {
      const p = this.model.parts.get(h.object.userData.part as string);
      if (p && this.canPick(p)) return { part: p.number, point: h.point };
    }
    return null;
  }

  private setHover(part: string | null): void {
    if (part === this.hovered) return;
    this.hovered = part;
    this.syncOutline();
    this.emit('hover', { part, clientX: this.pointer.cx, clientY: this.pointer.cy });
    this.invalidate();
  }

  private syncOutline(): void {
    const parts: PartRec[] = [];
    if (this.mode === 'model') {
      for (const n of [this.selected, this.hovered]) {
        const p = n ? this.model?.parts.get(n) : undefined;
        if (p && !parts.includes(p)) parts.push(p);
      }
    }
    this.outlineParts = parts;
  }

  private addMeasurePoint(point: THREE.Vector3): void {
    if (this.measurePts.length >= 2) this.measurePts = [];
    this.measurePts.push(point.clone());
    if (this.measureLine) {
      this.scene.remove(this.measureLine);
      this.measureLine.geometry.dispose();
      this.measureLine = null;
    }
    if (this.measurePts.length === 2) {
      const [a, b] = this.measurePts as [THREE.Vector3, THREE.Vector3];
      const mat = new THREE.LineBasicMaterial({ color: 0xd7dee3, depthTest: false, transparent: true });
      this.measureLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), mat);
      this.measureLine.renderOrder = 10;
      this.scene.add(this.measureLine);
      // glTF metres (x, y, z) → model millimetres (x, −z, y).
      const mm = (v: THREE.Vector3): [number, number, number] => [v.x * 1000, -v.z * 1000, v.y * 1000];
      this.emit('measure', { a: mm(a), b: mm(b), distanceMm: a.distanceTo(b) * 1000 });
    } else {
      this.emit('measure', null);
    }
    this.invalidate();
  }

  // ── Tour camera ───────────────────────────────────────────────────────────
  /** Camera for a station at progress t through its own move (position → position2). */
  private stationPose(s: Station, t: number, out: { pos: THREE.Vector3; target: THREE.Vector3 }): void {
    const a = new THREE.Vector3().fromArray(s.position);
    const ta = new THREE.Vector3().fromArray(s.target);
    if (!s.position2 || t <= 0) {
      out.pos.copy(a);
      out.target.copy(ta);
      return;
    }
    const b = new THREE.Vector3().fromArray(s.position2);
    const tb = new THREE.Vector3().fromArray(s.target2 ?? s.target);
    this.arc(a, ta, b, tb, t, out);
  }

  /** Blend two cameras by turning about the target, so the path goes round the robot and never through it. */
  private arc(a: THREE.Vector3, ta: THREE.Vector3, b: THREE.Vector3, tb: THREE.Vector3, t: number, out: { pos: THREE.Vector3; target: THREE.Vector3 }): void {
    const oa = a.clone().sub(ta);
    const ob = b.clone().sub(tb);
    const ra = oa.length();
    const rb = ob.length();
    const q = new THREE.Quaternion().setFromUnitVectors(oa.clone().normalize(), ob.clone().normalize());
    const dir = oa.normalize().applyQuaternion(new THREE.Quaternion().slerp(q, t));
    // Long turns swing a little wide so the figure stays whole in frame on the way round.
    const swing = Math.sin(Math.PI * t) * Math.min(0.5, oa.angleTo(ob) / Math.PI) * 0.35;
    out.target.lerpVectors(ta, tb, t);
    out.pos.copy(out.target).addScaledVector(dir, lerp(ra, rb, t) * (1 + swing));
    if (out.pos.y < 0.12) out.pos.y = 0.12;
  }

  private lensFov(lens: number, sensor: number): number {
    const aspect = this.camera.aspect;
    const half = Math.atan(sensor / 2 / lens);
    return (2 * (aspect >= 1 ? Math.atan(Math.tan(half) / aspect) : half)) / DEG;
  }

  private solveTour(dt: number): void {
    const n = this.stations.length;
    if (!n) return;
    const u = Math.min(n - 1, Math.max(0, this.tourU));
    const i = Math.min(n - 1, Math.floor(u));
    const p = u - i;
    const s = this.stations[i]!;
    const next = this.stations[i + 1];
    const here = { pos: new THREE.Vector3(), target: new THREE.Vector3() };
    // Within the section: the station's own move. Towards its end: travel to the next station.
    const own = ramp(p, 0.06, 0.52);
    const travel = next ? ramp(p, 0.6, 0.98) : 0;
    this.stationPose(s, own, here);
    let fov = this.lensFov(s.lens_mm, s.sensor_mm);
    if (next && travel > 0) {
      const there = { pos: new THREE.Vector3(), target: new THREE.Vector3() };
      this.stationPose(next, 0, there);
      this.arc(here.pos.clone(), here.target.clone(), there.pos, there.target, this.reduced ? Math.round(travel) : travel, here);
      fov = lerp(fov, this.lensFov(next.lens_mm, next.sensor_mm), travel);
    }
    const k = this.tourCam.ready && !this.reduced ? 1 - Math.exp(-dt * 7) : 1;
    this.tourCam.pos.lerp(here.pos, k);
    this.tourCam.target.lerp(here.target, k);
    this.tourCam.fov = lerp(this.tourCam.fov, fov, k);
    this.tourCam.ready = true;
    this.camera.position.copy(this.tourCam.pos);
    this.camera.fov = this.tourCam.fov;
    this.camera.lookAt(this.tourCam.target);
    this.camera.updateProjectionMatrix();
    if (this.tourCam.pos.distanceToSquared(here.pos) > 1e-6) this.dirty = true;

    // The station in charge of what is lit: this one until the camera is half way to the next.
    const lead = next && travel > 0.5 ? next : s;
    const elevOf = (st: Station) => (st.mount === 'deployed' ? 0 : 90);
    let elev = elevOf(s);
    if (s.mount_from && s.mount_to) elev = lerp(s.mount_from === 'deployed' ? 0 : 90, s.mount_to === 'deployed' ? 0 : 90, ramp(p, 0.1, 0.5));
    if (next) elev = lerp(elev, next.mount_from ? (next.mount_from === 'deployed' ? 0 : 90) : elevOf(next), travel);
    // The armour station takes the outer armour and the panels off while it is read.
    const stripFor = (st: Station) => (st.section === 'Armour and materials' ? 2 : 0);
    const strip = stripFor(s) * ramp(p, 0.12, 0.5) * (1 - travel);
    const want = [0, clamp01(strip), clamp01(strip - 1), 0, 0];
    let changed = Math.abs(elev - this.elev) > 0.01 || this.trav !== 0;
    for (let st = 1; st <= 4; st++) if (Math.abs(want[st]! - this.stripP[st]!) > 0.001) changed = true;
    if (changed) {
      this.elev = elev;
      this.trav = 0;
      this.stripP = want;
      this.poseDirty = true;
      this.shadowDirty = true;
    }
    const dimSet = lead.highlight?.length ? new Set(lead.highlight) : null;
    const same = (dimSet?.size ?? 0) === (this.tourDim?.size ?? 0) && [...(dimSet ?? [])].every((x) => this.tourDim?.has(x));
    if (!same || this.tourXray !== !!lead.xray) {
      this.tourDim = dimSet;
      this.tourXray = !!lead.xray;
      this.poseDirty = true;
    }
  }

  private effectiveXray(): boolean {
    return this.mode === 'dossier' ? this.tourXray : this.xray;
  }

  // ── Animation of the state numbers ────────────────────────────────────────
  private advance(dt: number): boolean {
    let busy = false;
    if (this.mode === 'model') {
      // Mount: stowing recentres the traverse before the barrel comes up.
      const stow = this.mountState === 'stowed';
      const travGoal = stow ? 0 : this.wantTrav;
      const elevGoal = stow ? (Math.abs(this.trav) > 0.4 ? this.elev : this.mountDef.elevRange[1]) : this.wantElev;
      if (this.lockDwell > 0) {
        this.lockDwell -= dt;
        busy = true;
      } else if (Math.abs(elevGoal - this.elev) > 0.004 || Math.abs(travGoal - this.trav) > 0.004 || Math.abs(this.elevVel.v) > 0.01) {
        this.elev = smoothDamp(this.elev, elevGoal, this.elevVel, 0.55, 52, dt);
        this.trav = smoothDamp(this.trav, travGoal, this.travVel, 0.35, 40, dt);
        this.poseDirty = this.shadowDirty = busy = true;
        this.emit('mount', { elevationDeg: this.elev, traverseDeg: this.trav, moving: true });
        if (Math.abs(elevGoal - this.elev) < 0.004 && Math.abs(travGoal - this.trav) < 0.004) {
          this.elev = elevGoal;
          this.trav = travGoal;
          this.elevVel.v = this.travVel.v = 0;
          this.emit('mount', { elevationDeg: this.elev, traverseDeg: this.trav, moving: false });
        }
      }
      // Strip-down: one stage at a time, in order, so several steps play as a sequence.
      const rate = dt / (this.reduced ? 0.3 : STRIP_SECONDS);
      for (let s = 1; s <= 4; s++) {
        if (s <= this.stripTarget && this.stripP[s]! < 1) {
          this.stripP[s] = Math.min(1, this.stripP[s]! + rate);
          this.poseDirty = this.shadowDirty = busy = true;
          break;
        }
      }
      for (let s = 4; s >= 1; s--) {
        if (s > this.stripTarget && this.stripP[s]! > 0) {
          this.stripP[s] = Math.max(0, this.stripP[s]! - rate);
          this.poseDirty = this.shadowDirty = busy = true;
          break;
        }
      }
      if (this.tween) {
        this.tween.t = Math.min(1, this.tween.t + dt / this.tween.dur);
        const k = smooth(this.tween.t);
        this.arc(this.tween.from[0], this.tween.from[1], this.tween.to[0], this.tween.to[1], k, { pos: this.camera.position, target: this.controls.target });
        if (this.tween.t >= 1) this.tween = null;
        busy = true;
      }
    } else if (this.mode === 'dossier') {
      this.solveTour(dt);
    }
    const xr = this.effectiveXray() ? 1 : 0;
    if (Math.abs(xr - this.xrayT) > 0.001) {
      this.xrayT = this.reduced ? xr : lerp(this.xrayT, xr, 1 - Math.exp(-dt * 9));
      if (Math.abs(xr - this.xrayT) < 0.004) this.xrayT = xr;
      this.poseDirty = busy = true;
    }
    return busy;
  }

  // ── State numbers → scene ─────────────────────────────────────────────────
  private applyPose(dt: number): boolean {
    const m = this.model;
    if (!m) return false;
    const d = this.mountDef;
    const E = new THREE.Matrix4().makeTranslation(d.ep).multiply(new THREE.Matrix4().makeRotationAxis(d.ea, this.elev * DEG)).multiply(new THREE.Matrix4().makeTranslation(d.ep.clone().negate()));
    this.poseTrav.makeTranslation(d.tp).multiply(new THREE.Matrix4().makeRotationAxis(d.ta, this.trav * DEG)).multiply(new THREE.Matrix4().makeTranslation(d.tp.clone().negate()));
    this.poseElev.multiplyMatrices(this.poseTrav, E);
    if (m.chain?.morphTargetInfluences) m.chain.morphTargetInfluences[0] = clamp01(this.elev / 90);

    const a = this.explodeAmt;
    const n = Math.max(1, m.assemblies.length - 1);
    for (const asm of m.assemblies) {
      const s1 = smooth((a / 0.5) * 1.3 - (0.3 * asm.index) / n);
      asm.node.position.copy(asm.offset).multiplyScalar(s1);
    }
    const xrayOn = this.xrayT > 0;
    const selecting = this.mode === 'model' && !!this.selected;
    // How bright everything that is not the subject is: the rest of the model beside a selection,
    // or the assemblies a dossier station is not about.
    const others = this.mode === 'dossier' ? 0.2 : 0.42;
    this.library.othersDim.value = others;
    const off = new THREE.Vector3();
    const T = new THREE.Matrix4();
    let settling = false;
    const kDim = this.reduced ? 1 : 1 - Math.exp(-dt * 10);

    for (const p of m.list) {
      const lead = p.host ?? p;
      const s2 = a > 0.5 ? smooth(((a - 0.5) / 0.5) * 1.25 - 0.25 * lead.order) : 0;
      off.copy(lead.explode).multiplyScalar(s2);
      let alpha = 1;
      const stage = this.stripP[p.strip] ?? 0;
      if (p.strip > 0 && stage > 0) {
        // Head first, feet last; each part's own clock runs inside the stage's.
        const u = clamp01((stage - p.delay * 0.3) / 0.7);
        if (this.reduced) alpha = 1 - stage;
        else if (p.fastener) {
          off.addScaledVector(p.axis, smooth(u / 0.3) * 0.03);
          alpha = 1 - ramp(u, 0.14, 0.34);
        } else {
          off.addScaledVector(p.dir, ramp(u, 0.2, 0.36) * 0.004 + smooth((u - 0.34) / 0.6) * p.lift);
          alpha = 1 - ramp(u, 0.62, 0.96);
        }
      }
      if (p.group) {
        p.node.matrix.copy(p.group === 'elev' ? this.poseElev : this.poseTrav).multiply(T.makeTranslation(off));
        p.node.matrixWorldNeedsUpdate = true;
      } else {
        p.node.position.copy(off);
      }

      const hiddenByUser = this.hidden.has(p.number) || (this.isolated !== null && (this.isolated.kind === 'part' ? this.isolated.id !== lead.number : this.isolated.id !== p.assembly));
      p.gone = alpha <= 0.004;
      p.node.visible = !p.gone && !(hiddenByUser && this.mode === 'model');
      if (xrayOn && p.cls === 'armour') alpha *= lerp(1, XRAY_ALPHA, this.xrayT);

      let dim = 1;
      if (selecting && lead.number !== this.selected) dim = others;
      if (this.mode === 'dossier' && this.tourDim && !this.tourDim.has(p.assembly)) dim = others;
      if (Math.abs(dim - p.dim) > 0.003) {
        p.dim = lerp(p.dim, dim, kDim);
        settling = true;
      } else p.dim = dim;

      const transparent = alpha < 0.995 || p.decal;
      const seeThrough = xrayOn && p.cls === 'armour';
      // Plain parts share materials; a part gets its own only while it fades, dims or is seen through.
      const state = transparent || seeThrough ? 2 : p.dim === 1 ? 0 : p.dim === others ? 1 : 2;
      if (state === 2) {
        p.own ??= p.sources.map((src, i) => this.library.create(p.keys[i]!, src, p.batch));
        p.own.forEach((mat, i) => {
          mat.userData.dim.value = p.dim;
          if (mat.opacity !== alpha) mat.opacity = alpha;
          if (!p.decal && mat.depthWrite === seeThrough) mat.depthWrite = !seeThrough;
          if (mat.transparent !== transparent) {
            mat.transparent = transparent;
            mat.needsUpdate = true;
          }
          if (p.matState !== 2) p.meshes[i]!.material = mat;
        });
      } else if (state !== p.matState) {
        p.meshes.forEach((mesh, i) => (mesh.material = this.library.pooled(p.keys[i]!, p.sources[i]!, p.batch, state === 1)));
      }
      p.matState = state;
      // A part that is fading out, or seen through, stops shading what is behind it.
      const casts = alpha > 0.5 && !p.decal;
      if (p.meshes[0] && p.meshes[0].castShadow !== casts) for (const mesh of p.meshes) mesh.castShadow = casts;
      p.transparent = transparent;
      p.alpha = alpha;
    }
    return settling;
  }

  private updateLabels(): void {
    const m = this.model;
    const show = !!m && this.mode === 'model' && this.explodeAmt >= 0.6;
    this.labels.hidden = !show;
    if (!show || !m) return;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (this.labels.childElementCount !== m.assemblies.length + 1) {
      this.labels.replaceChildren();
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      this.labels.appendChild(svg);
      for (const asm of m.assemblies) {
        svg.appendChild(document.createElementNS('http://www.w3.org/2000/svg', 'line'));
        const b = document.createElement('span');
        b.className = 'balloon';
        b.textContent = asm.id;
        this.labels.appendChild(b);
      }
    }
    const svg = this.labels.firstElementChild as SVGSVGElement;
    const mid = new THREE.Vector3(0, 1, 0).project(this.camera);
    const v = new THREE.Vector3();
    m.assemblies.forEach((asm, i) => {
      v.copy(asm.centre).add(asm.node.position).project(this.camera);
      const x = (v.x * 0.5 + 0.5) * w + this.shift.x;
      const y = (-v.y * 0.5 + 0.5) * h + this.shift.y;
      // The balloon stands off from the assembly, away from the middle of the figure.
      let dx = v.x - mid.x;
      let dy = -(v.y - mid.y);
      const len = Math.hypot(dx, dy) || 1;
      dx /= len;
      dy /= len;
      if (len < 0.02) {
        dx = 0.7;
        dy = -0.7;
      }
      const bx = Math.min(w - 20, Math.max(20, x + dx * 78));
      const by = Math.min(h - 20, Math.max(20, y + dy * 78));
      const line = svg.children[i] as SVGLineElement;
      line.setAttribute('x1', x.toFixed(1));
      line.setAttribute('y1', y.toFixed(1));
      line.setAttribute('x2', (bx - dx * 13).toFixed(1));
      line.setAttribute('y2', (by - dy * 13).toFixed(1));
      const b = this.labels.children[i + 1] as HTMLElement;
      b.style.transform = `translate(${bx.toFixed(1)}px, ${by.toFixed(1)}px)`;
      b.hidden = v.z > 1;
    });
  }

  private renderShadow(): void {
    const r = this.renderer;
    const [a, b] = this.shadowRT as [THREE.WebGLRenderTarget, THREE.WebGLRenderTarget];
    const bg = this.scene.background;
    const labelsLine = this.measureLine;
    this.scene.background = null;
    this.floor.visible = false;
    if (labelsLine) labelsLine.visible = false;
    this.scene.overrideMaterial = this.shadowDepth;
    const clear = r.getClearAlpha();
    r.setClearAlpha(0);
    r.setRenderTarget(a);
    r.clear();
    r.render(this.scene, this.shadowCam);
    this.scene.overrideMaterial = null;
    const mat = this.blur.material as THREE.ShaderMaterial;
    for (let i = 0; i < 2; i++) {
      mat.uniforms.tDiffuse!.value = a.texture;
      mat.uniforms.uDir!.value.set((1.6 + i * 2.2) / 512, 0);
      r.setRenderTarget(b);
      this.blur.render(r);
      mat.uniforms.tDiffuse!.value = b.texture;
      mat.uniforms.uDir!.value.set(0, (1.6 + i * 2.2) / 512);
      r.setRenderTarget(a);
      this.blur.render(r);
    }
    r.setRenderTarget(null);
    r.setClearAlpha(clear);
    this.scene.background = bg;
    this.floor.visible = true;
    if (labelsLine) labelsLine.visible = true;
  }

  // ── Loop ──────────────────────────────────────────────────────────────────
  private invalidate(): void {
    this.dirty = true;
  }
  private start(): void {
    if (!this.raf && !this.disposed) {
      this.last = performance.now();
      this.raf = requestAnimationFrame(this.tick);
    }
  }
  private tick = (now: number): void => {
    this.raf = 0;
    if (this.disposed || this.mode === 'idle' || !this.model) return;
    this.raf = requestAnimationFrame(this.tick);
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    const busy = this.advance(dt);
    if (this.mode === 'model') {
      if (this.controls.update()) this.dirty = true;
      if (this.pointer.moved && this.pointer.inside && !this.measuring) {
        this.pointer.moved = false;
        this.setHover(this.cast()?.part ?? null);
      }
    }
    // Shift the picture so that its centre sits in the middle of the area the panels leave free.
    const sx = this.frozenCamera ? 0 : (this.insets.left - this.insets.right) / 2;
    const sy = this.frozenCamera ? 0 : (this.insets.top - this.insets.bottom) / 2;
    if (Math.abs(sx - this.shift.x) > 0.5 || Math.abs(sy - this.shift.y) > 0.5) {
      this.shift.x = this.reduced ? sx : lerp(this.shift.x, sx, 1 - Math.exp(-dt * 8));
      this.shift.y = this.reduced ? sy : lerp(this.shift.y, sy, 1 - Math.exp(-dt * 8));
      this.dirty = true;
    }
    if (!busy && !this.dirty && !this.poseDirty) {
      // Nothing is moving. If the last frame was drawn at motion quality, draw the settled one in full.
      if ((this.needRefine || this.blobDirty) && now - this.lastRender > 140) this.frame_(dt, now);
      return;
    }
    this.frame_(dt, now);
    if (busy) this.dirty = true;
  };

  /** Draw one frame. */
  private frame_(dt = 0.016, now = performance.now()): void {
    const t0 = performance.now();
    // A frame that follows closely on the last one is part of a movement. Those may run
    // lighter; the frame drawn once things stop is always the full one.
    const moving = now - this.lastRender < 100;
    this.applySize(moving ? this.pixelRatio : this.maxPixelRatio);
    const mirror = !this.light && !(moving && this.lite);
    (this.floor.material as THREE.ShaderMaterial).uniforms.uReflect!.value = mirror ? LOOK.reflect : 0;
    this.needRefine = moving && (this.bufferRatio < this.maxPixelRatio || (this.lite && !this.light));

    if (this.poseDirty) {
      this.poseDirty = this.applyPose(dt);
      if (this.poseDirty) this.dirty = true;
    }
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (Math.abs(this.shift.x) > 0.5 || Math.abs(this.shift.y) > 0.5) this.camera.setViewOffset(w, h, -this.shift.x, -this.shift.y, w, h);
    else this.camera.clearViewOffset();
    this.scene.updateMatrixWorld();
    if (this.shadowDirty) {
      this.shadowDirty = false;
      this.renderer.shadowMap.needsUpdate = true;
      this.blobDirty = true;
    }
    // The soft contact shadow changes slowly: a few times a second is enough while things move.
    if (this.blobDirty && (!moving || now - this.lastBlob > 130)) {
      this.blobDirty = false;
      this.lastBlob = now;
      this.renderShadow();
    }
    this.dirty = false;
    this.renderer.info.reset();
    this.composer.render();
    this.drawCalls = this.renderer.info.render.calls;
    this.updateLabels();
    this.emit('camera', this.readout());

    // Frame pacing. The cost here is mostly draw calls, so the first thing to go is the floor
    // mirror (a second pass over the model); only after that does the resolution come down.
    if (moving) {
      this.intervals.push(now - this.lastRender);
      this.cpu.push(performance.now() - t0);
      if (this.intervals.length > 60) {
        this.intervals.shift();
        this.cpu.shift();
      }
      if (this.intervals.length >= 30) {
        const mean = this.intervals.reduce((x, y) => x + y, 0) / this.intervals.length;
        const floor = this.maxPixelRatio * 0.65;
        if (mean > 20) {
          if (!this.lite && !this.light) this.lite = true;
          else if (this.pixelRatio > floor) this.pixelRatio = Math.max(floor, this.pixelRatio * 0.85);
          this.intervals.length = 0;
          this.cpu.length = 0;
        } else if (mean < 14 && this.pixelRatio < this.maxPixelRatio) {
          this.pixelRatio = Math.min(this.maxPixelRatio, this.pixelRatio * 1.12);
          this.intervals.length = 0;
          this.cpu.length = 0;
        }
      }
    }
    this.lastRender = now;
  }

  private readout(): CameraReadout {
    const target = this.mode === 'dossier' ? this.tourCam.target : this.controls.target;
    const d = this.camera.position.clone().sub(target);
    const len = d.length() || 1;
    return {
      azimuthDeg: Math.atan2(d.x, d.z) / DEG,
      elevationDeg: Math.asin(d.y / len) / DEG,
      distanceMm: len * 1000,
    };
  }

  private resize(): void {
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h || !this.composer) return;
    this.maxPixelRatio = Math.min(2, window.devicePixelRatio || 1);
    if (!this.pixelRatio || this.pixelRatio > this.maxPixelRatio) this.pixelRatio = this.maxPixelRatio;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.applySize(this.maxPixelRatio, true);
    this.invalidate();
  }

  private applySize(ratio: number, force = false): void {
    if (!force && ratio === this.bufferRatio) return;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.bufferRatio = ratio;
    this.renderer.setPixelRatio(ratio);
    this.renderer.setSize(w, h, false);
    this.composer.setPixelRatio(ratio);
    this.composer.setSize(w, h);
    const pw = Math.floor(w * ratio);
    const ph = Math.floor(h * ratio);
    this.maskRT.setSize(pw, ph);
    this.maskMat.uniforms.uRes!.value.set(pw, ph);
    this.grade.uniforms.uTexel!.value.set(1 / pw, 1 / ph);
  }

  // ── Diagnostics used by the capture script ────────────────────────────────
  /** Put the camera exactly where an offline render was taken from, for side-by-side comparison. */
  debugCamera(position: Vec3 | null, target?: Vec3, lensMm?: number): void {
    this.frozenCamera = !!position;
    this.controls.enabled = !position && this.mode === 'model';
    if (position && target && lensMm) {
      this.tween = null;
      this.camera.position.fromArray(position);
      this.controls.target.fromArray(target);
      this.camera.fov = this.lensFov(lensMm, 36);
      this.camera.lookAt(this.controls.target);
    } else {
      this.camera.fov = LOOK.fov;
    }
    this.camera.updateProjectionMatrix();
    this.invalidate();
  }
  /** True when nothing is animating and the last frame is the settled one. */
  idle(): boolean {
    if (this.mode === 'idle') return true;
    return !this.dirty && !this.poseDirty && !this.needRefine && !this.blobDirty && !this.tween && this.lockDwell <= 0 && Math.abs(this.elevVel.v) < 0.01;
  }
  /** Spin the camera for a while and report the frame pacing. */
  async benchmark(seconds: number): Promise<SceneStats> {
    const start = performance.now();
    this.intervals.length = 0;
    await new Promise<void>((resolve) => {
      const step = () => {
        if (performance.now() - start > seconds * 1000) return resolve();
        const off = this.camera.position.clone().sub(this.controls.target).applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.012);
        this.camera.position.copy(this.controls.target).add(off);
        this.invalidate();
        requestAnimationFrame(step);
      };
      step();
    });
    return this.stats();
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.resizeObserver.disconnect();
    this.controls.dispose();
    this.library.dispose();
    this.labels.remove();
    this.renderer.dispose();
  }
}
