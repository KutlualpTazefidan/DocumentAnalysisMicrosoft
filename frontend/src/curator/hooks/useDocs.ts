import { useQuery } from "@tanstack/react-query";
import { listAssignedDocs, getToken } from "../api/curatorClient";

export function useDocs() {
  return useQuery({
    queryKey: ["curate", "docs"],
    queryFn: () => listAssignedDocs(getToken()!),
    enabled: !!getToken(),
  });
}
