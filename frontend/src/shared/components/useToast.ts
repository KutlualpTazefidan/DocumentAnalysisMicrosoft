import { useContext } from "react";
import { __TOAST_CTX__ } from "./Toaster";

export function useToast() {
  const ctx = useContext(__TOAST_CTX__);
  if (!ctx) throw new Error("useToast outside ToastProvider");
  return {
    success: (text: string) => ctx.push({ kind: "success", text }),
    error: (text: string) => ctx.push({ kind: "error", text }),
    info: (text: string) => ctx.push({ kind: "info", text }),
  };
}
