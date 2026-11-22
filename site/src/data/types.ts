// Shapes of the JSON files the Blender build writes. Millimetres, Z up,
// robot faces −Y, robot's left is +X, origin on the floor between the feet.

export type Vec3 = [number, number, number];

export interface Box {
  min: Vec3;
  max: Vec3;
  width: number;
  depth: number;
  height: number;
}

export type JointGroup = 'leg' | 'waist' | 'arm' | 'hand' | 'neck' | 'mount';

export interface Joint {
  name: string;
  group: JointGroup;
  origin: Vec3;
  axis: Vec3;
  range: [number, number];
  drive: string;
}

export interface AssemblyMass {
  assembly: string;
  name: string;
  parts: number;
  mass_kg: number;
}

export interface DesignNote {
  title: string;
  inputs?: Record<string, unknown>;
  working: string[];
  result: Record<string, number>;
  verdict: string;
}

export interface Spec {
  designation: string;
  klass: string;
  serial: string;
  envelope: { deployed: Box; stowed: Box };
  body: Box;
  height_to_cap_crown: number;
  shoulder_armour_span: number;
  landmarks: Record<string, number>;
  joints: Joint[];
  dof: Record<string, number> & { total: number };
  mount: {
    barrel_od: number;
    barrel_length: number;
    elevation: [number, number];
    traverse: number;
    trunnion: Vec3;
    bore_rise: number;
    /** Smallest gap found by the swept-volume check, and the gap it had to beat. */
    min_clearance_mm?: number;
    required_clearance_mm?: number;
  };
  targets: {
    power: string;
    pack_voltage: number;
    pack_kwh: number;
    average_draw_kw: number;
    walk_kmh: number;
    run_kmh: number;
    sealing: string;
    mass_ready_kg: number;
  };
  mass: {
    total_kg: number;
    target_kg: number;
    error_pct: number;
    fill_factors: Record<string, number>;
    common_scale: number;
    by_assembly: AssemblyMass[];
    by_class: Record<string, number>;
  };
  part_count: number;
  /** Strip-down stages: what each one removes. Stage 0 is what stays. */
  strip?: { stage: number; title: string; parts: number; mass_kg: number }[];
  design_notes: DesignNote[];
}

export type MountGroup = '' | 'elev' | 'trav';

export interface Part {
  number: string;
  name: string;
  node: string;
  assembly: string;
  assembly_name: string;
  material: string;
  material_key: string;
  material_class: string;
  function: string;
  bbox_min: Vec3;
  bbox_max: Vec3;
  size: Vec3;
  volume_cm3: number;
  density: number;
  count: number;
  mount_group: MountGroup;
  explode_stage: number;
  explode_offset: Vec3;
  mass_kg: number;
  /** Strip-down stage that removes the part; 0 stays to the end. */
  strip?: number;
}

export interface Assembly {
  id: string;
  name: string;
  parts: Part[];
  mass_kg: number;
}

/** Tour camera station, glTF axes (+Y up, robot faces +Z), metres. */
export interface Station {
  id: string;
  position: Vec3;
  target: Vec3;
  lens_mm: number;
  sensor_mm: number;
  mount?: 'stowed' | 'deployed';
  focus?: string;
  highlight?: string[];
  xray?: boolean;
  /** Section name and the station's own title, as authored. */
  section?: string;
  title?: string;
  position2?: Vec3;
  target2?: Vec3;
  /** How the camera goes from `position` to `position2` within the section: `orbit` or `dolly`. */
  move?: string;
  mount_from?: 'stowed' | 'deployed';
  mount_to?: 'stowed' | 'deployed';
}

/** Loose on purpose: the scene module owns the reading of this file. */
export type MountData = Record<string, unknown>;

export interface ModelManifest {
  [key: string]: unknown;
}

export interface SheetPlace {
  /** Centre, in sheet units. */
  x: number;
  y: number;
  /** Size of the visible line work, or of the balloon. */
  w: number;
  h: number;
  /** Id of the view group the place belongs to. */
  view: string;
  balloon: boolean;
  /** For a balloon: where its leader ends. */
  target?: { x: number; y: number };
}

export interface Sheet {
  id: string;
  number: string;
  title: string;
  scale: string;
  url: string;
  /** Key of the file in the asset manifest, for the byte counter. */
  key: string;
  width: number;
  height: number;
  /** Part number or assembly id → where it appears on this sheet. */
  places: Map<string, SheetPlace[]>;
  placeholder: boolean;
}

export interface SheetSet {
  sheets: Sheet[];
  pdfUrl: string | null;
  /** Revision letter of the drawing set. */
  revision: string | null;
  placeholder: boolean;
}
