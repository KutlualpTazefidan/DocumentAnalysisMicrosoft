import { useParams } from "react-router-dom";
import { DocStepTabs } from "../components/DocStepTabs";

export function Synthesise() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <div className="flex flex-col h-full">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white text-sm border-b border-navy-700 flex-shrink-0">
        <DocStepTabs slug={slug!} />
      </div>
      <div className="p-6">coming soon</div>
    </div>
  );
}
