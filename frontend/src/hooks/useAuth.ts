import { useEffect, useState, useCallback } from "react";
import { clearToken, getToken, setToken as setStoredToken } from "../curator/api/curatorClient";

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken());

  useEffect(() => {
    function onLogout() {
      setTokenState(null);
    }
    window.addEventListener("goldens:logout", onLogout);
    return () => window.removeEventListener("goldens:logout", onLogout);
  }, []);

  const login = useCallback((newToken: string) => {
    setStoredToken(newToken);
    setTokenState(newToken);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    window.dispatchEvent(new Event("goldens:logout"));
  }, []);

  return { token, login, logout };
}
