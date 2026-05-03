# In-Place Element Editor — Design Spec

> **Date:** 2026-05-03
> **Phase:** A.1.1 (post-A.1.0 polish)
> **Goal:** Replace the three editor tabs in `HtmlEditor` (Preview / WYSIWYG /
> Raw) with one in-place editor where the rendered HTML *is* the editable
> surface, click-to-edit-cell granularity, no mode switching.

## Problem

Today the extract page has three modes for the same data:

- **Preview** — sandboxed iframe (srcdoc), read-only.
- **WYSIWYG** — Tiptap editor, edits but renders Tiptap's interpretation, not the
  actual MathML/figure/table HTML; round-trips through Tiptap's schema can drop
  custom attributes (`data-source-box`, `data-aux-zone`, etc.).
- **Raw** — CodeMirror, plain-text HTML editing, accurate but unfriendly.

Users have to switch contexts to compare or to edit. WYSIWYG doesn't faithfully
render what the system actually produces. The three-tab UI duplicates concerns
because the underlying data model already has clean per-element ownership: each
element in `mineru.json` has a unique `box_id` mirrored by `data-source-box` in
the HTML.

## Scope

**In scope (text editing inside elements):**
- Paragraph text
- Heading text
- Caption text (figures, tables)
- Aux text (page headers/footers)
- Table cell text (whole-table HTML round-trips through the element)
- Math (LaTeX-aware editing — best-effort via DOM contenteditable)

**Out of scope (handled at the bbox layer in the existing sidebar):**
- Adding elements → existing "New box" button
- Removing elements → existing "Delete box" / kind=discard
- Moving elements → existing bbox edit
- Changing kind → existing properties panel kind dropdown
- Re-running VLM on a region → existing "Re-extract this box" button

## User flow

```
User scrolls extract preview — same rendered HTML as before.
   │
   ├─ 1st click on any element with [data-source-box]
   │     → highlight (existing behavior); sidebar selects that box.
   │
   ├─ 2nd click on the SAME box within 800 ms (or Enter while focused)
   │     → element becomes contenteditable=true, focus + cursor at click point.
   │
   ├─ User types
   │
   ├─ Esc → cancel; restore from prop, leave edit mode.
   │
   └─ Blur (click elsewhere) or Enter+Cmd
         → read box.outerHTML
         → PATCH /api/admin/docs/<slug>/elements/<box_id> { html_snippet }
         → backend re-runs _convert_inline_latex (so user can type $\alpha$
           and get <math>α</math> on save)
         → mineru.json + html.html updated
         → React Query invalidates → fresh html.html re-renders
         → small "Gespeichert" toast.
```

## Backend

### New endpoint

```
PATCH /api/admin/docs/<slug>/elements/<box_id>

Request:  { "html_snippet": "<p data-source-box=\"...\">edited text</p>" }
Response: { "box_id": "...", "html_snippet": "<p ...>edited text + converted math</p>" }
```

Implementation in `local_pdf/api/routers/admin/segments.py`:

```python
class UpdateElementRequest(BaseModel):
    html_snippet: str

@router.patch("/api/admin/docs/{slug}/elements/{box_id}")
async def update_element(
    slug: str,
    box_id: str,
    body: UpdateElementRequest,
    request: Request,
) -> dict[str, Any]:
    cfg = request.app.state.config
    m = read_mineru(cfg.data_root, slug)
    if m is None:
        raise HTTPException(404, "no mineru output")
    elements = list(m.get("elements", []))
    found = None
    for i, el in enumerate(elements):
        if el.get("box_id") == box_id:
            # Run LaTeX/footnote/etc passes so user input stays consistent
            # with the segment-time pipeline.
            new_html = _convert_inline_latex(body.html_snippet)
            elements[i] = {
                **el,
                "html_snippet": new_html,
                "html_snippet_raw": body.html_snippet,
            }
            found = elements[i]
            break
    if found is None:
        raise HTTPException(404, f"box not found: {box_id}")
    write_mineru(cfg.data_root, slug, {**m, "elements": elements})
    _refresh_active_html(cfg, slug)
    return found
```

No schema changes. `html_snippet_raw` is already optional; we store the
user's submitted form there so the Quelltext panel reflects what they typed.

### Test

`test_update_element_persists_and_refreshes_html` — PATCH with a new snippet,
then GET /mineru and /html and assert both reflect the change.

## Frontend

### `HtmlEditor.tsx` rewrite

**Removed**: mode tabs, Tiptap editor + extensions, CodeMirror raw editor, the
`onChange` PUT-html plumbing (replaced by per-element PATCH).

**New**: single Shadow DOM mount that renders the html.html.

```tsx
function HtmlEditor({ html, slug, onClickElement }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const lastClick = useRef<{ boxId: string; ts: number } | null>(null);
  const updateElement = useUpdateElement(slug);

  useEffect(() => {
    if (!hostRef.current) return;
    let root = hostRef.current.shadowRoot;
    if (!root) root = hostRef.current.attachShadow({ mode: "open" });
    root.innerHTML = `${EDITOR_CSS}${html}`;

    const onClick = (e: Event) => {
      const t = e.target as HTMLElement;
      const box = t.closest("[data-source-box]") as HTMLElement | null;
      if (!box) return;
      const boxId = box.getAttribute("data-source-box")!;

      const now = Date.now();
      const prev = lastClick.current;
      const isSecondClick =
        prev && prev.boxId === boxId && now - prev.ts < 800;

      if (isSecondClick && box.contentEditable !== "true") {
        box.contentEditable = "true";
        box.focus();
        // Cursor at click position (browser default places it sensibly)
        lastClick.current = null;
      } else {
        onClickElement(boxId);
        lastClick.current = { boxId, ts: now };
      }
    };

    const onBlur = (e: FocusEvent) => {
      const box = (e.target as HTMLElement).closest("[data-source-box]") as
        | HTMLElement
        | null;
      if (!box || box.contentEditable !== "true") return;
      const boxId = box.getAttribute("data-source-box")!;
      const newHtml = box.outerHTML.replace(/ contenteditable="true"/g, "");
      box.contentEditable = "false";
      updateElement.mutate({ boxId, html: newHtml });
    };

    const onKey = (e: KeyboardEvent) => {
      const box = (e.target as HTMLElement).closest("[data-source-box]") as
        | HTMLElement
        | null;
      if (!box || box.contentEditable !== "true") return;
      if (e.key === "Escape") {
        e.preventDefault();
        box.blur();
        // re-render restores from prop; mutation is not fired because we
        // detect via a flag (see implementation)
      }
    };

    root.addEventListener("click", onClick);
    root.addEventListener("focusout", onBlur as any, true);
    root.addEventListener("keydown", onKey as any, true);
    return () => {
      root!.removeEventListener("click", onClick);
      root!.removeEventListener("focusout", onBlur as any, true);
      root!.removeEventListener("keydown", onKey as any, true);
    };
  }, [html, slug, onClickElement, updateElement]);

  return <div ref={hostRef} className="h-full overflow-auto" />;
}
```

CSS injected alongside `_PDF_STYLE`:

```css
[data-source-box]{outline:1px dashed transparent;transition:outline-color 0.15s}
[data-source-box]:hover{outline-color:#93c5fd;cursor:text}
[data-source-box].is-highlighted{outline-color:#2563eb;outline-style:dashed}
[data-source-box][contenteditable="true"]{outline-color:#2563eb;outline-style:solid;outline-offset:2px}
```

### New mutation hook

`frontend/src/admin/hooks/useExtract.ts`:

```ts
export function useUpdateElement(slug: string) {
  const qc = useQueryClient();
  const token = useAuth().token;
  return useMutation({
    mutationFn: ({ boxId, html }: { boxId: string; html: string }) =>
      fetch(`${apiBase()}/api/admin/docs/${slug}/elements/${boxId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-Auth-Token": token },
        body: JSON.stringify({ html_snippet: html }),
      }).then((r) => {
        if (!r.ok) throw new Error(`update failed: ${r.status}`);
        return r.json();
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["html", slug] });
      qc.invalidateQueries({ queryKey: ["mineru", slug] });
    },
  });
}
```

### Edge cases

- **Math editing**: contenteditable on the box flows through to `<math>`/`<mi>`
  descendants — browser allows cursor placement inside MathML elements. Editing
  is functional but clunky (visual MathML doesn't have a friendly text editor
  affordance). For users who need it, the Quelltext panel still shows the raw
  LaTeX form — they can edit there mentally, type the new form into the inline
  edit box (e.g. `$\beta$` for `<math>β</math>`), and the backend re-runs
  `_convert_inline_latex` on save.
- **Tables**: clicking inside a `<td>` flows the contenteditable up to the
  table's box (since cells don't carry their own `data-source-box`). On blur,
  the entire `<div class="extracted-table">…</div>` outerHTML is saved. Cell
  edits survive because they're inside that outerHTML.
- **Different click during edit**: blur fires on the editing box (saves), then
  the new click triggers highlight on the new box. Sequential, no conflict.
- **Same click during edit**: contenteditable already true, no save fires until
  user clicks elsewhere or presses Esc.
- **Save latency**: 100–500 ms (PATCH → re-render html.html → re-fetch). UI
  shows the existing `savingStatus` indicator next to the action buttons.

## Out-of-scope follow-ups (noted, not in this PR)

- Floating bubble toolbar (B / I / sub / sup) — skipped per user direction.
- "Edit as LaTeX" overlay for math — would swap the rendered `<math>` for a
  textarea showing the source LaTeX; deferred.
- Undo/redo across save boundaries — browsers' contenteditable history is
  per-edit-session; not preserved across saves.

## Files touched

- New: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/segments.py`
  → add `UpdateElementRequest` + `update_element` endpoint.
- New: `frontend/src/admin/hooks/useExtract.ts` → add `useUpdateElement`.
- Rewrite: `frontend/src/admin/components/HtmlEditor.tsx`.
- Update: `frontend/src/admin/routes/extract.tsx` → drop `onChange`, drop
  `usePutHtml`, pass slug + token (or rely on hook reading from context).
- Remove deps: `@tiptap/*`, `@codemirror/*` (after verifying no other consumers).
- Tests: `test_routers_admin_segments.py` add update_element test;
  `frontend/tests/admin/components/HtmlEditor.test.tsx` rewrite for new behavior.

## Estimate
~half a day end to end.
