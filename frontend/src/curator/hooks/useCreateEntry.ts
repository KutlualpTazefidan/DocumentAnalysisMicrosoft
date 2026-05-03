import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postQuestion, getToken } from "../api/curatorClient";
import type { PostedQuestion } from "../api/curatorClient";

interface CreateArgs {
  slug: string;
  elementId: string;
  body: { query: string };
}

export function useCreateEntry() {
  const qc = useQueryClient();
  return useMutation<PostedQuestion, Error, CreateArgs>({
    mutationFn: ({ slug, elementId, body }) =>
      postQuestion(slug, { element_id: elementId, query: body.query }, getToken()!),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["curate", "element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["curate", "doc-elements", slug] });
    },
  });
}
