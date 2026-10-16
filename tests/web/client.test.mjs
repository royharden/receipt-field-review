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
  for (const name of ["main.tsx", "http.ts"]) {
    const source = readFileSync(new URL("../../web/" + name, import.meta.url), "utf8");
    assert.doesNotMatch(source, /localStorage|sessionStorage|document\.cookie|dangerouslySetInnerHTML|\.innerHTML\s*=|\beval\s*\(|new Function/);
  }
});

test("empty-clean refusal is distinct from stale-edit conflict and malformed input", () => {
  assert.match(describeError(new ApiError(409, "clean_export_empty")), /No resolved receipts/);
  assert.doesNotMatch(describeError(new ApiError(409, "clean_export_empty")), /State may have changed/);
  assert.match(describeError(new ApiError(409, "revision_conflict")), /your text is retained/);
  assert.match(describeError(new SyntaxError("private sentinel")), /not valid JSON/);
  assert.doesNotMatch(describeError(new SyntaxError("private sentinel")), /sentinel/);
});
