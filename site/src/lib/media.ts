// Build-time lookup for assets other agents produce. Missing files resolve to
// undefined so the page renders a fallback instead of breaking the build.
import type { ImageMetadata } from "astro";
import { existsSync } from "node:fs";
import { join } from "node:path";

const files = import.meta.glob<{ default: ImageMetadata }>("../assets/screens/*.{png,webp}", { eager: true });

export function screen(name: string): ImageMetadata | undefined {
  const at = (ext: string) => files[`../assets/screens/${name}.${ext}`]?.default;
  return at("png") ?? at("webp");
}

export interface Clip { webm?: string; mp4?: string; poster?: string }

const base = import.meta.env.BASE_URL.replace(/\/$/, "");
const clipDir = join(process.cwd(), "public", "clips");

export function clip(name: string): Clip | undefined {
  const url = (ext: string) => (existsSync(join(clipDir, `${name}.${ext}`)) ? `${base}/clips/${name}.${ext}` : undefined);
  const c = { webm: url("webm"), mp4: url("mp4"), poster: url("png") };
  return c.webm || c.mp4 ? c : undefined;
}
