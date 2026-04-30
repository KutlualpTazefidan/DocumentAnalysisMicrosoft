import { useQuery } from "@tanstack/react-query";
import { getElement } from "../api/docs";

export function useElement(slug: string | undefined, elementId: string | undefined) {
  return useQuery({
    queryKey: ["element", slug, elementId],
    queryFn: () => getElement(slug!, elementId!),
    enabled: !!slug && !!elementId,
  });
}
