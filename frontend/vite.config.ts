import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const apiTarget = process.env.AI26_API_TARGET ?? `http://127.0.0.1:${process.env.AI26_BACKEND_PORT ?? "8001"}`
const frontendPort = Number(process.env.AI26_FRONTEND_PORT ?? "5174")

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: frontendPort,
    strictPort: true,
    proxy: {
      "/api": apiTarget,
    },
  },
  preview: {
    host: "127.0.0.1",
    port: frontendPort,
    strictPort: true,
  },
})
