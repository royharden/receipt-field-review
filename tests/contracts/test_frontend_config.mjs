import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const packageConfig = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8"));
const typescript = JSON.parse(readFileSync(new URL("../../tsconfig.json", import.meta.url), "utf8"));
const vite = readFileSync(new URL("../../vite.config.ts", import.meta.url), "utf8");

test("bootstrap never presents a scaffold check as a frontend build", () => {
  assert.equal(packageConfig.private, true);
  assert.equal(packageConfig.scripts.build, undefined);
  assert.equal(packageConfig.dependencies, undefined);
  assert.ok(packageConfig.scripts["test:scaffold"].includes("node --test"));
});

test("future viewer configuration is root-portable and loopback bounded", () => {
  assert.match(vite, /root: "web"/);
  assert.match(vite, /outDir: "\.\.\/dist\/web"/);
  assert.equal((vite.match(/host: "127\.0\.0\.1"/g) ?? []).length, 2);
  assert.doesNotMatch(vite, /(?:port\s*:|0\.0\.0\.0|C:\\|VITE_.*(?:API_KEY|SECRET))/);
});

test("TypeScript configuration keeps application boundaries strict", () => {
  assert.equal(typescript.compilerOptions.strict, true);
  assert.equal(typescript.compilerOptions.noEmit, true);
  assert.equal(typescript.compilerOptions.noUnusedLocals, true);
  assert.equal(typescript.compilerOptions.moduleResolution, "Bundler");
});
