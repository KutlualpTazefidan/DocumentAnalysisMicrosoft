import { useMutation, useQueryClient } from "@tanstack/react-query";
import { refineEntry } from "../api/entries";
import type { RefineRequest, RefineResponse } from "../types/domain";

interface Args {
  entryId: string;
  body: RefineRequest;
  slug: string;
  elementId: string;
}

export function useRefineEntry() {
  const qc = useQueryClient();
  return useMutation<RefineResponse, Error, Args>({
    mutationFn: ({ entryId, body }) => refineEntry(entryId, body),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["doc-elements", slug] });
    },
  });
}
