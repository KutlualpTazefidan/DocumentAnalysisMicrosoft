import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, LogOut, Settings } from "lucide-react";
import type { RoleTheme } from "./ColorThemes";

/**
 * Clickable role pill in the header. Click opens a menu with
 * Einstellungen + Abmelden.
 */
export function RoleMenu({
  theme,
  name,
  onSettings,
  onLogout,
}: {
  theme: RoleTheme;
  name: string;
  onSettings: () => void;
  onLogout: () => void;
}): JSX.Element {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold tracking-wide focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
          style={{ background: theme.accent, color: "#1f2937" }}
          data-role={theme.label.toLowerCase()}
          aria-label={`${theme.label} ${name} — Menü öffnen`}
        >
          <span>{theme.label}</span>
          <span aria-hidden>·</span>
          <span>{name}</span>
          <ChevronDown className="w-3.5 h-3.5" aria-hidden />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 min-w-44 rounded-md bg-white shadow-lg border border-slate-200 py-1 text-sm text-slate-800"
        >
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
