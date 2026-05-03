import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deprecateQuestion } from "../api/curatorClient";
import type { CuratorQuestion, DeprecateQuestionBody } from "../api/curatorClient";

interface Args {
  slug: string;
  questionId: string;
  elementId: string;
  body: DeprecateQuestionBody;
}

export function useDeprecateEntry() {
  const qc = useQueryClient();
  return useMutation<CuratorQuestion, Error, Args>({
    mutationFn: ({ slug, questionId, body }) => deprecateQuestion(slug, questionId, body),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["curate", "element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["curate", "doc-elements", slug] });
    },
  });
}
