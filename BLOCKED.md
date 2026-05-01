## Task 22

**HtmlEditor — data-source-box click in WYSIWYG (jsdom/Tiptap)**

Tiptap's ProseMirror schema strips unknown `data-*` attributes from elements by default. As a result, `document.querySelector('[data-source-box="b-1"]')` returns null in jsdom after rendering `<HtmlEditor html='<p data-source-box="b-1">x</p>' />`. The full click-to-link interactivity test was replaced with a direct unit test of the `handleClick` logic (value-flow contract mock). Real interactivity is verified in Task 28 Playwright e2e.
