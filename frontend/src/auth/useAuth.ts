import { useEffect, useState, useCallback } from "react";

import { logoutSession, whoAmI } from "./api";

const TOKEN_KEY = "goldens.api_token";
const ROLE_KEY = "goldens.role";
const NAME_KEY = "goldens.name";
const TENANT_KEY = "goldens.tenant_slug";

export type Role = "admin" | "curator" | null;

export function useAuth() {
  const [token, setToken] = useState<string | null>(sessionStorage.getItem(TOKEN_KEY));
  const [role, setRole] = useState<Role>((sessionStorage.getItem(ROLE_KEY) as Role) ?? null);
  const [name, setName] = useState<string | null>(sessionStorage.getItem(NAME_KEY));
  const [tenantSlug, setTenantSlug] = useState<string | null>(
    sessionStorage.getItem(TENANT_KEY),
  );

  useEffect(() => {
    const fn = (): void => {
      setToken(null);
      setRole(null);
      setName(null);
      setTenantSlug(null);
    };
    window.addEventListener("goldens:logout", fn);
    return () => window.removeEventListener("goldens:logout", fn);
  }, []);

  // Page-refresh recovery: if no sessionStorage state but a valid
  // server-side cookie exists, restore identity transparently. Runs
  // once per mount and silently ignores 401 (no active session).
  useEffect(() => {
    if (role && name) return;
    let cancelled = false;
    void whoAmI()
      .then((ident) => {
        if (cancelled) return;
        sessionStorage.setItem(TOKEN_KEY, "");
        sessionStorage.setItem(ROLE_KEY, ident.role);
        sessionStorage.setItem(NAME_KEY, ident.pseudonym);
        if (ident.tenant_slug) {
          sessionStorage.setItem(TENANT_KEY, ident.tenant_slug);
        }
        setToken("");
        setRole(ident.role as Role);
        setName(ident.pseudonym);
        setTenantSlug(ident.tenant_slug);
      })
      .catch(() => {
        /* no active session → stay logged out */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    (t: string, r: Role, n: string, tenant?: string | null) => {
      sessionStorage.setItem(TOKEN_KEY, t);
      sessionStorage.setItem(ROLE_KEY, r ?? "");
      sessionStorage.setItem(NAME_KEY, n);
      if (tenant) sessionStorage.setItem(TENANT_KEY, tenant);
      else sessionStorage.removeItem(TENANT_KEY);
      setToken(t);
      setRole(r);
      setName(n);
      setTenantSlug(tenant ?? null);
    },
    [],
  );

  const logout = useCallback(() => {
    // Best-effort revoke of the server-side session cookie. Fire-and-
    // forget so logout UX never blocks on a network round-trip.
    void logoutSession().catch(() => {});
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(ROLE_KEY);
    sessionStorage.removeItem(NAME_KEY);
    sessionStorage.removeItem(TENANT_KEY);
    setToken(null);
    setRole(null);
    setName(null);
    setTenantSlug(null);
    window.dispatchEvent(new Event("goldens:logout"));
  }, []);

  return { token, role, name, tenantSlug, login, logout };
}
