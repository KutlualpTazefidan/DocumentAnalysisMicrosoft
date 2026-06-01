import { useEffect, useRef } from "react";

/**
 * Read-only HTML preview pane.
 *
 * Mounts the full ``html.html`` document inside a sandboxed iframe (CSS
 * isolation) and dispatches ``onClickElement(boxId)`` whenever the user
 * clicks an element with a ``data-source-box`` attribute.
 *
 * Used by the Synthesise tab to give the admin a clickable read-only
 * view of the extracted document — clicks select an element so the
 * sidebar can scope its question generation / display to that box.
 *
 * Intentionally distinct from ``HtmlEditor``: no edit modes, no save
 * plumbing, no in-place editing. Keeps the Synthesise PR orthogonal to
 * the in-place editor PR.
 */
interface Props {
  html: string;
  onClickElement: (boxId: string) => void;
  /** Currently-highlighted box; receives a dashed outline. */
  highlightedBoxId?: string | null;
}

const PREVIEW_CSS = `
[data-source-box]{outline:1px dashed transparent;transition:outline-color 0.15s ease}
[data-source-box]:hover{outline-color:#93c5fd;cursor:pointer}
[data-source-box].is-highlighted{outline-color:#2563eb;outline-style:solid;outline-width:2px;background-color:#eff6ff}
`;

export function HtmlPreview({
  html,
  onClickElement,
  highlightedBoxId,
}: Props): JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  function handleLoad() {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    // Inject the highlight CSS — same iframe is reused on srcDoc updates.
    const styleId = "__preview_extra_css__";
    let style = doc.getElementById(styleId) as HTMLStyleElement | null;
    if (!style) {
      style = doc.createElement("style");
      style.id = styleId;
      doc.head.appendChild(style);
    }
    style.textContent = PREVIEW_CSS;
    doc.addEventListener("click", (evt) => {
      const t = evt.target as HTMLElement;
      const el = t.closest("[data-source-box]") as HTMLElement | null;
      if (el) onClickElement(el.getAttribute("data-source-box")!);
    });
    if (highlightedBoxId) applyHighlight(doc, highlightedBoxId);
  }

  // Re-apply highlight when prop changes without re-mounting the iframe.
  useEffect(() => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc) return;
    applyHighlight(doc, highlightedBoxId ?? null);
  }, [highlightedBoxId]);

  return (
    <iframe
      ref={iframeRef}
      data-testid="synth-html-preview"
      sandbox="allow-same-origin"
      srcDoc={html}
      className="w-full h-full border-none"
      title="HTML preview (read-only)"
      onLoad={handleLoad}
    />
  );
}

function applyHighlight(doc: Document, boxId: string | null) {
  doc.querySelectorAll(".is-highlighted").forEach((el) => el.classList.remove("is-highlighted"));
  if (!boxId) return;
  const el = doc.querySelector(`[data-source-box="${cssEscape(boxId)}"]`);
  el?.classList.add("is-highlighted");
}

function cssEscape(s: string): string {
  return s.replace(/"/g, '\\"');
}
