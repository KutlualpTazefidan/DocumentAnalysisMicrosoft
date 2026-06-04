import type { ComponentType } from "react";
import { Link, useLocation } from "react-router-dom";

export interface RailItem {
  to: string;
  /** pathname prefix that marks this item active */
  match: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

/**
 * The BAM left icon rail — the primary section nav, rendered as a narrow
 * vertical strip of icons with an active cyan indicator. Replaces the old
 * horizontal top-nav links.
 */
export function IconRail({ items }: { items: RailItem[] }): JSX.Element {
  const { pathname } = useLocation();

  return (
    <nav
      aria-label="Hauptnavigation"
      className="w-12 flex-shrink-0 bg-rail border-r border-line flex flex-col items-center py-2 gap-1"
    >
      {items.map((it) => {
        const active = pathname.startsWith(it.match);
        const Icon = it.icon;
        return (
          <Link
            key={it.to}
            to={it.to}
            title={it.label}
            aria-label={it.label}
            aria-current={active ? "page" : undefined}
            className={`relative flex items-center justify-center w-10 h-10 rounded transition-colors ${
              active
                ? "text-bam-cyan bg-white"
                : "text-ink-muted hover:text-bam-navy hover:bg-white"
            }`}
          >
            {active && (
              <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded bg-bam-cyan" />
            )}
            <Icon className="w-5 h-5" />
          </Link>
        );
      })}
    </nav>
  );
}
