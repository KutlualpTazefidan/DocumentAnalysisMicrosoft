import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiBase, apiFetch } from "../api/adminClient";

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
 * Left column: list of tenants + create-tenant form.
 * Right column: when a tenant is selected — list of its users + a
 * create-user form (with pseudonym auto-suggest), deactivate button.
 *
 * Cookie-mode session-aware: every API call uses adminClient.apiFetch
 * which already sends credentials:'include'.
 */
export function TenantsAdmin(): JSX.Element {
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);

  return (
    <div className="flex h-full">
      <aside className="w-80 border-r border-slate-200 bg-slate-50 p-4 flex flex-col gap-4 overflow-y-auto">
        <h1 className="text-lg font-semibold">Tenants</h1>
        <TenantList
          selectedSlug={selectedSlug}
          onSelect={setSelectedSlug}
        />
        <CreateTenantForm
          onCreated={(t) => setSelectedSlug(t.slug)}
        />
      </aside>
      <main className="flex-1 min-w-0 overflow-y-auto p-6">
        {selectedSlug ? (
          <TenantDetail slug={selectedSlug} />
        ) : (
          <p className="text-slate-500 italic">
            Tenant aus der Liste links wählen, um Benutzer zu sehen oder neue
            anzulegen.
          </p>
        )}
      </main>
    </div>
  );
}

// ── Tenant list ───────────────────────────────────────────────────────

function TenantList({
  selectedSlug,
  onSelect,
}: {
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
}): JSX.Element {
  const q = useQuery<{ tenants: Tenant[] }>({
    queryKey: ["tenants"],
    queryFn: async () => {
      // Token unused on cookie-mode; apiFetch tolerates an empty string.
      const r = await apiFetch(`/api/admin/tenants`, "");
      return r.json();
    },
  });
  if (q.isLoading) return <p className="text-sm text-slate-500">Lade…</p>;
  if (q.error)
    return (
      <p className="text-sm text-red-600">
        Fehler: {(q.error as Error).message}
      </p>
    );
  const tenants = q.data?.tenants ?? [];
  if (tenants.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">
        Noch kein Tenant. Erst einen anlegen.
      </p>
    );
  }
  return (
    <ul className="space-y-1">
      {tenants.map((t) => (
        <li key={t.tenant_id}>
          <button
            type="button"
            onClick={() => onSelect(t.slug)}
            className={`w-full text-left px-3 py-2 rounded text-sm ${
              t.slug === selectedSlug
                ? "bg-blue-100 text-blue-900 font-semibold"
                : "hover:bg-slate-200"
            }`}
          >
            <div className="font-mono text-xs text-slate-600">{t.slug}</div>
            <div>{t.name}</div>
          </button>
        </li>
      ))}
    </ul>
  );
}

function CreateTenantForm({
  onCreated,
}: {
  onCreated: (t: Tenant) => void;
}): JSX.Element {
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();
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
      setSlug("");
      setName("");
      setError(null);
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
    <form
      onSubmit={handle}
      className="border-t border-slate-200 pt-4 space-y-2"
    >
      <h2 className="text-sm font-semibold">Neuer Tenant</h2>
      <input
        type="text"
        value={slug}
        onChange={(e) => setSlug(e.target.value)}
        placeholder="slug (a-z 0-9 -)"
        className="input text-sm w-full"
      />
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Name"
        className="input text-sm w-full"
      />
      {error && <div className="text-xs text-red-600">{error}</div>}
      <button
        type="submit"
        disabled={m.isPending || !slug.trim() || !name.trim()}
        className="btn-primary w-full text-sm"
      >
        {m.isPending ? "Lege an…" : "Anlegen"}
      </button>
    </form>
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
        <h2 className="text-xl font-semibold">
          Tenant{" "}
          <code className="text-base px-2 py-0.5 bg-slate-100 rounded">
            {slug}
          </code>
        </h2>
      </header>

      <CreateUserForm slug={slug} />

      <section>
        <h3 className="text-base font-semibold mb-2">Benutzer</h3>
        {q.isLoading && <p className="text-sm text-slate-500">Lade…</p>}
        {q.error && (
          <p className="text-sm text-red-600">
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
      <p className="text-sm text-slate-500 italic">
        Noch keine Benutzer in diesem Tenant.
      </p>
    );
  }
  return (
    <table className="w-full text-sm border border-slate-200">
      <thead className="bg-slate-50 text-slate-600">
        <tr>
          <th className="text-left px-3 py-2">Username</th>
          <th className="text-left px-3 py-2">Pseudonym</th>
          <th className="text-left px-3 py-2">Rolle</th>
          <th className="text-left px-3 py-2">Aktiv</th>
          <th className="text-left px-3 py-2">Letzter Login</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.user_id} className="border-t border-slate-200">
            <td className="px-3 py-2 font-mono">{u.username}</td>
            <td className="px-3 py-2">{u.pseudonym}</td>
            <td className="px-3 py-2">{u.role}</td>
            <td className="px-3 py-2">
              {u.active ? (
                <span className="text-emerald-700">aktiv</span>
              ) : (
                <span className="text-slate-500">deaktiviert</span>
              )}
            </td>
            <td className="px-3 py-2 text-slate-500 text-xs">
              {u.last_login_at ?? "noch nie"}
            </td>
            <td className="px-3 py-2">
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
                  className="text-rose-600 hover:underline text-xs"
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
      className="bg-slate-50 border border-slate-200 rounded p-4 space-y-3"
    >
      <h3 className="text-base font-semibold">Neuer Benutzer</h3>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-xs text-slate-600">Username</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="input text-sm w-full mt-0.5"
            autoComplete="username"
          />
        </label>
        <label className="block">
          <span className="text-xs text-slate-600">Passwort</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input text-sm w-full mt-0.5"
            autoComplete="new-password"
          />
        </label>
        <label className="block">
          <span className="text-xs text-slate-600">Rolle</span>
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
          <span className="text-xs text-slate-600">
            Pseudonym (leer = auto)
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
              className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-100"
              title="Pseudonym vom Server vorschlagen lassen"
            >
              ↻
            </button>
          </div>
        </label>
      </div>
      {error && <div className="text-xs text-red-600">{error}</div>}
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
