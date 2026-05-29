import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getPageStatus, setPageStatus } from "../api/docs";

export interface PageStatusData {
  slug: string;
  done_pages: number[];
}

/** GET the server-backed set of "done" (abgeschlossen) pages for a doc.
 *  placeholderData keeps the grid rendering with an empty done-set while
 *  the first request is in flight — no spinner, no flash. */
export function usePageStatus(slug: string, token: string) {
  return useQuery({
    queryKey: ["pageStatus", slug],
    queryFn: () => getPageStatus(slug, token),
    placeholderData: { slug, done_pages: [] } as PageStatusData,
  });
}

/** PATCH a single page's status. Optimistic: the done_pages cache is
 *  updated immediately (page added on "done", removed otherwise) so the
 *  button colour / lock state flip without waiting for the round-trip;
 *  rolled back on error and reconciled with the server onSettled. */
export function useSetPageStatus(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ page, status }: { page: number; status: "done" | "not_started" | "in_progress" }) =>
      setPageStatus(slug, page, status, token),
    onMutate: async ({ page, status }) => {
      await qc.cancelQueries({ queryKey: ["pageStatus", slug] });
      const previous = qc.getQueryData<PageStatusData>(["pageStatus", slug]);
      qc.setQueryData<PageStatusData>(["pageStatus", slug], (prev) => {
        const base: PageStatusData = prev ?? { slug, done_pages: [] };
        const next = new Set(base.done_pages);
        if (status === "done") {
          next.add(page);
        } else {
          next.delete(page);
        }
        return { ...base, done_pages: [...next].sort((a, b) => a - b) };
      });
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous !== undefined) {
        qc.setQueryData(["pageStatus", slug], ctx.previous);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["pageStatus", slug] });
    },
  });
}
