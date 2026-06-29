// frontend/src/admin/hooks/useActiveFile.ts
import { useSearchParams } from "react-router-dom";

/** Global "active file" = the ?file=<slug> URL query param. Single source of
 * truth shared across all workspace tabs (the dropdown writes it, tabs read it). */
export function useActiveFile(): {
  file: string | null;
  setFile: (slug: string | null) => void;
} {
  const [params, setParams] = useSearchParams();
  const file = params.get("file");
  const setFile = (slug: string | null) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (slug) next.set("file", slug);
        else next.delete("file");
        return next;
      },
      { replace: false }
    );
  };
  return { file, setFile };
}
