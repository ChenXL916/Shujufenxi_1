import assert from "node:assert/strict";
import { access, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import { join } from "node:path";
import test from "node:test";

import { stageDashboard } from "../scripts/stage-dashboard.mjs";

test("stages the complete Vite build and replaces stale assets", async () => {
  const directory = await mkdtemp(join(os.tmpdir(), "liveops-sites-"));
  const source = join(directory, "dist");
  const target = join(directory, "public");
  await mkdir(join(source, "assets"), { recursive: true });
  await mkdir(target, { recursive: true });
  await writeFile(join(source, "index.html"), "<title>dashboard</title>");
  await writeFile(join(source, "assets", "app.js"), "export {};");
  await writeFile(join(target, "stale.js"), "stale");

  await stageDashboard({
    sourceDirectory: source,
    targetDirectory: target,
  });

  assert.equal(
    await readFile(join(target, "index.html"), "utf8"),
    "<title>dashboard</title>",
  );
  assert.equal(
    await readFile(join(target, "assets", "app.js"), "utf8"),
    "export {};",
  );
  await assert.rejects(access(join(target, "stale.js")));
});

test("refuses to stage an incomplete Vite build", async () => {
  const directory = await mkdtemp(join(os.tmpdir(), "liveops-sites-"));
  await assert.rejects(
    stageDashboard({
      sourceDirectory: directory,
      targetDirectory: join(directory, "public"),
    }),
    /Vite 生产首页不存在/,
  );
});
