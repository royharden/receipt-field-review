import { useEffect, useState } from "react";
import type { ItemDetail, ReviewField } from "./contracts";
import type { HttpReviewApi } from "./http";

type ImageApi = Pick<HttpReviewApi, "image">;
type Preview = { api: ImageApi; key: string; url: string | null; state: "loading" | "ready" | "error" };

export function SourcePreview({ api, batch, detail, field }: {
  api: Pick<HttpReviewApi, "image">; batch: string; detail: ItemDetail; field: ReviewField | undefined;
}) {
  const view = detail.review;
  const source = field?.machine.source;
  const evidence = source?.kind === "document" ? source.evidence : null;
  const page = view.document.pages.find(p => p.page_id === evidence?.page_id) ?? view.document.pages[0];
  const box = evidence && page && evidence.page_id === page.page_id &&
    evidence.page_sha256 === page.page_sha256 && evidence.grid_policy_id === page.grid_policy_id &&
    evidence.width_px === page.width_px && evidence.height_px === page.height_px ? evidence.bbox_px : null;
  const available = detail.image_available && view.document.source_kind === "image" &&
    view.document.pages.length === 1 && page?.page_index === 0 && page.grid_policy_id === "rgba8-source-grid-v1";
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify([batch, view.item_id, view.revision, page?.page_id,
    page?.page_sha256, page?.width_px, page?.height_px, available, attempt]);
  const [preview, setPreview] = useState<Preview | null>(null);
  // A changed item/revision hides old pixels in this render, before the effect cleanup runs.
  const current = preview?.key === key && preview.api === api && available ? preview : null;
  const loaded = current?.state === "ready";

  useEffect(() => {
    if (!available || !page) { setPreview(null); return; }
    const controller = new AbortController();
    let active = true;
    let objectUrl: string | null = null;
    setPreview({ api, key, url: null, state: "loading" });
    void api.image(batch, view.item_id, view.revision, page, controller.signal).then(blob => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setPreview({ api, key, url: objectUrl, state: "loading" });
    }).catch(() => {
      if (active) setPreview({ api, key, url: null, state: "error" });
    });
    return () => {
      active = false; controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  // The key contains every page identity/dimension input. Field selection changes only the box.
  }, [api, key]);

  return <section className="source-pane" aria-label="Recognized source preview">
    <div className="section-title"><h2>Receipt source</h2><span className="tag">
      {loaded ? "Normalized image" : current?.state === "error" ? "Image could not be loaded" :
        available ? "Loading image" : "Image unavailable"}</span></div>
    <p className="muted" aria-live="polite">{loaded ?
      "Normalized source pixels. The selected region uses the same pixel grid; recognition and field values still require review." :
      "Recognized text and supplied geometry remain available. This preview does not establish measured OCR or receipt accuracy."}</p>
    {current?.state === "error" && <button onClick={() => setAttempt(value => value + 1)}>Retry image</button>}
    {page ? <svg role="img" aria-label={loaded ? "Normalized receipt image with selected field region" :
      "Recognized text with selected field region"} viewBox={`0 0 ${page.width_px} ${page.height_px}`} className="page-preview">
      <rect width={page.width_px} height={page.height_px} className="paper" />
      {current?.url && current.state !== "error" && <image href={current.url} width={page.width_px} height={page.height_px}
        visibility={loaded ? "visible" : "hidden"} onLoad={() => setPreview(old => old?.key === key && old.url === current.url ?
          { ...old, state: "ready" } : old)} onError={() => setPreview(old => old?.key === key && old.url === current.url ?
          { ...old, state: "error" } : old)} />}
      {!loaded && page.lines.map(line => line.bbox_px && <text key={line.stable_id}
        x={line.bbox_px.x0} y={line.bbox_px.y1}
        fontSize={Math.max(6, Math.min(40, line.bbox_px.y1 - line.bbox_px.y0))}>{line.text}</text>)}
      {box && <rect x={box.x0} y={box.y0} width={box.x1 - box.x0} height={box.y1 - box.y0} className="source-region" />}
    </svg> : <p>No recognized page available.</p>}
    <details><summary>Source references</summary><p className="mono">{evidence?.page_id ?? "No anchored evidence"}</p>
      <p className="mono">{evidence?.evidence_artifact_sha256 ?? "No artifact reference"}</p></details>
  </section>;
}
