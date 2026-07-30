import { access, cp, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(here, "..");
const source = resolve(projectRoot, "..", "web", "dist");
const target = resolve(projectRoot, "public");

async function requireFile(path, description) {
  try {
    await access(path);
  } catch {
    throw new Error(`${description}不存在：${path}`);
  }
}

export async function stageDashboard({
  sourceDirectory = source,
  targetDirectory = target,
} = {}) {
  await requireFile(resolve(sourceDirectory, "index.html"), "Vite 生产首页");
  await requireFile(resolve(sourceDirectory, "assets"), "Vite 生产资源目录");
  await rm(targetDirectory, { recursive: true, force: true });
  await mkdir(targetDirectory, { recursive: true });
  await cp(sourceDirectory, targetDirectory, { recursive: true });
  return { source: sourceDirectory, target: targetDirectory };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = await stageDashboard();
  process.stdout.write(
    `Sites 前端资源已暂存：${result.source} -> ${result.target}\n`,
  );
}
