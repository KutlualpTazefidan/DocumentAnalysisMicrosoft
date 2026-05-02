import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteDoc, listDocs, publishDoc, uploadDoc } from "../api/docs";

export function useDocs(token: string) {
  return useQuery({ queryKey: ["docs"], queryFn: () => listDocs(token), staleTime: 5_000 });
}

export function useUploadDoc(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadDoc(file, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs"] }),
  });
}

export function usePublishDoc(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => publishDoc(slug, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs"] }),
  });
}

export function useDeleteDoc(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => deleteDoc(slug, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs"] }),
  });
}
