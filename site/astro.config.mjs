// @ts-check
import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";

// GitHub Pages project site: https://moneytosms.github.io/ai26/
export default defineConfig({
  site: "https://moneytosms.github.io",
  base: "/ai26",
  trailingSlash: "ignore",
  integrations: [react()],
  vite: { plugins: [tailwindcss()] },
});
