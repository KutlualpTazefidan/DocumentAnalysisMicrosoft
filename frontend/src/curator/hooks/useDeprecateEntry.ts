import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deprecateEntry } from "../api/entries";
import type { DeprecateRequest, DeprecateResponse } from "../../shared/types/domain";

interface Args {
  entryId: string;
  body: DeprecateRequest;
  slug: string;
  elementId: string;
}

export function useDeprecateEntry() {
  const qc = useQueryClient();
  return useMutation<DeprecateResponse, Error, Args>({
    mutationFn: ({ entryId, body }) => deprecateEntry(entryId, body),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["doc-elements", slug] });
    },
  });
}
