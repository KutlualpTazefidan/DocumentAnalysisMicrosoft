import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createEntry } from "../api/entries";
import type { CreateEntryRequest, CreateEntryResponse } from "../../shared/types/domain";

interface CreateArgs {
  slug: string;
  elementId: string;
  body: CreateEntryRequest;
}

export function useCreateEntry() {
  const qc = useQueryClient();
  return useMutation<CreateEntryResponse, Error, CreateArgs>({
    mutationFn: ({ slug, elementId, body }) => createEntry(slug, elementId, body),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["doc-elements", slug] });
    },
  });
}
