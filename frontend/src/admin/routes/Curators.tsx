import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { createCurator, listCurators, revokeCurator } from "../api/docs";
import type { CuratorCreated } from "../types/domain";
import { T } from "../styles/typography";

interface Props {
  /** Override token for testing; in production the component reads it from useAuth(). */
  token?: string;
}

export function Curators({ token: tokenProp }: Props = {}): JSX.Element {
  const { token: authToken } = useAuth();
  const token = tokenProp ?? authToken ?? "";
  const qc = useQueryClient();
  const { success, error } = useToast();

  const curators = useQuery({
    queryKey: ["curators"],
    queryFn: () => listCurators(token),
    staleTime: 5_000,
  });

  // Create flow
  const [createOpen, setCreateOpen] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [createdRecord, setCreatedRecord] = useState<CuratorCreated | null>(null);
  const [tokenModalOpen, setTokenModalOpen] = useState(false);

  const createMut = useMutation({
    mutationFn: (name: string) => createCurator(name, token),
    onSuccess: (data) => {
      setCreateOpen(false);
      setNameInput("");
      setCreatedRecord(data);
      setTokenModalOpen(true);
      success(`Curator "${data.name}" created`);
    },
    onError: (err) => error(`create failed: ${(err as Error).message}`),
  });

  function handleCreateSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (nameInput.trim()) createMut.mutate(nameInput.trim());
  }

  function handleTokenDismiss() {
    setTokenModalOpen(false);
    setCreatedRecord(null);
    qc.invalidateQueries({ queryKey: ["curators"] });
  }

  // Revoke flow
  const revokeMut = useMutation({
    mutationFn: (id: string) => revokeCurator(id, token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["curators"] });
      success("Curator revoked");
    },
    onError: (err) => error(`revoke failed: ${(err as Error).message}`),
  });

  function handleRevoke(id: string, name: string) {
    if (window.confirm(`Revoke access for "${name}"? This cannot be undone.`)) {
      revokeMut.mutate(id);
    }
  }

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex items-center gap-3 mb-4">
        <h1 className={T.cardTitle}>Curators</h1>
        <button
          className={`ml-auto bg-blue-600 text-white px-3 py-1 rounded ${T.body}`}
          onClick={() => setCreateOpen(true)}
        >
          Create curator
        </button>
      </div>

      {/* List */}
      <table className={`w-full ${T.body}`}>
        <thead>
          <tr className="text-left border-b">
            <th className="p-2">Name</th>
            <th className="p-2">Token prefix</th>
            <th className="p-2">Created</th>
            <th className="p-2" />
          </tr>
        </thead>
        <tbody>
          {(curators.data ?? []).map((c) => (
            <tr key={c.id} className="border-b hover:bg-slate-50">
              <td className="p-2">{c.name}</td>
              <td className="p-2 font-mono">{c.token_prefix}</td>
              <td className="p-2 text-slate-500">{new Date(c.created_utc).toLocaleDateString()}</td>
              <td className="p-2 text-right">
                <button
                  className={`text-red-600 hover:underline ${T.body}`}
                  onClick={() => handleRevoke(c.id, c.name)}
                  disabled={revokeMut.isPending}
                >
                  Revoke
                </button>
              </td>
            </tr>
          ))}
          {curators.data?.length === 0 && (
            <tr>
              <td colSpan={4} className="p-4 text-center text-slate-400">No curators yet.</td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Create dialog */}
      <Dialog.Root open={createOpen} onOpenChange={setCreateOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded shadow-lg p-6 w-80">
            <Dialog.Title className={`${T.cardTitle} mb-4`}>Create curator</Dialog.Title>
            <form onSubmit={handleCreateSubmit} className="flex flex-col gap-3">
              <input
                className={`border rounded px-2 py-1 ${T.body}`}
                placeholder="Name"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <Dialog.Close asChild>
                  <button type="button" className={`px-3 py-1 rounded border ${T.body}`}>Cancel</button>
                </Dialog.Close>
                <button
                  type="submit"
                  className={`px-3 py-1 rounded bg-blue-600 text-white ${T.body}`}
                  disabled={createMut.isPending || !nameInput.trim()}
                >
                  Create
                </button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Token modal — shown once after creation (C16) */}
      <Dialog.Root open={tokenModalOpen} onOpenChange={(o) => { if (!o) handleTokenDismiss(); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded shadow-lg p-6 w-96">
            <Dialog.Title className={`${T.cardTitle} mb-2`}>Curator token</Dialog.Title>
            <p className={`${T.body} text-slate-600 mb-3`}>
              Copy this token now — it will not be shown again.
            </p>
            {createdRecord && (
              <div className="flex items-center gap-2 mb-4">
                <code className={`flex-1 bg-slate-100 rounded px-2 py-1 ${T.mono} break-all`}>
                  {createdRecord.token}
                </code>
                <button
                  className={`px-2 py-1 rounded border ${T.body}`}
                  onClick={() => navigator.clipboard.writeText(createdRecord.token)}
                >
                  Copy
                </button>
              </div>
            )}
            <div className="flex justify-end">
              <button
                className={`px-3 py-1 rounded bg-blue-600 text-white ${T.body}`}
                onClick={handleTokenDismiss}
              >
                Done
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
