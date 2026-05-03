import { useEffect, useRef } from "react";
import { T } from "../styles/typography";

/**
 * In-place HTML editor.
 *
 * The rendered html.html mounts inside a Shadow DOM (CSS isolation, no JS
 * sandbox needed because the html.html is generated server-side). Clicking
 * on any element with `data-source-box`:
 *   - first click  → highlight (sidebar selects the box)
 *   - second click on the SAME box within ~800 ms → enter edit mode
 *     (contenteditable=true on that element)
 *   - blur         → save via `onElementChange(boxId, outerHTML)`
 *   - Esc          → cancel and restore from prop
 *
 * Math editing flows through to `<math>`/`<mi>` descendants via DOM
 * contenteditable. For LaTeX-friendly editing, users can type `$..$` /
 * `$$..$$` / bare `\command{...}` — the backend re-runs
 * `_convert_inline_latex` on save so the rendered form gets re-converted.
 *
 * The Quelltext panel in the sidebar keeps showing the raw `html_snippet_raw`
 * for read-only inspection.
 */

const EDITOR_CSS = `
[data-source-box]{outline:1px dashed transparent;transition:outline-color 0.15s ease}
[data-source-box]:hover{outline-color:#93c5fd;cursor:text}
[data-source-box].is-highlighted{outline-color:#2563eb;outline-style:dashed}
[data-source-box][contenteditable="true"]{outline-color:#2563eb;outline-style:solid;outline-offset:2px;background-color:#eff6ff}
`;

const SECOND_CLICK_WINDOW_MS = 800;

interface Props {
  html: string;
  onClickElement: (boxId: string) => void;
  onElementChange: (boxId: string, newOuterHtml: string) => void;
  /** box_id currently highlighted by the sidebar — applies the dashed
   *  outline. */
  highlightedBoxId?: string | null;
  /** Optional small status text shown next to the title (e.g. "Speichert…"). */
  status?: string;
}

interface PendingClick {
  boxId: string;
  ts: number;
}

export function HtmlEditor({
  html,
  onClickElement,
  onElementChange,
  highlightedBoxId,
  status,
}: Props): JSX.Element {
  const hostRef = useRef<HTMLDivElement>(null);
  const lastClickRef = useRef<PendingClick | null>(null);
  // Snapshot of the box's outerHTML at edit-mode entry, used to restore on Esc.
  const editingBoxRef = useRef<{ box: HTMLElement; original: string } | null>(null);

  // Mount / re-render whenever html changes.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let root = host.shadowRoot;
    if (!root) root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${EDITOR_CSS}</style>${html}`;
    // Re-apply highlight if any (re-render wiped the class).
    if (highlightedBoxId) {
      const el = root.querySelector(
        `[data-source-box="${cssEscape(highlightedBoxId)}"]`,
      );
      el?.classList.add("is-highlighted");
    }
  }, [html, highlightedBoxId]);

  // Wire event listeners on the shadow root once.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const root = host.shadowRoot;
    if (!root) return;

    function findBox(t: EventTarget | null): HTMLElement | null {
      const el = t as HTMLElement | null;
      return el?.closest?.("[data-source-box]") as HTMLElement | null;
    }

    function handleClick(evt: Event) {
      const box = findBox(evt.target);
      if (!box) return;
      const boxId = box.getAttribute("data-source-box")!;
      // If this box is already in edit mode, let the click reposition the
      // cursor — don't reset state.
      if (box.contentEditable === "true") return;

      const now = Date.now();
      const prev = lastClickRef.current;
      const isSecondClick =
        prev && prev.boxId === boxId && now - prev.ts < SECOND_CLICK_WINDOW_MS;

      if (isSecondClick) {
        // Enter edit mode.
        editingBoxRef.current = { box, original: box.outerHTML };
        box.contentEditable = "true";
        box.focus();
        // Browser places the caret near the click point by default.
        lastClickRef.current = null;
      } else {
        // First click → highlight only.
        onClickElement(boxId);
        lastClickRef.current = { boxId, ts: now };
      }
    }

    function handleFocusOut(evt: FocusEvent) {
      const editing = editingBoxRef.current;
      if (!editing) return;
      const box = findBox(evt.target);
      if (!box || box !== editing.box) return;
      // Leave edit mode and save (unless the same focusout was triggered by
      // an Esc cancel that already cleared editingBoxRef).
      const boxId = box.getAttribute("data-source-box")!;
      box.contentEditable = "false";
      const newOuter = box.outerHTML;
      editingBoxRef.current = null;
      // Skip save if user typed nothing.
      if (newOuter !== editing.original) {
        onElementChange(boxId, newOuter);
      }
    }

    function handleKeyDown(evt: KeyboardEvent) {
      const editing = editingBoxRef.current;
      if (!editing) return;
      if (evt.key === "Escape") {
        evt.preventDefault();
        // Restore original HTML; bypass the save in handleFocusOut by
        // clearing the ref before triggering blur.
        editing.box.contentEditable = "false";
        editing.box.outerHTML = editing.original;
        editingBoxRef.current = null;
      }
    }

    root.addEventListener("click", handleClick);
    root.addEventListener("focusout", handleFocusOut as EventListener, true);
    root.addEventListener("keydown", handleKeyDown as EventListener, true);
    return () => {
      root.removeEventListener("click", handleClick);
      root.removeEventListener("focusout", handleFocusOut as EventListener, true);
      root.removeEventListener("keydown", handleKeyDown as EventListener, true);
    };
  }, [onClickElement, onElementChange]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center p-2 border-b">
        <span className={T.heading}>HTML editor</span>
        {status && (
          <span className={`${T.body} text-slate-500`} aria-live="polite">
            {status}
          </span>
        )}
      </div>
      <div
        ref={hostRef}
        data-testid="html-editor-host"
        className="flex-1 overflow-auto bg-white"
      />
    </div>
  );
}

/** Minimal CSS.escape shim for older runtimes — only needed for box_id, which
 *  is always alphanumeric + dash, so a no-op identity is fine. */
function cssEscape(s: string): string {
  return s.replace(/"/g, '\\"');
}
