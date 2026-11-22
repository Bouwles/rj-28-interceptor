// Number formatting. Every figure on screen passes through here from a data file.

const MINUS = '−';

function group(intPart: string): string {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** Fixed decimals with thousands grouping and a true minus sign. */
export function num(v: number, digits = 0): string {
  const s = Math.abs(v).toFixed(digits);
  const [i, f] = s.split('.');
  const body = f ? `${group(i!)}.${f}` : group(i!);
  return (v < 0 && Number(s) !== 0 ? MINUS : '') + body;
}

/** One decimal unless the value is a whole number. */
export function trim1(v: number): string {
  return num(v, Math.abs(v - Math.round(v)) < 0.05 ? 0 : 1);
}

export function mm(v: number): string {
  return `${trim1(v)} mm`;
}

export function kg(v: number, digits = 2): string {
  return `${num(v, digits)} kg`;
}

/** Part masses span five orders of magnitude; small ones read better in grams. */
export function partMass(kgValue: number): string {
  if (kgValue >= 1) return `${num(kgValue, 2)} kg`;
  const g = kgValue * 1000;
  if (g < 1) return '< 1 g';
  return `${num(g, 0)} g`;
}

export function deg(v: number, signed = false): string {
  const body = trim1(v);
  return `${signed && v > 0 ? '+' : ''}${body}°`;
}

export function range(r: readonly [number, number]): string {
  const [a, b] = r;
  if (a === -b) return `±${trim1(Math.abs(b))}°`;
  return `${deg(a, a < 0)} to ${deg(b, a < 0)}`;
}

export function dims(size: readonly number[]): string {
  return size.map((v) => trim1(v)).join(' × ');
}

export function pct(v: number, digits = 0): string {
  return `${num(v, digits)}%`;
}

export function megabytes(bytes: number): string {
  return (bytes / 1e6).toFixed(2);
}

export function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** `hip_yaw_L` → `Hip yaw`. */
export function jointLabel(name: string): string {
  const base = name.replace(/_[LR]$/, '').replace(/_/g, ' ').replace(/(\D)(\d)/g, '$1 $2');
  return base.charAt(0).toUpperCase() + base.slice(1);
}
