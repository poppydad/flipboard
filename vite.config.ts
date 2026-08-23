import { defineConfig } from "vite";

export default defineConfig({
  root: "renderer",
  server: {
    port: 5173,
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
