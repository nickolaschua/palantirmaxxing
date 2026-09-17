import { defineConfig } from "vite";
import cesium from "vite-plugin-cesium";

// Demo app build. The library build lives in vite.lib.config.ts.
export default defineConfig({
  plugins: [cesium()],
  // The decision demo imports the backend's result from ../data/results.
  server: { port: 5173, fs: { allow: [".."] } },
});
