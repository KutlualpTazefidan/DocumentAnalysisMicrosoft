import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ElementSidebar } from "../components/ElementSidebar";
import { ElementDetail } from "../components/ElementDetail";
import { HelpModal } from "../components/HelpModal";
import { useElements } from "../hooks/useElements";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";

export function DocElements() {
  const { slug, elementId } = useParams<{ slug: string; elementId?: string }>();
  const navigate = useNavigate();
  const { data: elements } = useElements(slug);
  const [helpOpen, setHelpOpen] = useState(false);

  // If no elementId in URL, redirect to first element once data is loaded.
  useEffect(() => {
    if (!elementId && elements && elements.length > 0 && slug) {
      navigate(
        `/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(elements[0].element.element_id)}`,
        { replace: true },
      );
    }
  }, [elementId, elements, slug, navigate]);

  const currentIndex = useMemo(() => {
    if (!elements || !elementId) return -1;
    return elements.findIndex((e) => e.element.element_id === elementId);
  }, [elements, elementId]);

  function goToIndex(idx: number) {
    if (!elements || !slug) return;
    const clamped = Math.max(0, Math.min(idx, elements.length - 1));
    const target = elements[clamped];
    if (target) {
      navigate(
        `/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(target.element.element_id)}`,
      );
    }
  }

  function selectElement(id: string) {
    if (!slug) return;
    navigate(`/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(id)}`);
  }

  useKeyboardShortcuts({
    j: () => goToIndex(currentIndex + 1),
    k: () => goToIndex(currentIndex - 1),
    ArrowDown: () => goToIndex(currentIndex + 1),
    ArrowUp: () => goToIndex(currentIndex - 1),
    "?": () => setHelpOpen(true),
  });

  if (!slug) return <p>Missing slug.</p>;

  return (
    <div className="min-h-screen flex flex-col">
      <div className="flex flex-1 overflow-hidden">
        <ElementSidebar
          slug={slug}
          activeElementId={elementId}
          onSelect={selectElement}
        />
        <main className="flex-1 overflow-y-auto p-8 max-w-3xl mx-auto w-full">
          {elementId ? (
            <ElementDetail
              slug={slug}
              elementId={elementId}
              onWeiter={() => goToIndex(currentIndex + 1)}
            />
          ) : null}
        </main>
      </div>
      {helpOpen ? <HelpModal onClose={() => setHelpOpen(false)} /> : null}
    </div>
  );
}
