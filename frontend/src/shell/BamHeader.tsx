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
  tenantName,
  onSettings,
  onLogout,
  centerSlot,
}: {
  theme: RoleTheme;
  name: string;
  tenantName?: string | null;
  onSettings: () => void;
  onLogout: () => void;
  centerSlot?: ReactNode;
}): JSX.Element {
  return (
    <header className="flex-shrink-0">
      <div className="h-12 bg-[#d6d6d6] flex items-center gap-4 px-4">
        {/* Brand lockup: BAM mark stacked over the GOLDENS wordmark */}
        <div className="flex flex-col items-start justify-center leading-none">
          <img src="/brand/bam-logo-tight.png" alt="BAM" className="h-6 w-auto" />
          <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-bam-navy mt-0.5">
            Goldens
          </span>
        </div>

        <div className="flex-1 flex justify-center">{centerSlot}</div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            title="Benachrichtigungen"
            aria-label="Benachrichtigungen"
            className="p-1.5 rounded text-ink-muted hover:text-bam-navy hover:bg-canvas"
          >
            <Bell className="w-4 h-4" aria-hidden />
          </button>
          {/* Vertical separator between the bell and the account control. */}
          <span aria-hidden className="h-6 w-px bg-line" />
          <RoleMenu
            theme={theme}
            name={name}
            tenantName={tenantName}
            onSettings={onSettings}
            onLogout={onLogout}
          />
        </div>
      </div>
    </header>
  );
}
