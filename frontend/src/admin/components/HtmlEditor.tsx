import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useRef, useState } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { defaultKeymap } from "@codemirror/commands";
import { html as htmlLang } from "@codemirror/lang-html";
import { T } from "../styles/typography";

// PDF-style typography mirroring extract.py _PDF_STYLE, scoped to ProseMirror.
// TipTap strips the <style> block from the HTML it parses, but we can style
// the known tags it preserves (h1/h2/p/pre/code) via this injected stylesheet.
const WYSIWYG_STYLE = `
.ProseMirror { font-family: Georgia,'Times New Roman',serif; max-width:720px; margin:0 auto; line-height:1.6; color:#1f2937; padding:0.5rem; }
.ProseMirror h1 { font-size:2em; font-weight:bold; text-align:center; margin:1.5em 0 0.5em; }
.ProseMirror h2 { font-size:1.5em; font-weight:bold; margin:1.2em 0 0.4em; border-bottom:1px solid #d1d5db; padding-bottom:0.2em; }
.ProseMirror h3 { font-size:1.2em; font-weight:bold; margin:1em 0 0.3em; }
.ProseMirror p  { margin:0.6em 0; }
.ProseMirror pre { background:#f3f4f6; padding:1em; border-radius:4px; overflow-x:auto; }
.ProseMirror code { font-family:"SF Mono",Menlo,monospace; }
`.trim();

type Mode = "preview" | "wysiwyg" | "raw";

interface Props {
  html: string;
  onChange: (html: string) => void;
  onClickElement: (boxId: string) => void;
}

export function HtmlEditor({ html, onChange, onClickElement }: Props): JSX.Element {
  // Default to preview so the user immediately sees PDF-styled output.
  const [mode, setMode] = useState<Mode>("preview");
  const cmHostRef = useRef<HTMLDivElement>(null);
  const cmRef = useRef<EditorView | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const editor = useEditor({
    extensions: [StarterKit],
    content: html,
    editorProps: {
      handleClick(_view, _pos, evt) {
        const t = evt.target as HTMLElement;
        const el = t.closest("[data-source-box]") as HTMLElement | null;
        if (el) {
          onClickElement(el.getAttribute("data-source-box")!);
          return true;
        }
        return false;
      },
    },
    onUpdate({ editor }) {
      onChange(editor.getHTML());
    },
  });

  // Keep TipTap in sync when html prop changes (e.g. after re-extract).
  useEffect(() => {
    if (editor && html !== editor.getHTML()) {
      editor.commands.setContent(html, false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [html]);

  // CodeMirror: mount/unmount when raw mode activates.
  useEffect(() => {
    if (mode !== "raw" || !cmHostRef.current) return;
    const cmView = new EditorView({
      state: EditorState.create({
        doc: html,
        extensions: [keymap.of(defaultKeymap), htmlLang(), EditorView.updateListener.of((v) => {
          if (v.docChanged) onChange(v.state.doc.toString());
        })],
      }),
      parent: cmHostRef.current,
    });
    cmRef.current = cmView;
    return () => {
      cmView.destroy();
      cmRef.current = null;
    };
  }, [mode, html, onChange]);

  // Preview iframe: attach click listener on load to dispatch onClickElement.
  function handleIframeLoad() {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    doc.addEventListener("click", (evt) => {
      const t = evt.target as HTMLElement;
      const el = t.closest("[data-source-box]") as HTMLElement | null;
      if (el) {
        onClickElement(el.getAttribute("data-source-box")!);
      }
    });
  }

  const modeButtons: { key: Mode; label: string }[] = [
    { key: "preview", label: "Vorschau" },
    { key: "wysiwyg", label: "WYSIWYG" },
    { key: "raw", label: "Quelltext" },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Inject WYSIWYG typography */}
      <style>{WYSIWYG_STYLE}</style>

      <div className="flex justify-between items-center p-2 border-b">
        <span className={`${T.heading}`}>HTML editor</span>
        {/* 3-button segmented control */}
        <div className={`flex rounded overflow-hidden border border-slate-300 ${T.body}`} role="group" aria-label="Editor mode">
          {modeButtons.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={mode === key}
              className={
                mode === key
                  ? "px-2 py-1 bg-slate-700 text-white font-medium"
                  : "px-2 py-1 bg-white text-slate-600 hover:bg-slate-50"
              }
              onClick={() => setMode(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {mode === "preview" && (
          // sandbox="allow-same-origin" lets the <style> in <head> apply.
          // No allow-scripts: React side attaches the listener after load.
          <iframe
            ref={iframeRef}
            data-testid="html-preview-iframe"
            sandbox="allow-same-origin"
            srcDoc={html}
            className="w-full h-full border-none"
            title="HTML preview"
            onLoad={handleIframeLoad}
          />
        )}
        {mode === "wysiwyg" && (
          <div className="p-2">
            <EditorContent editor={editor} />
          </div>
        )}
        {mode === "raw" && (
          <div ref={cmHostRef} data-testid="codemirror-host" className="h-full" />
        )}
      </div>
    </div>
  );
}
