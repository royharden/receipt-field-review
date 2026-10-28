/** Authored transport/React controls only; no HTTP listener, Python, OCR or model execution. */
import assert from "node:assert/strict";
import { File } from "node:buffer";
import { webcrypto } from "node:crypto";
import test from "node:test";
import { JSDOM } from "jsdom";
import { ApiError, HttpReviewApi, IMAGE_LIMIT, imageDigest } from "../../web/http.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://127.0.0.1:24002" });
for (const name of ["window", "document", "navigator", "HTMLElement", "Node", "MutationObserver"])
  Object.defineProperty(globalThis, name, { configurable: true, value: name === "window" ? dom.window : dom.window[name] });
if (!globalThis.crypto) Object.defineProperty(globalThis, "crypto", { value: webcrypto });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = await import("react");
const { render, fireEvent, screen, waitFor, cleanup } = await import("@testing-library/react");
const { App, ImageImport } = await import("../../web/main.tsx");
test.afterEach(cleanup);

const batch = "a".repeat(32), origin = "http://127.0.0.1:24002";
const token = "synthetic-image-flow-capability-00000000";
const hash = "b".repeat(64), item = "receipt-image:" + hash;
const spec = { schema_version: 1, method: "B0", config_ref: "receipt-image-local/1",
  reference_date: "2026-10-14", images: { [item]: { schema_version: 1, original_sha256: hash, expected_revision: null } } };
const input = { schema_version: 1, request_id: "authored-image-request", spec };
const jobId = await imageDigest(new TextEncoder().encode(input.request_id).buffer);
function staged(sha = hash, size = 3) {
  return { schema_version: 1, item_id: "receipt-image:" + sha, original_sha256: sha,
    original_bytes: size, original_format: "PNG", normalized_png_sha256: "c".repeat(64),
    width: 100, height: 60, ocr_executed: false };
}
function pendingJob(request = input, id = jobId) {
  return { schema_version: 1, job_id: id, request_id: request.request_id, spec: request.spec,
    state: "pending", execution_config_sha256: "d".repeat(64), started_at: null, ended_at: null,
    execution_origin: "not_run", model_cost_usd: null, model_cost_status: "not_run",
    items: Object.fromEntries(Object.keys(request.spec.images).map(key => [key,
      { schema_version: 1, status: "queued", result_revision: null, reason: null }])) };
}

test("binary stage keeps exact private PUT bytes and rejects staging success for another image or OCR", async () => {
  // what_bug_this_catches: JSON/base64 upload or a mismatched acknowledgement could label the wrong image as staged.
  const bytes = new Blob([new Uint8Array([1, 2, 3])]); let observed;
  const api = new HttpReviewApi(token, origin, async (url, init) => {
    observed = { url, init }; return Response.json(staged());
  });
  assert.equal((await api.stageImage(batch, hash, bytes)).ocr_executed, false);
  assert.equal(observed.url, `${origin}/api/batches/${batch}/images/${hash}`);
  assert.equal(observed.init.method, "PUT"); assert.equal(observed.init.body, bytes);
  assert.equal(observed.init.headers["Content-Type"], "application/octet-stream");
  assert.equal(observed.init.headers["X-RFR-Token"], token);
  assert.equal(observed.init.mode, "same-origin"); assert.equal(observed.init.redirect, "error");
  assert.ok(!observed.url.includes(token));
  for (const value of [{ ...staged(), original_sha256: "e".repeat(64) },
    { ...staged(), ocr_executed: true }, { ...staged(), original_bytes: 4 }]) {
    const bad = new HttpReviewApi(token, origin, async () => Response.json(value));
    await assert.rejects(bad.stageImage(batch, hash, bytes), /image_stage_identity_refused/);
  }
});

test("invalid image size/identity refuses before fetch", async () => {
  // what_bug_this_catches: oversized buffers or path-shaped identities reaching the upload route.
  let calls = 0;
  const api = new HttpReviewApi(token, origin, async () => { calls++; return Response.json(staged()); });
  for (const [b, sha, bytes] of [["../batch", hash, new Blob(["x"])],
    [batch, "../hash", new Blob(["x"])], [batch, hash, new Blob([])],
    [batch, hash, new Blob([new Uint8Array(IMAGE_LIMIT + 1)])]])
    await assert.rejects(api.stageImage(b, sha, bytes));
  assert.equal(calls, 0);
});

test("job start freezes cohort/revisions/date; status is GET and rejects a changed or incomplete cohort", async () => {
  // what_bug_this_catches: a response could silently drop one requested image, substitute intent, or dispatch work on status reads.
  const seen = [];
  const api = new HttpReviewApi(token, origin, async (url, init) => {
    seen.push({ url, init }); return Response.json(pendingJob());
  });
  await api.startImageJob(batch, input); await api.startImageJob(batch, input);
  await api.imageJob(batch, jobId);
  assert.equal(seen[0].init.body, seen[1].init.body);
  assert.deepEqual(JSON.parse(seen[0].init.body), input);
  assert.equal(seen[2].init.method, "GET"); assert.equal(seen[2].init.body, undefined);
  for (const value of [{ ...pendingJob(), items: {} },
    { ...pendingJob(), spec: { ...spec, reference_date: "2026-10-15" } },
    { ...pendingJob(), job_id: "f".repeat(64) }]) {
    const bad = new HttpReviewApi(token, origin, async () => Response.json(value));
    await assert.rejects(bad.startImageJob(batch, input), /image_job_identity_refused/);
  }
  const fakeSuccess = pendingJob(); fakeSuccess.state = "complete";
  const bad = new HttpReviewApi(token, origin, async () => Response.json(fakeSuccess));
  await assert.rejects(bad.imageJob(batch, jobId), /image_job_identity_refused/);
});

function mount(api, options = {}) {
  const locks = [], settled = [];
  render(React.createElement(ImageImport, { api, batch, uploadAvailable: true, workerAvailable: true,
    disabled: false, lock: value => locks.push(value), settled: async () => { settled.push(true); }, ...options }));
  return { locks, settled };
}
async function chooseAndStage(files) {
  fireEvent.change(screen.getByLabelText("Receipt image files"), { target: { files } });
  fireEvent.click(screen.getByRole("button", { name: "Stage remaining images" }));
}

test("lost start acknowledgement retains exact frozen request; status reports every partial outcome", async () => {
  // what_bug_this_catches: retrying after a timeout with a new ID, changed reference date or current revisions can execute another job.
  const requests = []; let frozen, id, itemReads = 0;
  const firstFile = new File(["one"], "one.png"), secondFile = new File(["two"], "two.png");
  const firstSha = await imageDigest(await firstFile.arrayBuffer()), priorRevision = "f".repeat(64);
  const api = {
    async stageImage(_batch, sha, bytes) { return staged(sha, bytes.size); },
    async items() { itemReads++; return [{ item_id: "receipt-image:" + firstSha, revision: priorRevision, deleted: false }]; },
    async startImageJob(_batch, request) {
      requests.push(JSON.stringify(request)); frozen = request;
      id = await imageDigest(new TextEncoder().encode(request.request_id).buffer);
      if (requests.length === 1) throw new Error("authored lost acknowledgement");
      return pendingJob(request, id);
    },
    async imageJob() {
      const result = pendingJob(frozen, id), keys = Object.keys(result.items);
      result.state = "partial"; result.execution_origin = "local_image_pipeline";
      result.model_cost_status = "not_applicable";
      result.items[keys[0]] = { schema_version: 1, status: "ok", result_revision: "e".repeat(64), reason: null };
      result.items[keys[1]] = { schema_version: 1, status: "stale", result_revision: null, reason: "source_revision_changed" };
      return result;
    },
  };
  const state = mount(api);
  await chooseAndStage([firstFile, secondFile]);
  await waitFor(() => assert.equal(screen.getAllByText("Staged · OCR not run").length, 2));
  await waitFor(() => assert.equal(screen.getByLabelText("Extraction reference date").disabled, false));
  assert.equal(state.settled.length, 0, "staging is not extraction/review success");
  fireEvent.change(screen.getByLabelText("Extraction reference date"), { target: { value: "2026-10-14" } });
  fireEvent.click(screen.getByRole("button", { name: "Start selected images" }));
  await screen.findByRole("alert");
  assert.equal(screen.getByLabelText("Extraction reference date").disabled, true);
  assert.equal(screen.getByRole("button", { name: "Clear image workflow" }).disabled, true);
  assert.equal(state.locks.at(-1), true, "unknown acknowledgement must keep the outer workflow locked");
  fireEvent.click(screen.getByRole("button", { name: "Retry frozen image job" }));
  await screen.findByText("Image job: pending");
  assert.equal(screen.getByRole("button", { name: "Clear image workflow" }).disabled, true);
  assert.equal(screen.getByLabelText("Extraction reference date").disabled, true);
  assert.equal(requests.length, 2); assert.equal(requests[0], requests[1]);
  assert.equal(itemReads, 1, "retry must not refresh the frozen source revision/cohort");
  assert.equal(JSON.parse(requests[0]).spec.images["receipt-image:" + firstSha].expected_revision, priorRevision);
  await waitFor(() => assert.equal(screen.getByRole("button", { name: "Read persisted image job status" }).disabled, false));
  fireEvent.click(screen.getByRole("button", { name: "Read persisted image job status" }));
  await screen.findByText("Image job: partial");
  assert.match(screen.getByLabelText("Image job result").textContent, /ok/);
  assert.match(screen.getByLabelText("Image job result").textContent, /stale/);
  await waitFor(() => assert.equal(state.settled.length, 1));
  assert.equal(requests.length, 2, "status reads never submit another job");
  assert.ok(state.locks.includes(true));
});

test("confirmed pre-admission worker refusal permits clear and restores the app workflow despite missing job status", async t => {
  // what_bug_this_catches: a definite 503 before job creation froze a nonexistent job and disabled all app recovery.
  // Authored transport models the pinned server ordering; no backend or persistence implementation runs here.
  const previous = Object.fromEntries(["fetch", "location", "history"].map(key => [key,
    Object.getOwnPropertyDescriptor(globalThis, key)]));
  let refused, statusReads = 0;
  const reviewedItem = "authored-recognized-item";
  const summary = { item_id: reviewedItem, revision: "e".repeat(64), deleted: false, clean: false,
    unfinished_fields: [], unresolved_issues: [] };
  const detail = { schema_version: 1, image_available: false, review: {
    ...summary, document: { source_kind: "native_text", pages: [] }, fields: {}, checks: [],
  } };
  const fetcher = async (url, init) => {
    const path = new URL(url).pathname;
    if (path === "/api/status") return Response.json({ contract: "receipt-api/1", currencies: ["USD"],
      capabilities: { image_upload: true, local_b0: true } });
    if (path === `/api/batches/${batch}/items`) return Response.json([summary]);
    if (path === `/api/batches/${batch}/items/${reviewedItem}`) return Response.json(detail);
    if (init.method === "PUT" && path.startsWith(`/api/batches/${batch}/images/`))
      return Response.json(staged(path.split("/").at(-1), init.body.size));
    if (init.method === "POST" && path === `/api/batches/${batch}/image-jobs`) {
      refused = JSON.parse(init.body);
      return Response.json({ error: "image_worker_unavailable" }, { status: 503 });
    }
    if (init.method === "GET" && path.startsWith(`/api/batches/${batch}/image-jobs/`)) {
      statusReads++;
      return Response.json({ error: "job_not_found" }, { status: 404 });
    }
    assert.fail(`unexpected authored transport request: ${init.method} ${path}`);
  };
  for (const [key, value] of Object.entries({ fetch: fetcher, location: dom.window.location, history: dom.window.history }))
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  t.after(() => {
    cleanup(); dom.window.history.replaceState(null, "", "/");
    for (const [key, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  });
  render(React.createElement(App));
  fireEvent.change(screen.getByLabelText("Local capability"), { target: { value: token } });
  fireEvent.change(screen.getByLabelText("Existing batch ID (optional)"), { target: { value: batch } });
  fireEvent.click(screen.getByRole("button", { name: "Connect to local API" }));
  await screen.findByRole("button", { name: "Reload state" });
  const actions = ["Disconnect", "Create batch", "Open batch", "Download export", "Reload state"];
  await waitFor(() => { for (const name of actions) assert.equal(screen.getByRole("button", { name }).disabled, false); });
  await chooseAndStage([new File(["refused"], "refused.png")]);
  await screen.findByText("Staged · OCR not run");
  await waitFor(() => assert.equal(screen.getByLabelText("Extraction reference date").disabled, false));
  fireEvent.change(screen.getByLabelText("Extraction reference date"), { target: { value: "2026-10-14" } });
  fireEvent.click(screen.getByRole("button", { name: "Start selected images" }));
  assert.match((await screen.findByRole("alert")).textContent, /No image job was created/);
  assert.equal(screen.getByRole("button", { name: "Clear image workflow" }).disabled, false);
  assert.equal(screen.getByLabelText("Extraction reference date").disabled, false);
  assert.equal(screen.getByLabelText("Include refused.png").disabled, false);
  assert.equal(screen.queryByRole("button", { name: "Retry frozen image job" }), null);
  assert.equal(screen.queryByRole("button", { name: "Read persisted image job status" }), null);
  assert.equal(screen.queryByLabelText("Image job result"), null);
  for (const name of actions) assert.equal(screen.getByRole("button", { name }).disabled, true,
    "the retained image selection still locks outer actions until explicitly cleared");
  assert.equal(statusReads, 0, "recovery must not require finding a job that was never admitted");
  const refusedId = await imageDigest(new TextEncoder().encode(refused.request_id).buffer);
  await assert.rejects(new HttpReviewApi(token, origin, fetcher).imageJob(batch, refusedId),
    e => e instanceof ApiError && e.status === 404 && e.message === "job_not_found");
  assert.equal(statusReads, 1, "the authored missing-job response is distinct from an accepted record");
  fireEvent.click(screen.getByRole("button", { name: "Clear image workflow" }));
  await waitFor(() => { for (const name of actions) assert.equal(screen.getByRole("button", { name }).disabled, false); });
  assert.equal(screen.getByLabelText("Receipt image files").disabled, false);
  fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
  await screen.findByRole("button", { name: "Connect to local API" });
});

for (const [label, refusal] of [
  ["other 503 code", new ApiError(503, "request_refused")],
  ["same code with another status", new ApiError(500, "image_worker_unavailable")],
  ["untyped matching text", new Error("image_worker_unavailable")],
]) test(`uncertain start failure retains exact intent and lock: ${label}`, async () => {
  // what_bug_this_catches: broad 5xx/code/text classification could abandon an admitted job after an unknown ACK.
  const requests = []; let itemReads = 0;
  const api = { async stageImage(_batch, sha, bytes) { return staged(sha, bytes.size); },
    async items() { itemReads++; return []; },
    async startImageJob(_batch, value) { requests.push(JSON.stringify(value)); throw refusal; },
    async imageJob() { throw new ApiError(404, "job_not_found"); },
  };
  const state = mount(api);
  await chooseAndStage([new File(["uncertain"], "uncertain.png")]);
  await screen.findByText("Staged · OCR not run");
  await waitFor(() => assert.equal(screen.getByLabelText("Extraction reference date").disabled, false));
  fireEvent.change(screen.getByLabelText("Extraction reference date"), { target: { value: "2026-10-14" } });
  fireEvent.click(screen.getByRole("button", { name: "Start selected images" }));
  await screen.findByRole("alert");
  assert.equal(screen.getByRole("button", { name: "Clear image workflow" }).disabled, true);
  assert.equal(screen.getByLabelText("Extraction reference date").disabled, true);
  assert.equal(screen.getByLabelText("Include uncertain.png").disabled, true);
  assert.equal(state.locks.at(-1), true);
  fireEvent.click(screen.getByRole("button", { name: "Read persisted image job status" }));
  await waitFor(() => assert.match(screen.getByRole("alert").textContent, /job_not_found/));
  assert.equal(screen.getByRole("button", { name: "Clear image workflow" }).disabled, true,
    "a missing status response alone cannot resolve unknown admission");
  fireEvent.click(screen.getByRole("button", { name: "Retry frozen image job" }));
  await waitFor(() => assert.equal(requests.length, 2));
  assert.equal(requests[0], requests[1]); assert.equal(itemReads, 1);
  assert.equal(state.settled.length, 0);
});

test("an accepted job remains frozen when status returns the worker refusal code", async () => {
  // what_bug_this_catches: POST-only non-admission evidence must not be inferred from a failed GET for an accepted job.
  let request, id;
  const api = { async stageImage(_batch, sha, bytes) { return staged(sha, bytes.size); },
    async items() { return []; },
    async startImageJob(_batch, value) {
      request = value; id = await imageDigest(new TextEncoder().encode(value.request_id).buffer);
      return pendingJob(value, id);
    },
    async imageJob() { throw new ApiError(503, "image_worker_unavailable"); },
  };
  const state = mount(api);
  await chooseAndStage([new File(["accepted"], "accepted.png")]);
  await screen.findByText("Staged · OCR not run");
  await waitFor(() => assert.equal(screen.getByLabelText("Extraction reference date").disabled, false));
  fireEvent.change(screen.getByLabelText("Extraction reference date"), { target: { value: "2026-10-14" } });
  fireEvent.click(screen.getByRole("button", { name: "Start selected images" }));
  await screen.findByText("Image job: pending");
  await waitFor(() => assert.equal(screen.getByRole("button", { name: "Read persisted image job status" }).disabled, false));
  fireEvent.click(screen.getByRole("button", { name: "Read persisted image job status" }));
  assert.match((await screen.findByRole("alert")).textContent, /image_worker_unavailable/);
  assert.ok(screen.getByText(`Job ${id}`));
  assert.equal(request.spec.reference_date, "2026-10-14");
  assert.equal(screen.getByRole("button", { name: "Clear image workflow" }).disabled, true);
  assert.equal(screen.getByLabelText("Extraction reference date").disabled, true);
  assert.equal(screen.getByLabelText("Include accepted.png").disabled, true);
  assert.equal(state.locks.at(-1), true); assert.equal(state.settled.length, 0);
});

test("failed staging retains successes and unattempted files; identical retry is not a dropped cohort", async () => {
  // what_bug_this_catches: skipping a failed upload and starting only the successful subset without operator selection.
  const calls = []; let refuse = true;
  const api = { async stageImage(_batch, sha, bytes) {
    calls.push(sha); if (calls.length === 2 && refuse) { refuse = false; throw new Error("authored refusal"); }
    return staged(sha, bytes.size);
  }, async items() { return []; }, async startImageJob() { assert.fail("no extraction permitted"); }, async imageJob() { assert.fail(); } };
  mount(api);
  await chooseAndStage([new File(["one"], "one.png"), new File(["two"], "two.png"), new File(["three"], "three.png")]);
  await screen.findByRole("alert");
  assert.equal(calls.length, 2);
  assert.equal(screen.getByRole("button", { name: "Start selected images" }).disabled, true);
  fireEvent.click(screen.getByRole("button", { name: "Stage remaining images" }));
  await waitFor(() => assert.equal(calls.length, 4));
  assert.equal(calls[1], calls[2], "failed exact image is retried before the unattempted third image");
  await waitFor(() => assert.equal(screen.getAllByText("Staged · OCR not run").length, 3));
});

test("unavailable worker and invalid selection cannot turn staging into OCR success", async () => {
  // what_bug_this_catches: hard-coded capabilities could enable extraction or silently truncate101files.
  let calls = 0;
  const api = { async stageImage(_batch, sha, bytes) { calls++; return staged(sha, bytes.size); },
    async items() { return []; }, async startImageJob() { assert.fail("worker unavailable"); }, async imageJob() { assert.fail(); } };
  mount(api, { workerAvailable: false });
  const file = new File(["authored"], "receipt.png");
  fireEvent.change(screen.getByLabelText("Receipt image files"), { target: { files: Array(101).fill(file) } });
  assert.match((await screen.findByRole("alert")).textContent, /1–100/); assert.equal(calls, 0);
  await chooseAndStage([file]);
  await screen.findByText("Staged · OCR not run");
  assert.equal(calls, 1);
  fireEvent.change(screen.getByLabelText("Extraction reference date"), { target: { value: "2026-10-14" } });
  assert.equal(screen.getByRole("button", { name: "Start selected images" }).disabled, true);
});

test("automatic status polling survives its own busy transition and stops at a persisted terminal result", async () => {
  // what_bug_this_catches: an effect depending on busy can abort its own GET, leaving a durable job stuck as pending forever.
  let request, id, polls = 0;
  const api = { async stageImage(_batch, sha, bytes) { return staged(sha, bytes.size); },
    async items() { return []; },
    async startImageJob(_batch, value) {
      request = value; id = await imageDigest(new TextEncoder().encode(value.request_id).buffer);
      return pendingJob(value, id);
    },
    async imageJob(_batch, identity, signal) {
      assert.equal(identity, id); polls++;
      await new Promise(resolve => setTimeout(resolve, 20));
      assert.equal(signal?.aborted, false, "status request must not cancel itself when busy becomes true");
      const next = pendingJob(request, id);
      if (polls === 2) {
        next.state = "complete"; next.execution_origin = "local_image_pipeline"; next.model_cost_status = "not_applicable";
        for (const key of Object.keys(next.items)) next.items[key] = {
          schema_version: 1, status: "ok", result_revision: "e".repeat(64), reason: null,
        };
      }
      return next;
    },
  };
  const state = mount(api);
  await chooseAndStage([new File(["poll"], "poll.png")]);
  await screen.findByText("Staged · OCR not run");
  await waitFor(() => assert.equal(screen.getByLabelText("Extraction reference date").disabled, false));
  fireEvent.change(screen.getByLabelText("Extraction reference date"), { target: { value: "2026-10-14" } });
  fireEvent.click(screen.getByRole("button", { name: "Start selected images" }));
  await screen.findByText("Image job: complete", {}, { timeout: 7000 });
  assert.equal(polls, 2); await waitFor(() => assert.equal(state.settled.length, 1));
});

test("unmount does not dispatch the remaining selected uploads", async () => {
  // what_bug_this_catches: leaving a component while its first request waits must not submit the rest of a cohort afterward.
  let release, calls = 0;
  const gate = new Promise(resolve => { release = resolve; });
  const api = { async stageImage(_batch, sha, bytes) {
    calls++; await gate; return staged(sha, bytes.size);
  }, async items() { return []; }, async startImageJob() { assert.fail(); }, async imageJob() { assert.fail(); } };
  const mounted = render(React.createElement(ImageImport, { api, batch, uploadAvailable: true,
    workerAvailable: true, disabled: false, lock() {}, settled: async () => {} }));
  await chooseAndStage([new File(["one"], "one.png"), new File(["two"], "two.png")]);
  await waitFor(() => assert.equal(calls, 1)); mounted.unmount();
  await React.act(async () => { release(); await gate; });
  assert.equal(calls, 1);
});
