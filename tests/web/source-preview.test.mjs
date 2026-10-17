/** Actual React component + authored synthetic DOM/transport; no native browser/OCR claim. */
import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {url:"http://127.0.0.1:20601"});
for(const name of ["window","document","navigator","HTMLElement","Node","MutationObserver"])
  Object.defineProperty(globalThis,name,{configurable:true,value:name==="window"?dom.window:dom.window[name]});
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const React = await import("react");
const {render,fireEvent,screen,cleanup} = await import("@testing-library/react");
const {SourcePreview} = await import("../../web/source-preview.tsx");
const created=[],revoked=[];
const originalCreate=URL.createObjectURL, originalRevoke=URL.revokeObjectURL;
URL.createObjectURL=blob=>{ const url=`blob:authored-${created.length}`; created.push({url,blob});return url; };
URL.revokeObjectURL=url=>revoked.push(url);
test.after(()=>{URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;dom.window.close();});
test.afterEach(()=>{cleanup();created.length=0;revoked.length=0;});

const page={page_id:"source-page",page_index:0,width_px:200,height_px:300,page_sha256:"b".repeat(64),
  grid_policy_id:"rgba8-source-grid-v1",lines:[{stable_id:"line",text:"AUTHORED RECEIPT",bbox_px:{x0:10,y0:20,x1:100,y1:40}}]};
const detail={image_available:true,review:{item_id:"item-one",revision:"a".repeat(64),document:{source_kind:"image",pages:[page]}}};
const field={machine:{source:{kind:"document",evidence:{...page,bbox_px:{x0:10,y0:20,x1:100,y1:40},evidence_artifact_sha256:"c".repeat(64)}}}};
const props=(api,changes={})=>({api,batch:"batch-one",detail,field,...changes});
const mount=(api,changes)=>render(React.createElement(SourcePreview,props(api,changes)));
async function flush(action=()=>{}){await React.act(async()=>{action();await new Promise(resolve=>setImmediate(resolve));});}
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
const blob=()=>new Blob(["authored pixels returned by the test transport"],{type:"image/png"});

test("available normalized image loads on exact page grid, selected box changes without refetch and URL is released",async()=>{
  // what_bug_this_catches: text-only preview despite API pixels, or image and box in different grids.
  const calls=[];const api={async image(...args){calls.push(args);return blob();}};
  const view=mount(api);await flush();
  assert.equal(calls.length,1);assert.equal(calls[0][0],"batch-one");assert.equal(calls[0][1],"item-one");
  assert.equal(calls[0][2],detail.review.revision);assert.equal(calls[0][3].page_sha256,page.page_sha256);
  assert.equal(screen.getByText("Loading image").textContent,"Loading image");
  const image=view.container.querySelector("image");assert.equal(image.getAttribute("href"),created[0].url);
  fireEvent.load(image);
  assert.ok(screen.getByRole("img",{name:"Normalized receipt image with selected field region"}));
  assert.equal(view.container.querySelector("svg").getAttribute("viewBox"),"0 0 200 300");
  assert.equal(view.container.querySelector(".source-region").getAttribute("width"),"90");
  assert.equal(view.container.querySelector("text"),null);
  const other={machine:{source:{...field.machine.source,evidence:{...field.machine.source.evidence,bbox_px:{x0:30,y0:50,x1:80,y1:70}}}}};
  view.rerender(React.createElement(SourcePreview,props(api,{field:other})));await flush();
  assert.equal(calls.length,1);assert.equal(view.container.querySelector(".source-region").getAttribute("x"),"30");
  view.unmount();assert.deepEqual(revoked,[created[0].url]);assert.equal(calls[0][4].aborted,true);
});

test("unavailable and unsupported grids keep useful text without any image request",async()=>{
  let calls=0;const api={async image(){calls++;return blob();}};
  for(const change of [
    {image_available:false},
    {review:{...detail.review,document:{...detail.review.document,source_kind:"pdf"}}},
    {review:{...detail.review,document:{...detail.review.document,pages:[{...page,grid_policy_id:"other"}]}}},
  ]){
    const view=mount(api,{detail:{...detail,...change}});await flush();
    assert.ok(screen.getByText("Image unavailable"));assert.ok(screen.getByText("AUTHORED RECEIPT"));
    assert.equal(view.container.querySelector("image"),null);view.unmount();
  }
  assert.equal(calls,0);assert.equal(created.length,0);
});

test("failed fetch and image decode preserve text and refuse image display",async()=>{
  const view=mount({async image(){throw new Error("private diagnostic must not be shown");}});await flush();
  assert.ok(screen.getByText("Image could not be loaded"));assert.ok(screen.getByText("AUTHORED RECEIPT"));
  assert.doesNotMatch(view.container.textContent,/private diagnostic/);assert.equal(created.length,0);view.unmount();
  const decoded=mount({async image(){return blob();}});await flush();
  fireEvent.error(decoded.container.querySelector("image"));
  assert.ok(screen.getByText("Image could not be loaded"));assert.equal(decoded.container.querySelector("image"),null);
  assert.ok(screen.getByText("AUTHORED RECEIPT"));decoded.unmount();assert.deepEqual(revoked,[created[0].url]);
});

for(const transition of ["item","revision","grid","unavailable"]) test(`late source response after ${transition} change cannot display previous pixels`,async()=>{
  // what_bug_this_catches: a slower previous request could overwrite current receipt/revision pixels.
  const first=deferred(),second=deferred(),signals=[];
  const api={image(...args){signals.push(args[4]);return signals.length===1?first.promise:second.promise;}};
  const view=mount(api);await flush();
  const next={...detail,review:{...detail.review,document:{...detail.review.document,pages:[{...page}]}}};
  if(transition==="item") next.review.item_id="item-two";
  if(transition==="revision") next.review.revision="d".repeat(64);
  if(transition==="grid") next.review.document.pages[0].page_sha256="d".repeat(64);
  if(transition==="unavailable") next.image_available=false;
  view.rerender(React.createElement(SourcePreview,props(api,{detail:next})));await flush();assert.equal(signals[0].aborted,true);
  await flush(()=>first.resolve(blob()));assert.equal(created.length,0);assert.equal(view.container.querySelector("image"),null);
  if(transition!=="unavailable"){
    await flush(()=>second.resolve(blob()));assert.equal(created.length,1);
    fireEvent.load(view.container.querySelector("image"));assert.ok(screen.getByText("Normalized image"));
  }
});

test("already displayed pixels disappear on changed revision; old load events cannot qualify new pixels",async()=>{
  const pending=deferred();let calls=0;
  const api={image(){return ++calls===1?Promise.resolve(blob()):pending.promise;}};
  const view=mount(api);await flush();const oldImage=view.container.querySelector("image");fireEvent.load(oldImage);
  const next={...detail,review:{...detail.review,revision:"d".repeat(64)}};
  view.rerender(React.createElement(SourcePreview,props(api,{detail:next})));await flush();
  assert.equal(view.container.querySelector("image"),null);assert.deepEqual(revoked,[created[0].url]);
  fireEvent.load(oldImage);assert.ok(screen.getByText("Loading image"));
  await flush(()=>pending.resolve(blob()));assert.equal(created.length,2);
});

test("mismatched evidence grid never draws the selected box over source pixels",async()=>{
  const mismatched={machine:{source:{...field.machine.source,evidence:{...field.machine.source.evidence,page_sha256:"d".repeat(64)}}}};
  const view=mount({async image(){return blob();}},{field:mismatched});await flush();fireEvent.load(view.container.querySelector("image"));
  assert.equal(view.container.querySelector(".source-region"),null);assert.ok(screen.getByText("Normalized image"));
});

test("unmount before ignored transport cancellation creates no URL or late update",async()=>{
  const pending=deferred();const view=mount({image(){return pending.promise;}});await flush();view.unmount();
  await flush(()=>pending.resolve(blob()));assert.equal(created.length,0);assert.equal(revoked.length,0);
});

test("explicit image retry recovers a transient failure without changing review data",async()=>{
  let calls=0;const api={async image(){if(++calls===1)throw new Error("transient authored fault");return blob();}};
  const before=JSON.stringify(detail);const view=mount(api);await flush();
  fireEvent.click(screen.getByRole("button",{name:"Retry image"}));await flush();
  assert.equal(calls,2);fireEvent.load(view.container.querySelector("image"));
  assert.ok(screen.getByText("Normalized image"));assert.equal(JSON.stringify(detail),before);
});

test("replacing the capability client hides old pixels and aborts its request",async()=>{
  const requests=[];const first={async image(...args){requests.push(args);return blob();}};
  const pending=deferred();const second={image(){return pending.promise;}};
  const view=mount(first);await flush();fireEvent.load(view.container.querySelector("image"));
  view.rerender(React.createElement(SourcePreview,props(second)));await flush();
  assert.equal(view.container.querySelector("image"),null);assert.equal(requests[0][4].aborted,true);
  assert.deepEqual(revoked,[created[0].url]);await flush(()=>pending.resolve(blob()));
  assert.equal(created.length,2);
});
