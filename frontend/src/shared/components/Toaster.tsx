import * as RT from "@radix-ui/react-toast";
import { createContext, useCallback, useState } from "react";

type ToastKind = "success" | "error" | "info";
type ToastEntry = { id: number; kind: ToastKind; text: string };

const Ctx = createContext<{ push: (e: Omit<ToastEntry, "id">) => void } | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastEntry[]>([]);
  const push = useCallback((e: Omit<ToastEntry, "id">) => {
    setItems((prev) => [...prev, { id: Date.now() + Math.random(), ...e }]);
  }, []);
  return (
    <Ctx.Provider value={{ push }}>
      <RT.Provider swipeDirection="right">
        {children}
        {items.map((t) => (
          <RT.Root
            key={t.id}
            className={`bg-white border rounded p-3 shadow ${
              t.kind === "error" ? "border-red-500" : t.kind === "success" ? "border-green-500" : "border-slate-300"
            }`}
            onOpenChange={(o) => { if (!o) setItems((prev) => prev.filter((x) => x.id !== t.id)); }}
          >
            <RT.Description>{t.text}</RT.Description>
          </RT.Root>
        ))}
        <RT.Viewport className="fixed bottom-4 right-4 flex flex-col gap-2 w-96 z-50" />
      </RT.Provider>
    </Ctx.Provider>
  );
}

export const __TOAST_CTX__ = Ctx;
export function Toaster() { return null; /* viewport rendered inside provider */ }
