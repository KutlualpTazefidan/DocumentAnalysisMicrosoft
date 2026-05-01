import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useRef, useState } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { defaultKeymap } from "@codemirror/commands";
import { html as htmlLang } from "@codemirror/lang-html";

interface Props {
  html: string;
  onChange: (html: string) => void;
  onClickElement: (boxId: string) => void;
}

export function HtmlEditor({ html, onChange, onClickElement }: Props): JSX.Element {
  const [mode, setMode] = useState<"wysiwyg" | "raw">("wysiwyg");
  const cmHostRef = useRef<HTMLDivElement>(null);
  const cmRef = useRef<EditorView | null>(null);

  const editor = useEditor({
    extensions: [StarterKit],
    content: html,
    editorProps: {
      handleClick(view, _pos, evt) {
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

  useEffect(() => {
    if (mode !== "raw" || !cmHostRef.current) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: html,
        extensions: [keymap.of(defaultKeymap), htmlLang(), EditorView.updateListener.of((v) => {
          if (v.docChanged) onChange(v.state.doc.toString());
        })],
      }),
      parent: cmHostRef.current,
    });
    cmRef.current = view;
    return () => {
      view.destroy();
      cmRef.current = null;
    };
  }, [mode, html, onChange]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center p-2 border-b">
        <span className="text-sm font-semibold">HTML editor</span>
        <button
          type="button"
          className="text-xs underline"
          onClick={() => setMode((m) => (m === "wysiwyg" ? "raw" : "wysiwyg"))}
        >
          {mode === "wysiwyg" ? "Raw HTML" : "WYSIWYG"}
        </button>
      </div>
      <div className="flex-1 overflow-auto p-2">
        {mode === "wysiwyg" ? <EditorContent editor={editor} /> : <div ref={cmHostRef} />}
      </div>
    </div>
  );
}
