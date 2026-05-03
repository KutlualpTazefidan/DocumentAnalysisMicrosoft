import { useMutation, useQueryClient } from "@tanstack/react-query";
import { refineQuestion } from "../api/curatorClient";
import type { CuratorQuestion, RefineQuestionBody } from "../api/curatorClient";

interface Args {
  slug: string;
  questionId: string;
  elementId: string;
  body: RefineQuestionBody;
}

export function useRefineEntry() {
  const qc = useQueryClient();
  return useMutation<CuratorQuestion, Error, Args>({
    mutationFn: ({ slug, questionId, body }) => refineQuestion(slug, questionId, body),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["curate", "element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["curate", "doc-elements", slug] });
    },
  });
}
