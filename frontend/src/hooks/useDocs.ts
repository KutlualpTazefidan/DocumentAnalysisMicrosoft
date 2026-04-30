import { useQuery } from "@tanstack/react-query";
import { listDocs } from "../api/docs";

export function useDocs() {
  return useQuery({
    queryKey: ["docs"],
    queryFn: listDocs,
  });
}
