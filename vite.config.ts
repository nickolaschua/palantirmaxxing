import { defineConfig } from "vite";
import cesium from "vite-plugin-cesium";

// Demo app build. The library build lives in vite.lib.config.ts.
export default defineConfig({
  plugins: [cesium()],
  server: { port: 5173 },
});
