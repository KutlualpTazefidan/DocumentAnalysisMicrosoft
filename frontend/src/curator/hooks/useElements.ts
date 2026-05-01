import { useQuery } from "@tanstack/react-query";
import { listCurateElements, getToken } from "../api/curatorClient";
import type { ElementWithCounts } from "../../shared/types/domain";

export function useElements(slug: string | undefined) {
  return useQuery<ElementWithCounts[]>({
    queryKey: ["curate", "doc-elements", slug],
    queryFn: async () => {
      const elements = await listCurateElements(slug!, getToken()!);
      return elements.map((element) => ({ element, count_active_entries: 0 }));
    },
    enabled: !!slug && !!getToken(),
  });
}
