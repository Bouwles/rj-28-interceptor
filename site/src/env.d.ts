/// <reference types="vite/client" />

declare const __HAS_SHEETS__: boolean;

declare module 'virtual:asset-manifest' {
  const manifest: Record<string, { bytes: number; width?: number; height?: number }>;
  export default manifest;
}
