import type { ReactNode } from "react";
import { Bell } from "../shared/icons";
import type { RoleTheme } from "./shared/ColorThemes";
import { RoleMenu } from "./shared/RoleMenu";

/**
 * The BAM top header — white bar with a cyan accent hairline, carrying the
 * BAM mark + GOLDENS lockup on the left, an optional centered control slot
 * (admin uses it for the vLLM control), and the tenant badge + notification
 * icon + role pill on the right. Replaces the old dark per-shell headers.
 */
export function BamHeader({
  theme,
  name,
  tenantSlug,
  onSettings,
  onLogout,
  centerSlot,
}: {
  theme: RoleTheme;
  name: string;
  tenantSlug?: string | null;
  onSettings: () => void;
  onLogout: () => void;
  centerSlot?: ReactNode;
}): JSX.Element {
  return (
    <header className="flex-shrink-0">
      <div className="h-12 bg-white flex items-center gap-4 px-4">
        {/* Brand lockup: BAM mark+wordmark · GOLDENS */}
        <div className="flex items-center gap-2.5">
          <img src="/brand/bam-logo.png" alt="BAM" className="h-6 w-auto" />
          <span className="text-[15px] font-bold uppercase tracking-[0.12em] text-bam-navy">
            Goldens
          </span>
        </div>

        <div className="flex-1 flex justify-center">{centerSlot}</div>

        <div className="flex items-center gap-3">
          {tenantSlug && (
            <span
              className="px-2 py-0.5 rounded text-xs font-mono border border-line text-ink-muted"
              title="Aktiver Fachbereich"
            >
              {tenantSlug}
            </span>
          )}
          <button
            type="button"
            title="Benachrichtigungen"
            aria-label="Benachrichtigungen"
            className="p-1.5 rounded text-ink-muted hover:text-bam-navy hover:bg-canvas"
          >
            <Bell className="w-4 h-4" aria-hidden />
          </button>
          <RoleMenu
            theme={theme}
            name={name}
            onSettings={onSettings}
            onLogout={onLogout}
          />
        </div>
      </div>
      {/* BAM cyan accent hairline under the header. */}
      <div className="h-[2px] bg-bam-cyan" />
    </header>
  );
}
