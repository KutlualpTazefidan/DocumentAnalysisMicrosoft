// frontend/src/admin/components/DocStepTabs.tsx
import { FileText, Folder, Scissors, Sparkles } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

interface Props {
  slug: string;
}

const TABS = [
  { key: "files", label: "Files", icon: Folder, href: (_slug: string) => "/admin/inbox" },
  { key: "segment", label: "Segment", icon: Scissors, href: (slug: string) => `/admin/doc/${slug}/segment` },
  { key: "extract", label: "Extract", icon: FileText, href: (slug: string) => `/admin/doc/${slug}/extract` },
  { key: "synthesise", label: "Synthesise", icon: Sparkles, href: (slug: string) => `/admin/doc/${slug}/synthesise` },
] as const;

export function DocStepTabs({ slug }: Props): JSX.Element {
  const { pathname } = useLocation();

  function isActive(key: string): boolean {
    if (key === "files") return false;
    if (key === "segment") return pathname.endsWith("/segment");
    if (key === "extract") return pathname.endsWith("/extract");
    if (key === "synthesise") return pathname.endsWith("/synthesise");
    return false;
  }

  return (
    <nav role="tablist" className="flex items-center border-b border-navy-700 -mb-px">
      {TABS.map((tab) => {
        const active = isActive(tab.key);
        const Icon = tab.icon;
        return (
          <Link
            key={tab.key}
            to={tab.href(slug)}
            role="tab"
            aria-current={active ? "page" : undefined}
            className={[
              "flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors",
              active
                ? "text-white border-b-2 border-blue-400"
                : "text-navy-200 hover:text-white hover:bg-navy-700/40",
            ].join(" ")}
          >
            <Icon className="w-4 h-4" aria-hidden />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
