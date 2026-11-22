export interface GpuCapability {
  webgpu: boolean;
  webgl2: boolean;
}

/** What the browser can draw with. Cheap, synchronous, and leaves no context behind. */
export function detectCapability(): GpuCapability {
  const webgpu = typeof navigator !== 'undefined' && 'gpu' in navigator;
  let webgl2 = false;
  try {
    const probe = document.createElement('canvas');
    const gl = probe.getContext('webgl2', { failIfMajorPerformanceCaveat: false });
    webgl2 = !!gl;
    gl?.getExtension('WEBGL_lose_context')?.loseContext();
  } catch {
    webgl2 = false;
  }
  return { webgpu, webgl2 };
}
