import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" — guro_id_api.py отдаёт index.html и /assets по относительным
// путям (см. handle_index в guro_id_api.py), без этого сборка ссылалась бы
// на /assets/... от корня домена.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
  },
});
