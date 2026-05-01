import { useEffect, useState, useCallback } from "react";

const TOKEN_KEY = "goldens.api_token";
const ROLE_KEY = "goldens.role";
const NAME_KEY = "goldens.name";

export type Role = "admin" | "curator" | null;

export function useAuth() {
  const [token, setToken] = useState<string | null>(sessionStorage.getItem(TOKEN_KEY));
  const [role, setRole] = useState<Role>((sessionStorage.getItem(ROLE_KEY) as Role) ?? null);
  const [name, setName] = useState<string | null>(sessionStorage.getItem(NAME_KEY));

  useEffect(() => {
    const fn = () => { setToken(null); setRole(null); setName(null); };
    window.addEventListener("goldens:logout", fn);
    return () => window.removeEventListener("goldens:logout", fn);
  }, []);

  const login = useCallback((t: string, r: Role, n: string) => {
    sessionStorage.setItem(TOKEN_KEY, t);
    sessionStorage.setItem(ROLE_KEY, r ?? "");
    sessionStorage.setItem(NAME_KEY, n);
    setToken(t); setRole(r); setName(n);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(ROLE_KEY);
    sessionStorage.removeItem(NAME_KEY);
    setToken(null); setRole(null); setName(null);
    window.dispatchEvent(new Event("goldens:logout"));
  }, []);

  return { token, role, name, login, logout };
}
