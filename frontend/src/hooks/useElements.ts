import { useQuery } from "@tanstack/react-query";
import { listElements } from "../api/docs";

export function useElements(slug: string | undefined) {
  return useQuery({
    queryKey: ["doc-elements", slug],
    queryFn: () => listElements(slug!),
    enabled: !!slug,
  });
}
