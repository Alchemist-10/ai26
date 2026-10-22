// Build-time check for clips other agents drop into public/clips. Missing files degrade to fallbacks.
import fs from "node:fs";
import path from "node:path";

const dir = path.join(process.cwd(), "public", "clips");
const base = import.meta.env.BASE_URL.replace(/\/$/, "");

export const clip = (name: string) => {
  const has = (ext: string) => fs.existsSync(path.join(dir, `${name}.${ext}`));
  const url = (ext: string) => `${base}/clips/${name}.${ext}`;
  return {
    webm: has("webm") ? url("webm") : undefined,
    mp4: has("mp4") ? url("mp4") : undefined,
    png: has("png") ? url("png") : undefined,
  };
};

export const hasClip = (name: string) => Object.values(clip(name)).some(Boolean);
