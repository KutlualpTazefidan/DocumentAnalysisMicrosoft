// frontend/src/admin/components/DocStepTabs.tsx
import { FileText, Folder, Scissors } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

interface Props {
  slug: string;
}

const TABS = [
  { key: "files", label: "Files", icon: Folder, href: "/admin/inbox" },
  { key: "segment", label: "Segment", icon: Scissors, href: (slug: string) => `/admin/doc/${slug}/segment` },
  { key: "extract", label: "Extract", icon: FileText, href: (slug: string) => `/admin/doc/${slug}/extract` },
] as const;

export function DocStepTabs({ slug }: Props): JSX.Element {
  const { pathname } = useLocation();

  function isActive(key: string): boolean {
    if (key === "files") return false;
    if (key === "segment") return pathname.endsWith("/segment");
    if (key === "extract") return pathname.endsWith("/extract");
    return false;
  }

  function tabHref(tab: (typeof TABS)[number]): string {
    if (typeof tab.href === "string") return tab.href;
    return tab.href(slug);
  }

  return (
    <nav role="tablist" className="flex items-center gap-1">
      {TABS.map((tab) => {
        const active = isActive(tab.key);
        const Icon = tab.icon;
        return (
          <Link
            key={tab.key}
            to={tabHref(tab)}
            role="tab"
            aria-current={active ? "page" : undefined}
            className={[
              "flex items-center gap-1.5 px-3 py-1 rounded text-sm font-medium transition-colors",
              active
                ? "bg-navy-700 text-white border-b-2 border-blue-400"
                : "text-navy-200 hover:text-white hover:bg-navy-700/50",
            ].join(" ")}
          >
            <Icon className="w-3.5 h-3.5" aria-hidden />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
