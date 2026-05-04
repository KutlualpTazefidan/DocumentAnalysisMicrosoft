// frontend/src/admin/components/DocStepTabs.tsx
import { FileText, Folder, GitCompare, Sparkles } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { T } from "../styles/typography";

interface Props {
  slug?: string;
}

const TABS = [
  { key: "files", label: "Files", icon: Folder, href: (_slug: string) => "/admin/inbox" },
  { key: "extract", label: "Extract", icon: FileText, href: (slug: string) => `/admin/doc/${slug}/extract` },
  { key: "synthesise", label: "Synthesise", icon: Sparkles, href: (slug: string) => `/admin/doc/${slug}/synthesise` },
  { key: "compare", label: "Vergleich", icon: GitCompare, href: (slug: string) => `/admin/doc/${slug}/compare` },
] as const;

export function DocStepTabs({ slug }: Props): JSX.Element {
  const { pathname } = useLocation();

  function isActive(key: string): boolean {
    if (key === "files") return pathname.endsWith("/inbox");
    if (key === "extract") return pathname.endsWith("/extract");
    if (key === "synthesise") return pathname.endsWith("/synthesise");
    if (key === "compare") return pathname.endsWith("/compare");
    return false;
  }

  const activeTabClass = "text-white border-b-2 border-blue-400";
  const inactiveTabClass = "text-navy-200 hover:text-white hover:bg-navy-700/40";
  const disabledTabClass = "text-navy-500 opacity-50 cursor-not-allowed";
  const baseTabClass = `flex items-center gap-2 px-4 py-2 ${T.body} font-medium transition-colors`;

  return (
    <nav role="tablist" className="flex items-center border-b border-navy-700 -mb-px">
      {TABS.map((tab) => {
        const active = isActive(tab.key);
        const Icon = tab.icon;
        const needsSlug = tab.key !== "files";
        const disabled = needsSlug && !slug;

        if (disabled) {
          return (
            <span
              key={tab.key}
              role="tab"
              aria-disabled="true"
              title="Bitte zuerst ein Dokument öffnen."
              className={`${baseTabClass} ${disabledTabClass}`}
            >
              <Icon className="w-4 h-4" aria-hidden />
              {tab.label}
            </span>
          );
        }

        return (
          <Link
            key={tab.key}
            to={tab.href(slug ?? "")}
            role="tab"
            aria-current={active ? "page" : undefined}
            className={`${baseTabClass} ${active ? activeTabClass : inactiveTabClass}`}
          >
            <Icon className="w-4 h-4" aria-hidden />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
