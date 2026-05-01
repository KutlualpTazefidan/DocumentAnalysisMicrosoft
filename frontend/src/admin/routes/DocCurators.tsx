import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { assignCurator, listCurators, listDocCurators, unassignCurator } from "../api/docs";
import type { CuratorRecord } from "../types/domain";

interface Props {
  /** Override token for testing; in production the component reads it from useAuth(). */
  token?: string;
}

export function DocCurators({ token: tokenProp }: Props = {}): JSX.Element {
  const { token: authToken } = useAuth();
  const token = tokenProp ?? authToken ?? "";
  const { slug = "" } = useParams<{ slug: string }>();
  const qc = useQueryClient();
  const { success, error } = useToast();

  const allCuratorsQuery = useQuery<CuratorRecord[]>({
    queryKey: ["curators"],
    queryFn: () => listCurators(token),
    staleTime: 5_000,
  });

  const docCuratorsQuery = useQuery<CuratorRecord[]>({
    queryKey: ["doc-curators", slug],
    queryFn: () => listDocCurators(slug, token),
    staleTime: 5_000,
    enabled: !!slug,
  });

  const assignedIds = new Set((docCuratorsQuery.data ?? []).map((c) => c.id));

  const assignMut = useMutation({
    mutationFn: (curatorId: string) => assignCurator(slug, curatorId, token),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["doc-curators", slug] });
      success(`Assigned "${data.name}"`);
    },
    onError: (err) => error(`assign failed: ${(err as Error).message}`),
  });

  const unassignMut = useMutation({
    mutationFn: (curatorId: string) => unassignCurator(slug, curatorId, token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["doc-curators", slug] });
      success("Unassigned curator");
    },
    onError: (err) => error(`unassign failed: ${(err as Error).message}`),
  });

  return (
    <div className="p-6 h-full overflow-auto">
      <h1 className="text-xl font-semibold mb-6">Curators for doc: {slug}</h1>

      <div className="flex gap-8">
        {/* Left pane: all curators — click to assign */}
        <div className="flex-1">
          <h2 className="text-sm font-semibold text-slate-500 uppercase mb-2">All curators</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b">
                <th className="p-2">Name</th>
                <th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {(allCuratorsQuery.data ?? []).map((c) => (
                <tr key={c.id} className="border-b hover:bg-slate-50">
                  <td className="p-2">{c.name}</td>
                  <td className="p-2 text-right">
                    {!assignedIds.has(c.id) && (
                      <button
                        className="text-blue-600 hover:underline text-xs"
                        onClick={() => assignMut.mutate(c.id)}
                        disabled={assignMut.isPending}
                        aria-label={`assign ${c.name}`}
                      >
                        + assign
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {allCuratorsQuery.data?.length === 0 && (
                <tr>
                  <td colSpan={2} className="p-4 text-center text-slate-400">No curators yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Right pane: doc's assigned curators */}
        <div className="flex-1">
          <h2 className="text-sm font-semibold text-slate-500 uppercase mb-2">Assigned to this doc</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b">
                <th className="p-2">Name</th>
                <th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {(docCuratorsQuery.data ?? []).map((c) => (
                <tr key={c.id} className="border-b hover:bg-slate-50">
                  <td className="p-2">{c.name}</td>
                  <td className="p-2 text-right">
                    <button
                      className="text-red-600 hover:underline text-xs"
                      onClick={() => unassignMut.mutate(c.id)}
                      disabled={unassignMut.isPending}
                      aria-label={`unassign ${c.name}`}
                    >
                      × unassign
                    </button>
                  </td>
                </tr>
              ))}
              {docCuratorsQuery.data?.length === 0 && (
                <tr>
                  <td colSpan={2} className="p-4 text-center text-slate-400">No curators assigned.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
