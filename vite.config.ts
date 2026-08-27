import { defineConfig } from "vite";

export default defineConfig({
  root: "renderer",
  // `npm run build` emits a static bundle to dist/ at the repo root, which
  // service/main.py serves directly. That's what runs on the Pi — the dev
  // server below is for development on a laptop, not for the real board.
  build: {
    outDir: "../dist",
    emptyOutDir: true,
    rollupOptions: { input: "renderer/display.html" },
  },
  server: {
    port: 5173,
    // Bind to the LAN interface, not just localhost, so a phone/TV on the
    // same Wi-Fi can reach it (e.g. http://<this machine's LAN IP>:5173) —
    // needed for interim testing before the Pi + kiosk display exist.
    host: true,
    // Dev-only bridge to the FastAPI service (`uvicorn service.main:app`).
    // Keeps the renderer same-origin with the API, matching how it'll be
    // served in production — no CORS needed on either side.
    proxy: {
      "/current": "http://localhost:8000",
      "/message": "http://localhost:8000",
      "/queue": "http://localhost:8000",
      "/next": "http://localhost:8000",
      "/compose": "http://localhost:8000",
    },
  },
});
