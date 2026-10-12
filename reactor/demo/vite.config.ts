import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { defineConfig } from "vite";
const require = createRequire(import.meta.url);
const sdkDirectory = dirname(require.resolve("@reactor-team/js-sdk"));
export default defineConfig({
  optimizeDeps: {
    exclude: ["@reactor-team/js-sdk"],
    include: ["react", "react/jsx-runtime", "react/jsx-dev-runtime", "react-dom/client", "awaitqueue", "hls.js", "mp4box"],
  },
  plugins: [{name: "reactor-sdk-wasm-assets", generateBundle() {
    for (const name of ["reactor_wasm.js", "reactor_wasm_bg.wasm"]) {
      this.emitFile({type: "asset", fileName: `assets/wasm/${name}`, source: readFileSync(join(sdkDirectory, "wasm", name))});
    }
  }}],
});
