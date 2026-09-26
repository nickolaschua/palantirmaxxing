import { defineConfig, loadEnv } from "vite";
import cesium from "vite-plugin-cesium";

// Demo app build. The library build lives in vite.lib.config.ts.
export default defineConfig(({ mode }) => ({
  plugins: [cesium()],
  // The decision demo imports the backend's result from ../data/results.
  server: { host: "127.0.0.1", port: 5173, strictPort: true, fs: { allow: [".."] },
    proxy: { "/api": { target: loadEnv(mode, ".", "MVP_").MVP_API_TARGET ?? "http://127.0.0.1:8000" } } },
}));
