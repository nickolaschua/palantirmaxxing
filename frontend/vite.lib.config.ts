import { defineConfig } from "vite";

// Library build. Cesium is external — the host app supplies it, so we don't
// ship a second copy of a 6 MB engine into whatever consumes this.
export default defineConfig({
  build: {
    outDir: "dist-lib",
    lib: {
      entry: "src/lib/index.ts",
      name: "SingaporeCanvas",
      fileName: "singapore-canvas",
      formats: ["es"],
    },
    rollupOptions: { external: ["cesium"] },
  },
});
