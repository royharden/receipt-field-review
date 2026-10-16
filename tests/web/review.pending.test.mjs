/** Real React + synthetic DOM + real canonical files. ACK fault is explicit test transport only. */
import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createInterface } from "node:readline";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://127.0.0.1:24002", pretendToBeVisual: true,
});
for (const name of ["window", "document", "navigator", "HTMLElement", "Node", "MutationObserver"])
  Object.defineProperty(globalThis, name, { configurable: true, value: name === "window" ? dom.window : dom.window[name] });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = await import("react");
const { render, fireEvent, screen, cleanup } = await import("@testing-library/react");
const { Review } = await import("../../web/main.tsx");
const { ApiError } = await import("../../web/http.ts");
const root = fileURLToPath(new URL("../../", import.meta.url));
const python = process.env.RFR_TEST_PYTHON ?? path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const caseParent = process.env.RFR_REVIEW_TEST_TMP ?? tmpdir();

async function canonical() {
  await mkdir(caseParent, {recursive:true});
  const folder = await mkdtemp(path.join(caseParent, "rfr-react-"));
  const child = spawn(python, [path.join(root, "tests/web/canonical_bridge.py"), folder], {
    cwd: root, stdio: ["pipe", "pipe", "pipe"], windowsHide: true,
    env: {...process.env, PYTHONDONTWRITEBYTECODE:"1"},
  });
  let nextId = 0, stderr = "";
  const waiting = new Map();
  const exited = new Promise(resolve => child.once("exit", (code, signal) => {
    for (const pending of waiting.values()) pending.reject(new Error(`canonical bridge exited ${code}: ${stderr.slice(-1000)}`));
    waiting.clear(); resolve({code, signal});
  }));
  child.stderr.on("data", data => { stderr = (stderr + data).slice(-64 * 1024); });
  child.on("error", error => { for (const p of waiting.values()) p.reject(error); waiting.clear(); });
  const reader = createInterface({input: child.stdout});
  reader.on("line", line => {
    const message = JSON.parse(line), pending = waiting.get(message.id);
    assert.ok(pending, "response must bind an outstanding test-port request");
    waiting.delete(message.id);
    if (message.ok) pending.resolve(message.value);
    else pending.reject(new ApiError(message.status, message.error));
  });
  const call = (operation, input) => new Promise((resolve, reject) => {
    const id = ++nextId; waiting.set(id, {resolve, reject});
    child.stdin.write(JSON.stringify({id, operation, input}) + "\n");
  });
  const initial = await call("init");
  return { ...initial, folder, call,
    async close() {
      child.stdin.end();
      const timer = setTimeout(() => child.kill(), 5000);
      const terminal = await exited; clearTimeout(timer); reader.close();
      await writeFile(path.join(folder, "bridge-terminal.json"), JSON.stringify({ ...terminal, stderr, transport:"stdio canonical services; no HTTP/native browser" }));
      assert.equal(terminal.code, 0, stderr);
    },
  };
}

function port(backend, {loseAck = false, gate = null} = {}) {
  const calls = {draft:0, apply:0, bodies:[], receipts:[], ackFaults:0, draftErrors:0, itemsFinished:0};
  let mustLose = loseAck;
  return {calls, api: {
    async draft(_batch, _item, input) {
      calls.draft++;
      try { return await backend.call("draft", input); }
      catch (error) { calls.draftErrors++; throw error; }
    },
    async apply(_batch, _item, draft) {
      calls.apply++; calls.bodies.push(JSON.stringify(draft));
      if (gate) await gate;
      const receipt = await backend.call("apply", draft); calls.receipts.push(receipt);
      if (mustLose) {
        mustLose = false; calls.ackFaults++;
        throw new Error("test-only acknowledgement withheld AFTER actual canonical commit");
      }
      return receipt;
    },
    async item() {
      const value = await backend.call("item"); calls.itemsFinished++; return value;
    },
  }};
}

function mount(backend, api, seed = backend.detail) {
  let locked = false;
  function Host() {
    const [detail, setDetail] = React.useState(seed);
    const [, setLocked] = React.useState(false);
    const lock = React.useCallback(value => { locked = value; setLocked(value); }, []);
    return React.createElement(Review, {api, batch:backend.batch, detail,
      changed:async next => setDetail(next), lock});
  }
  const mounted = render(React.createElement(Host));
  return { ...mounted, locked: () => locked };
}

function editMerchant(value = "React acknowledgement control") {
  fireEvent.click(screen.getByRole("button", {name:/merchant name/}));
  fireEvent.change(screen.getByLabelText("Corrected value"), {target:{value}});
  fireEvent.change(screen.getByLabelText("Decision reason"), {target:{value:"Authored React control; no native-browser or Human Gold claim"}});
}
function keyboardSave() { fireEvent.keyDown(window, {key:"Enter", ctrlKey:true}); }
async function settledEvent(trigger, completed) {
  // Wait on the explicit service boundary inside act, not a notice that precedes refresh.
  await React.act(async () => {
    trigger();
    const until = Date.now() + 10000;
    while (!completed()) {
      if (Date.now() >= until) throw new Error("explicit test-port completion deadline");
      await new Promise(resolve => setTimeout(resolve, 5));
    }
    await new Promise(resolve => setImmediate(resolve));
  });
}

for (const route of ["keyboard", "visible retry"]) test(`actual React ${route} retains exact intent after real commit and injected ACK loss`, {timeout:45000}, async () => {
  const backend = await canonical();
  let observedCalls = null;
  try {
    const {api, calls} = port(backend, {loseAck:true}); const view = mount(backend, api);
    observedCalls = calls;
    editMerchant(); await settledEvent(keyboardSave, () => calls.ackFaults === 1);
    const committed = await backend.call("audit"); assert.equal(committed.events, 1);
    assert.equal(calls.receipts[0].outcome, "appended"); assert.equal(calls.ackFaults, 1);
    assert.equal(screen.getByRole("button", {name:"Save decision"}).disabled, true);
    assert.equal(screen.getByRole("button", {name:"Discard unsaved edits"}).disabled, true);
    assert.equal(view.locked(), true);
    assert.equal(screen.getByRole("button", {name:"Retry saved decision"}).disabled, false);
    await settledEvent(() => {
      if (route === "keyboard") keyboardSave();
      else fireEvent.click(screen.getByRole("button", {name:"Retry saved decision"}));
    }, () => calls.itemsFinished === 1 || calls.draftErrors > 0);
    assert.equal(calls.draft, 1, "pending recovery must not construct a replacement intent");
    assert.equal(calls.draftErrors, 0);
    assert.match(screen.getByRole("status").textContent, /Already saved/);
    assert.equal(calls.apply, 2); assert.equal(calls.bodies[0], calls.bodies[1]);
    assert.equal(calls.receipts[1].outcome, "exact_retry");
    assert.equal(calls.receipts[0].event_id, calls.receipts[1].event_id);
    assert.deepEqual(await backend.call("audit"), committed, "retry cannot append or rewrite journal bytes");
    assert.equal((await backend.call("item")).review.fields.merchant_name.effective_value, "React acknowledgement control");
    assert.equal(screen.queryByRole("button", {name:"Retry saved decision"}), null);
    assert.equal(view.locked(), false);
    await writeFile(path.join(backend.folder, "react-result.json"), JSON.stringify({route,calls,committed,after:await backend.call("audit"),native_browser:"UNKNOWN; synthetic DOM events only"}));
  } catch (error) {
    await writeFile(path.join(backend.folder, "failure-observation.json"), JSON.stringify({
      route, error:error.message, calls:observedCalls, audit:await backend.call("audit"),
      visibleAlert:screen.queryByRole("alert")?.textContent ?? null,
      retryDisabled:screen.queryByRole("button",{name:"Retry saved decision"})?.disabled ?? null,
      evidence:"Actual React/synthetic DOM/canonical services; no native browser",
    }));
    throw error;
  } finally { cleanup(); await backend.close(); }
});

test("actual React busy routing ignores repeated keyboard events during the in-flight apply", {timeout:45000}, async () => {
  const backend = await canonical(); let release;
  const gate = new Promise(resolve => {release = resolve;});
  try {
    const {api,calls} = port(backend,{gate}); mount(backend,api); editMerchant();
    await settledEvent(keyboardSave, () => calls.apply === 1);
    keyboardSave(); keyboardSave(); assert.equal(calls.draft,1); assert.equal(calls.apply,1);
    assert.equal((await backend.call("audit")).events,0);
    await settledEvent(release, () => calls.itemsFinished === 1);
    assert.match(screen.getByRole("status").textContent, /Decision saved/);
    assert.equal((await backend.call("audit")).events,1);
  } finally { release(); cleanup(); await backend.close(); }
});

test("actual React genuine stale refusal preserves text and cannot overwrite the canonical peer", {timeout:45000}, async () => {
  const backend = await canonical();
  try {
    const {api,calls} = port(backend); mount(backend,api); editMerchant("Unsaved stale edit");
    const peer = await backend.call("draft", {field_id:"merchant_name",action:"correct",value:"Canonical peer",expected_item_revision:backend.detail.review.revision,expected_prior_event_id:null,actor:"synthetic-peer",reason:"Real canonical stale-head control"});
    await backend.call("apply",peer); const original = await backend.call("audit");
    await settledEvent(keyboardSave, () => calls.draftErrors === 1);
    assert.match(screen.getByRole("alert").textContent,/revision_conflict/);
    assert.equal(calls.apply,0); assert.deepEqual(await backend.call("audit"),original);
    assert.equal(screen.getByLabelText("Corrected value").value,"Unsaved stale edit");
    assert.equal(screen.getByRole("button",{name:"Save decision"}).disabled,true);
    await settledEvent(() => fireEvent.click(screen.getByRole("button",{name:"Reload state"})), () => calls.itemsFinished === 1);
    assert.equal(screen.queryByRole("alert"),null);
    assert.equal(screen.getByLabelText("Corrected value").value,"Unsaved stale edit");
    fireEvent.click(screen.getByRole("button",{name:"Discard unsaved edits"}));
    assert.equal(screen.getByLabelText("Corrected value").value,"Canonical peer");
    assert.deepEqual(await backend.call("audit"),original);
  } finally { cleanup(); await backend.close(); }
});

test("actual React unsaved cancel does not dispatch; forced remount after lost ACK replays real saved state", {timeout:45000}, async () => {
  const backend = await canonical();
  try {
    const {api,calls} = port(backend,{loseAck:true}); const mounted = mount(backend,api);
    keyboardSave(); assert.equal(calls.draft,0); assert.equal(calls.apply,0);
    editMerchant("Discard me"); fireEvent.click(screen.getByRole("button",{name:"Discard unsaved edits"}));
    assert.equal(calls.draft,0); assert.equal((await backend.call("audit")).events,0);
    editMerchant("Persisted across React remount");
    await settledEvent(keyboardSave, () => calls.ackFaults === 1);
    const audit = await backend.call("audit"); mounted.unmount();
    const replay = await backend.call("item"); mount(backend,api,replay);
    fireEvent.click(screen.getByRole("button",{name:/merchant name/}));
    assert.equal(screen.getByLabelText("Corrected value").value,"Persisted across React remount");
    assert.deepEqual(await backend.call("audit"),audit); assert.equal(audit.events,1);
  } finally { cleanup(); await backend.close(); }
});
