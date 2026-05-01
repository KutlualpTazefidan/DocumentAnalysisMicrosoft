import { useQuery } from "@tanstack/react-query";
import { getCurateElement, listQuestions } from "../api/curatorClient";
import type { CuratorQuestion } from "../api/curatorClient";
import type { DocumentElement } from "../../shared/types/domain";

export interface ElementWithQuestions {
  element: DocumentElement;
  entries: CuratorQuestion[];
}

export function useElement(slug: string | undefined, elementId: string | undefined) {
  return useQuery<ElementWithQuestions>({
    queryKey: ["curate", "element", slug, elementId],
    queryFn: async () => {
      const [element, entries] = await Promise.all([
        getCurateElement(slug!, elementId!),
        listQuestions(slug!, elementId!),
      ]);
      return { element, entries };
    },
    enabled: !!slug && !!elementId,
  });
}
