import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { ApiError, HttpReviewApi, describeError } from "../../web/http.ts";

const origin = "http://127.0.0.1:20601";
const token = "synthetic-browser-capability-00000000";

test("actual client keeps capability out of URLs and uses same-origin private requests", async () => {
  const seen = [];
  const api = new HttpReviewApi(token, origin, async function (url, init) {
    assert.equal(this, globalThis, "browser WebIDL fetch must receive Window/globalThis");
    seen.push({ url, init });
    return new Response(JSON.stringify({ contract: "receipt-api/1" }), { headers: { "Content-Type": "application/json" } });
  });
  assert.equal((await api.status()).contract, "receipt-api/1");
  await api.createBatch("USD");
  assert.equal(seen[0].url, origin + "/api/status");
  assert.equal(seen[0].init.headers["X-RFR-Token"], token);
  for (const {url, init} of seen) {
    assert.ok(!url.includes(token));
    assert.equal(init.credentials, "omit"); assert.equal(init.redirect, "error");
    assert.equal(init.mode, "same-origin"); assert.equal(init.cache, "no-store");
    assert.ok(init.signal instanceof AbortSignal);
  }
  assert.deepEqual(JSON.parse(seen[1].init.body), {currency: {code: "USD"}});
});

test("exact saved draft retry sends identical bytes and correctly binds route item", async () => {
  const seen = [];
  const api = new HttpReviewApi(token, origin, async (url, init) => {
    seen.push({url, body: init.body});
    return new Response('{"outcome":"exact_retry"}');
  });
  const saved = {expected_item_revision: "a".repeat(64), intent: {event_id:"saved-event", value:"Corrected"}};
  await api.apply("batch-id", "item/with space", saved);
  await api.apply("batch-id", "item/with space", saved);
  assert.equal(seen[0].url, origin + "/api/batches/batch-id/items/item%2Fwith%20space/decisions");
  assert.equal(seen[0].body, seen[1].body);
});

test("server conflicts are typed; unsafe body diagnostics never become display errors", async () => {
  const refusal = new HttpReviewApi(token, origin, async () => new Response('{"error":"revision_conflict"}', {status:409}));
  await assert.rejects(refusal.items("batch"), e => e instanceof ApiError && e.status === 409 && e.message === "revision_conflict");
  const privateError = new HttpReviewApi(token, origin, async () => new Response('{"error":"private payload <script>"}', {status:500}));
  await assert.rejects(privateError.status(), e => e.message === "request_refused");
});

test("client refuses foreign origins, credentials and malformed capabilities", () => {
  for (const host of ["https://127.0.0.1", "http://foreign.test", origin + "/extra", "http://user:pass@127.0.0.1:20601"])
    assert.throws(() => new HttpReviewApi(token, host));
  assert.throws(() => new HttpReviewApi("short", origin));
  assert.throws(() => new HttpReviewApi("x".repeat(32) + "\n", origin));
});

test("viewer source has no persistent receipt/capability storage or HTML evaluation path", () => {
  for (const name of ["main.tsx", "http.ts", "source-preview.tsx"]) {
    const source = readFileSync(new URL("../../web/" + name, import.meta.url), "utf8");
    assert.doesNotMatch(source, /localStorage|sessionStorage|document\.cookie|dangerouslySetInnerHTML|\.innerHTML\s*=|\beval\s*\(|new Function/);
  }
});

// Authored one-pixel PNG transport control; no image/OCR accuracy assertion.
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4lwAAAAASUVORK5CYII=", "base64");
const revision = "a".repeat(64), grid = "b".repeat(64);
const page = { page_sha256:grid, width_px:1, height_px:1 };
const imageHeaders = {"Content-Type":"image/png", "X-RFR-Item-Revision":revision, "X-RFR-Page-SHA256":grid};

test("source pixels require exact revision/grid headers and private token fetch; cancellation reaches fetch", async () => {
  // what_bug_this_catches: a direct img URL would omit capability or put it in the URL;
  // an unbound image response could show pixels from a different receipt revision.
  const controller = new AbortController(); let request;
  const api = new HttpReviewApi(token, origin, async (url, init) => {
    request={url,init}; return new Response(png, {headers:imageHeaders});
  });
  assert.deepEqual(new Uint8Array(await (await api.image("batch", "item/one", revision, page, controller.signal)).arrayBuffer()), new Uint8Array(png));
  assert.equal(request.url, origin+"/api/batches/batch/items/item%2Fone/page?revision="+revision);
  assert.equal(request.init.headers["X-RFR-Token"], token); assert.ok(!request.url.includes(token));
  for (const [key,value] of Object.entries({credentials:"omit",cache:"no-store",redirect:"error",mode:"same-origin"}))
    assert.equal(request.init[key], value);
  controller.abort(); assert.equal(request.init.signal.aborted, true);
});

for (const [name, headers, body] of [
  ["wrong MIME", {...imageHeaders,"Content-Type":"image/svg+xml"}, png],
  ["missing grid", {"Content-Type":"image/png","X-RFR-Item-Revision":revision}, png],
  ["wrong grid", {...imageHeaders,"X-RFR-Page-SHA256":"c".repeat(64)}, png],
  ["wrong revision", {...imageHeaders,"X-RFR-Item-Revision":"c".repeat(64)}, png],
  ["not PNG", imageHeaders, Buffer.alloc(40)],
  ["truncated PNG", imageHeaders, png.subarray(0,24)],
]) test(`source image refuses ${name} before display`, async () => {
  const api = new HttpReviewApi(token, origin, async () => new Response(body,{headers}));
  await assert.rejects(api.image("batch","item",revision,page), /source_image_identity_refused/);
});

test("source image refuses grid dimensions and malformed request identity", async () => {
  // what_bug_this_catches: stretching another-size image would misalign the source overlay.
  let calls=0;
  const api = new HttpReviewApi(token,origin,async()=>{calls++;return new Response(png,{headers:imageHeaders});});
  await assert.rejects(api.image("batch","item",revision,{...page,width_px:2}), /identity_refused/);
  assert.equal(calls,1);
  for(const [rev,dimensions] of [["bad",page],[revision,{...page,width_px:0}],[revision,{...page,width_px:25_000_001}]])
    await assert.rejects(api.image("batch","item",rev,dimensions), /identity_refused/);
  assert.equal(calls,1,"invalid requests must not reach private source endpoint");
});

test("source image stale/refused HTTP response retains typed error", async () => {
  const api = new HttpReviewApi(token,origin,async()=>new Response('{"error":"item_revision_conflict"}',{status:409}));
  await assert.rejects(api.image("batch","item",revision,page), e=>e instanceof ApiError && e.status===409);
});

test("empty-clean refusal is distinct from stale-edit conflict and malformed input", () => {
  assert.match(describeError(new ApiError(409, "clean_export_empty")), /No resolved receipts/);
  assert.doesNotMatch(describeError(new ApiError(409, "clean_export_empty")), /State may have changed/);
  assert.match(describeError(new ApiError(409, "revision_conflict")), /your text is retained/);
  assert.match(describeError(new SyntaxError("private sentinel")), /not valid JSON/);
  assert.doesNotMatch(describeError(new SyntaxError("private sentinel")), /sentinel/);
});
