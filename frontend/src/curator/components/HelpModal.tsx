import * as Dialog from "@radix-ui/react-dialog";
import { HelpCircle, X } from "lucide-react";

const SHORTCUTS: Array<[string, string]> = [
  ["Enter (im Textarea)", "Speichern"],
  ["Enter (Textarea leer)", "Weiter"],
  ["Ctrl+Enter / Cmd+Enter", "Speichern (auch wenn Textarea Inhalt hat)"],
  ["Escape", "Modal schließen"],
  ["j / ArrowDown", "Sidebar nach unten"],
  ["k / ArrowUp", "Sidebar nach oben"],
  ["t (auf Tabelle)", "Volle Tabelle ↔ Stub"],
  ["?", "Diese Hilfe"],
];

export function HelpModal() {
  return (
    <Dialog.Root>
      <Dialog.Trigger className="btn-secondary inline-flex items-center gap-1">
        <HelpCircle className="w-4 h-4" /> Hilfe
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-lg font-semibold">Tastatur-Shortcuts</Dialog.Title>
            <Dialog.Close className="text-slate-500 hover:text-slate-700">
              <X className="w-4 h-4" />
            </Dialog.Close>
          </div>
          <Dialog.Description asChild>
            <dl className="space-y-2 text-sm">
              {SHORTCUTS.map(([k, v]) => (
                <div key={k} className="grid grid-cols-2 gap-4">
                  <dt className="font-mono text-slate-700">{k}</dt>
                  <dd className="text-slate-600">{v}</dd>
                </div>
              ))}
            </dl>
          </Dialog.Description>
          <Dialog.Close className="btn-secondary mt-4">Schließen</Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
