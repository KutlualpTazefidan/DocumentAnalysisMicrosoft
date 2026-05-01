import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createBox, deleteBox, getSegments, mergeBoxes, splitBox, updateBox } from "../api/docs";
import type { BoxKind, SegmentBox, SegmentsFile } from "../types/domain";

export function useSegments(slug: string, token: string) {
  return useQuery({ queryKey: ["segments", slug], queryFn: () => getSegments(slug, token) });
}

export function useUpdateBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ boxId, patch }: { boxId: string; patch: { kind?: BoxKind; bbox?: [number, number, number, number] } }) =>
      updateBox(slug, boxId, patch, token),
    onSuccess: (updated: SegmentBox) => {
      qc.setQueryData<SegmentsFile>(["segments", slug], (prev) => {
        if (!prev) return prev;
        return { ...prev, boxes: prev.boxes.map((b) => (b.box_id === updated.box_id ? updated : b)) };
      });
    },
  });
}

export function useMergeBoxes(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => mergeBoxes(slug, ids, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}

export function useSplitBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ boxId, splitY }: { boxId: string; splitY: number }) => splitBox(slug, boxId, splitY, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}

export function useCreateBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ page, bbox, kind }: { page: number; bbox: [number, number, number, number]; kind: BoxKind }) =>
      createBox(slug, page, bbox, kind, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}

export function useDeleteBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (boxId: string) => deleteBox(slug, boxId, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}
