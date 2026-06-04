import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";

import { apiBase, apiFetch } from "../api/adminClient";
import { StatusBadge } from "../components/StatusBadge";
import {
  CheckCircle2,
  Edit3,
  Plus,
  Trash2,
  X,
  XCircle,
} from "../../shared/icons";
import { useToast } from "../../shared/components/useToast";

interface Tenant {
  tenant_id: string;
  slug: string;
  name: string;
  created_at: string;
}

interface UserOut {
  user_id: string;
  tenant_id: string;
  username: string;
  pseudonym: string;
  role: string;
  active: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface CreateTenantBody {
  slug: string;
  name: string;
}

interface CreateUserBody {
  username: string;
  password: string;
  role: "admin" | "reviewer" | "curator";
  pseudonym?: string | null;
}

/**
 * Tenants + users admin page.
 *
 * Sidebar: tenant list — + button in the header opens a modal for
 * creating a new mandant; each row has edit/delete affordances.
 * Right column: when a tenant is selected — its users + a create-user
 * form (with pseudonym auto-suggest), deactivate button per user.
 *
 * Cookie-mode session-aware: every API call uses adminClient.apiFetch
 * which already sends credentials:'include'.
 */
export function TenantsAdmin(): JSX.Element {
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Tenant | null>(null);
  const { success, error } = useToast();
  const qc = useQueryClient();

  const del = useMutation<void, Error, Tenant>({
    mutationFn: async (t) => {
      const r = await apiFetch(`/api/admin/tenants/${encodeURIComponent(t.slug)}`, "", {
        method: "DELETE",
      });
      if (!r.ok && r.status !== 204) {
        const body = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(body.detail ?? `HTTP ${r.status}`);
      }
    },
    onSuccess: (_, t) => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      if (selectedSlug === t.slug) setSelectedSlug(null);
      success(`Fachbereich „${t.slug}" gelöscht`);
    },
    onError: (err) => error(`Löschen fehlgeschlagen: ${err.message}`),
  });

  function handleDelete(t: Tenant): void {
    const ok = window.confirm(
      `Fachbereich „${t.slug}" wirklich löschen? Alle Benutzer und Sessions werden mitgelöscht — Dateien unter data_root/tenants/${t.slug}/ bleiben auf der Platte.`,
    );
    if (!ok) return;
    del.mutate(t);
  }

  return (
    <div className="flex h-full">
      <aside className="w-80 border-r border-line p-4 flex flex-col gap-4 overflow-y-auto">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-bam-navy">Fachbereiche</h1>
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="p-1.5 rounded hover:bg-rowsel text-ink-muted"
            title="Neuen Fachbereich anlegen"
            aria-label="Neuen Fachbereich anlegen"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
        <TenantList
          selectedSlug={selectedSlug}
          onSelect={setSelectedSlug}
          onEdit={setEditing}
          onDelete={handleDelete}
        />
      </aside>
      <main className="flex-1 min-w-0 overflow-y-auto p-6">
        {selectedSlug ? (
          <TenantDetail slug={selectedSlug} />
        ) : (
          <p className="text-ink-muted italic">
            Fachbereich aus der Liste links wählen, um Benutzer zu sehen oder neue
            anzulegen.
          </p>
        )}
      </main>
      <CreateTenantModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(t) => {
          setSelectedSlug(t.slug);
          setCreateOpen(false);
        }}
      />
      <EditTenantModal
        tenant={editing}
        onClose={() => setEditing(null)}
      />
    </div>
  );
}

// ── Tenant list ───────────────────────────────────────────────────────

function TenantList({
  selectedSlug,
  onSelect,
  onEdit,
  onDelete,
}: {
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  onEdit: (t: Tenant) => void;
  onDelete: (t: Tenant) => void;
}): JSX.Element {
  const q = useQuery<{ tenants: Tenant[] }>({
    queryKey: ["tenants"],
    queryFn: async () => {
      // Token unused on cookie-mode; apiFetch tolerates an empty string.
      const r = await apiFetch(`/api/admin/tenants`, "");
      return r.json();
    },
  });
  const tenants = q.data?.tenants ?? [];

  // Auto-select when there's exactly one tenant and the user hasn't
  // picked anything yet — fixes the audit's "empty TenantsAdmin sends
  // the user nowhere" finding for the common single-tenant case.
  useEffect(() => {
    if (selectedSlug === null && tenants.length === 1) {
      onSelect(tenants[0]!.slug);
    }
  }, [selectedSlug, tenants, onSelect]);

  if (q.isLoading) return <p className="text-sm text-ink-muted">Lade…</p>;
  if (q.error)
    return (
      <p className="text-sm text-bam-red">
        Fehler: {(q.error as Error).message}
      </p>
    );
  if (tenants.length === 0) {
    return (
      <p className="text-sm text-ink-muted italic">
        Noch kein Fachbereich. Erst einen anlegen.
      </p>
    );
  }
  return (
    <ul className="space-y-1">
      {tenants.map((t) => {
        const active = t.slug === selectedSlug;
        return (
          <li
            key={t.tenant_id}
            className={`group relative rounded ${
              active ? "bg-rowsel" : "hover:bg-rowsel"
            }`}
          >
            <button
              type="button"
              onClick={() => onSelect(t.slug)}
              className={`w-full text-left px-3 py-2 pr-16 rounded text-sm ${
                active ? "text-bam-cyan font-semibold" : ""
              }`}
            >
              <div className="font-mono text-xs text-ink-muted">{t.slug}</div>
              <div>{t.name}</div>
            </button>
            <div
              className={`absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5 focus-within:opacity-100 ${
                active ? "opacity-100" : "opacity-0 group-hover:opacity-100"
              }`}
            >
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(t);
                }}
                className="p-1 rounded hover:bg-rowsel text-ink-muted"
                title={`Fachbereich „${t.slug}" bearbeiten`}
                aria-label={`Fachbereich ${t.slug} bearbeiten`}
              >
                <Edit3 className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(t);
                }}
                className="p-1 rounded hover:bg-bam-red/10 text-ink-muted hover:text-bam-red"
                title={`Fachbereich „${t.slug}" löschen`}
                aria-label={`Fachbereich ${t.slug} löschen`}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function CreateTenantModal({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onCreated: (t: Tenant) => void;
}): JSX.Element {
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  // Reset form state every time the modal opens — gives a clean slate
  // after a previous create or cancel.
  useEffect(() => {
    if (open) {
      setSlug("");
      setName("");
      setError(null);
    }
  }, [open]);

  const m = useMutation<Tenant, Error, CreateTenantBody>({
    mutationFn: async (body) => {
      const r = await apiFetch(`/api/admin/tenants`, "", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return r.json();
    },
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      onCreated(t);
    },
    onError: (err) => setError(err.message),
  });

  function handle(e: FormEvent): void {
    e.preventDefault();
    if (!slug.trim() || !name.trim()) return;
    m.mutate({ slug: slug.trim(), name: name.trim() });
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl p-6 w-full max-w-md z-50">
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-lg font-semibold text-bam-navy">
              Neuer Fachbereich
            </Dialog.Title>
            <Dialog.Close
              className="text-ink-muted hover:text-ink"
              aria-label="Schließen"
            >
              <X className="w-4 h-4" />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            Lege einen neuen Fachbereich an. Slug ist eine Kurz-ID; der
            Anzeigename erscheint in der Fachbereich-Liste.
          </Dialog.Description>
          <form onSubmit={handle} className="space-y-3">
            <label className="block">
              <span className="text-sm text-ink">Slug</span>
              <input
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="z.B. neue-firma"
                className="input mt-1"
                autoFocus
                aria-label="Slug"
              />
              <span className="text-xs text-ink-muted mt-1 block">
                Kurz-ID — Kleinbuchstaben, Zahlen, Bindestriche.
              </span>
            </label>
            <label className="block">
              <span className="text-sm text-ink">Anzeigename</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z.B. Neue Firma GmbH"
                className="input mt-1"
                aria-label="Anzeigename"
              />
            </label>
            {error && (
              <div role="alert" className="text-sm text-bam-red">
                {error}
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Dialog.Close className="btn-secondary text-sm">
                Abbrechen
              </Dialog.Close>
              <button
                type="submit"
                disabled={m.isPending || !slug.trim() || !name.trim()}
                className="btn-primary text-sm"
              >
                {m.isPending ? "Lege an…" : "Fachbereich anlegen"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function EditTenantModal({
  tenant,
  onClose,
}: {
  tenant: Tenant | null;
  onClose: () => void;
}): JSX.Element {
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const qc = useQueryClient();

  // Reset name from the passed tenant whenever the modal opens for a
  // different tenant (the parent passes null to close, an object to open).
  useEffect(() => {
    if (tenant) {
      setName(tenant.name);
      setErr(null);
    }
  }, [tenant]);

  const m = useMutation<Tenant, Error, { slug: string; name: string }>({
    mutationFn: async ({ slug, name }) => {
      const r = await apiFetch(`/api/admin/tenants/${encodeURIComponent(slug)}`, "", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(body.detail ?? `HTTP ${r.status}`);
      }
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      onClose();
    },
    onError: (e) => setErr(e.message),
  });

  function handle(e: FormEvent): void {
    e.preventDefault();
    if (!tenant || !name.trim()) return;
    m.mutate({ slug: tenant.slug, name: name.trim() });
  }

  return (
    <Dialog.Root
      open={tenant !== null}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl p-6 w-full max-w-md z-50">
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-lg font-semibold text-bam-navy">
              Fachbereich bearbeiten
            </Dialog.Title>
            <Dialog.Close
              className="text-ink-muted hover:text-ink"
              aria-label="Schließen"
            >
              <X className="w-4 h-4" />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            Anzeigename ändern. Die Slug-ID ist unveränderlich.
          </Dialog.Description>
          {tenant && (
            <form onSubmit={handle} className="space-y-3">
              <div>
                <span className="text-sm text-ink block">Slug</span>
                <code className="block mt-1 px-3 py-1.5 bg-rail rounded text-sm">
                  {tenant.slug}
                </code>
                <span className="text-xs text-ink-muted mt-1 block">
                  Unveränderlich — Slug partitioniert die Daten unter
                  data_root.
                </span>
              </div>
              <label className="block">
                <span className="text-sm text-ink">Anzeigename</span>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input mt-1"
                  autoFocus
                  aria-label="Anzeigename"
                />
              </label>
              {err && (
                <div role="alert" className="text-sm text-bam-red">
                  {err}
                </div>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <Dialog.Close className="btn-secondary text-sm">
                  Abbrechen
                </Dialog.Close>
                <button
                  type="submit"
                  disabled={
                    m.isPending || !name.trim() || name.trim() === tenant.name
                  }
                  className="btn-primary text-sm"
                >
                  {m.isPending ? "Speichere…" : "Speichern"}
                </button>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// ── Tenant detail ─────────────────────────────────────────────────────

function TenantDetail({ slug }: { slug: string }): JSX.Element {
  const q = useQuery<{ users: UserOut[] }>({
    queryKey: ["tenant-users", slug],
    queryFn: async () => {
      const r = await apiFetch(
        `/api/admin/tenants/${encodeURIComponent(slug)}/users`,
        "",
      );
      return r.json();
    },
  });
  return (
    <div className="space-y-6 max-w-3xl">
      <header>
        <h2 className="text-xl font-semibold text-bam-navy">
          Fachbereich{" "}
          <code className="text-base px-2 py-0.5 bg-rail rounded">
            {slug}
          </code>
        </h2>
      </header>

      <CreateUserForm slug={slug} />

      <section>
        <h3 className="text-base font-semibold mb-2 text-bam-navy">Benutzer</h3>
        {q.isLoading && <p className="text-sm text-ink-muted">Lade…</p>}
        {q.error && (
          <p className="text-sm text-bam-red">
            Fehler: {(q.error as Error).message}
          </p>
        )}
        <UserTable
          slug={slug}
          users={q.data?.users ?? []}
        />
      </section>
    </div>
  );
}

function UserTable({
  slug,
  users,
}: {
  slug: string;
  users: UserOut[];
}): JSX.Element {
  const qc = useQueryClient();
  const m = useMutation<void, Error, string>({
    mutationFn: async (userId) => {
      await apiFetch(
        `/api/admin/users/${encodeURIComponent(userId)}`,
        "",
        { method: "DELETE" },
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenant-users", slug] });
    },
  });
  if (users.length === 0) {
    return (
      <p className="text-sm text-ink-muted italic">
        Noch keine Benutzer in diesem Fachbereich.
      </p>
    );
  }
  return (
    <table className="w-full text-sm border border-line">
      <thead>
        <tr>
          <th className="bam-th">Benutzername</th>
          <th className="bam-th">Pseudonym</th>
          <th className="bam-th">Rolle</th>
          <th className="bam-th">Aktiv</th>
          <th className="bam-th">Letzte Anmeldung</th>
          <th className="bam-th">
            <span className="sr-only">Aktionen</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.user_id} className="bam-row">
            <td className="bam-td font-mono">{u.username}</td>
            <td className="bam-td">{u.pseudonym}</td>
            <td className="bam-td">{u.role}</td>
            <td className="bam-td">
              {u.active ? (
                <StatusBadge tone="success" label="aktiv" icon={CheckCircle2} />
              ) : (
                <StatusBadge tone="muted" label="deaktiviert" icon={XCircle} />
              )}
            </td>
            <td className="bam-td text-ink-muted text-xs">
              {u.last_login_at ?? "noch nie"}
            </td>
            <td className="bam-td">
              {u.active && (
                <button
                  type="button"
                  onClick={() => {
                    if (
                      window.confirm(
                        `Benutzer "${u.username}" deaktivieren? Sessions werden sofort verworfen.`,
                      )
                    ) {
                      m.mutate(u.user_id);
                    }
                  }}
                  className="btn-danger text-xs px-2 py-0.5"
                >
                  Deaktivieren
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CreateUserForm({ slug }: { slug: string }): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<CreateUserBody["role"]>("curator");
  const [pseudonym, setPseudonym] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  // Pseudonym suggest. Lazy: only fetches when the user clicks the
  // "Vorschlagen" button so we don't spam the endpoint on every render.
  const suggest = useMutation<{ pseudonym: string }, Error, void>({
    mutationFn: async () => {
      const r = await fetch(
        `${apiBase()}/api/admin/tenants/${encodeURIComponent(slug)}/pseudonym-suggest`,
        { credentials: "include" },
      );
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
    onSuccess: (data) => setPseudonym(data.pseudonym),
  });

  const create = useMutation<UserOut, Error, CreateUserBody>({
    mutationFn: async (body) => {
      const r = await apiFetch(
        `/api/admin/tenants/${encodeURIComponent(slug)}/users`,
        "",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenant-users", slug] });
      setUsername("");
      setPassword("");
      setPseudonym("");
      setError(null);
    },
    onError: (err) => setError(err.message),
  });

  function handle(e: FormEvent): void {
    e.preventDefault();
    if (!username.trim() || !password) return;
    create.mutate({
      username: username.trim(),
      password,
      role,
      pseudonym: pseudonym.trim() || null,
    });
  }

  return (
    <form
      onSubmit={handle}
      className="card p-4 space-y-3"
    >
      <h3 className="text-base font-semibold text-bam-navy">Neuer Benutzer</h3>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-xs text-ink-muted">Benutzername</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="input text-sm w-full mt-0.5"
            autoComplete="username"
          />
        </label>
        <label className="block">
          <span className="text-xs text-ink-muted">Passwort</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input text-sm w-full mt-0.5"
            autoComplete="new-password"
          />
        </label>
        <label className="block">
          <span className="text-xs text-ink-muted">Rolle</span>
          <select
            value={role}
            onChange={(e) =>
              setRole(e.target.value as CreateUserBody["role"])
            }
            className="input text-sm w-full mt-0.5"
          >
            <option value="curator">curator</option>
            <option value="reviewer">reviewer</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-ink-muted">
            Pseudonym (leer = wird beim Anlegen automatisch erzeugt)
          </span>
          <div className="flex gap-1 mt-0.5">
            <input
              type="text"
              value={pseudonym}
              onChange={(e) => setPseudonym(e.target.value)}
              className="input text-sm flex-1"
              placeholder="z.B. Wachsamer Hirsch"
            />
            <button
              type="button"
              onClick={() => suggest.mutate()}
              disabled={suggest.isPending}
              className="text-xs px-2 py-1 border border-line2 rounded hover:bg-rowsel"
              title="Server schlägt ein freies Pseudonym vor (Adjektiv + Tier)"
            >
              {suggest.isPending ? "…" : "Vorschlagen"}
            </button>
          </div>
        </label>
      </div>
      {error && <div className="text-xs text-bam-red">{error}</div>}
      <button
        type="submit"
        disabled={create.isPending || !username.trim() || !password}
        className="btn-primary text-sm"
      >
        {create.isPending ? "Lege an…" : "Benutzer anlegen"}
      </button>
    </form>
  );
}
