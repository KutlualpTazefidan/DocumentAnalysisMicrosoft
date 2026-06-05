import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { LogOut, Power, Settings } from "lucide-react";
import type { RoleTheme } from "./ColorThemes";

/**
 * Account control in the header — mirrors the BAM tool family: the user's
 * name with the active Fachbereich (display name) beneath it, and a power
 * (on/off) icon on the right. Click opens a menu carrying the role plus
 * Einstellungen + Abmelden.
 */
export function RoleMenu({
  theme,
  name,
  tenantName,
  onSettings,
  onLogout,
}: {
  theme: RoleTheme;
  name: string;
  /** Active Fachbereich display name (Anzeigename) — shown under the name. */
  tenantName?: string | null;
  onSettings: () => void;
  onLogout: () => void;
}): JSX.Element {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 px-2 py-1 rounded text-bam-navy hover:bg-black/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-bam-cyan"
          data-role={theme.label.toLowerCase()}
          aria-label={`${name}${tenantName ? `, ${tenantName}` : ""} (${theme.label}) — Menü öffnen`}
        >
          <span className="flex flex-col items-start leading-tight">
            {/* Normal weight (not bold). */}
            <span className="text-[12px]">{name}</span>
            {tenantName && (
              <span className="text-[10px] text-ink-muted">{tenantName}</span>
            )}
          </span>
          {/* Power icon on the right, in the same (normal) colour as the text. */}
          <Power className="w-4 h-4" aria-hidden />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 min-w-44 rounded-md bg-white shadow-lg border border-slate-200 py-1 text-sm text-slate-800"
        >
          {/* Role lives in the popup, not on the button. */}
          <DropdownMenu.Label className="flex items-center gap-2 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: theme.accent }}
              aria-hidden
            />
            {theme.label}
          </DropdownMenu.Label>
          <DropdownMenu.Separator className="my-1 h-px bg-slate-200" />
          <DropdownMenu.Item
            onSelect={onSettings}
            className="flex items-center gap-2 px-3 py-1.5 cursor-pointer outline-none data-[highlighted]:bg-slate-100"
          >
            <Settings className="w-4 h-4 text-slate-500" aria-hidden />
            Einstellungen
          </DropdownMenu.Item>
          <DropdownMenu.Separator className="my-1 h-px bg-slate-200" />
          <DropdownMenu.Item
            onSelect={onLogout}
            className="flex items-center gap-2 px-3 py-1.5 cursor-pointer outline-none text-danger-500 data-[highlighted]:bg-rose-50"
          >
            <LogOut className="w-4 h-4" aria-hidden />
            Abmelden
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
