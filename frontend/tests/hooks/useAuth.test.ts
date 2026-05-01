import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAuth } from "../../src/hooks/useAuth";
import { setToken } from "../../src/curator/api/curatorClient";

describe("useAuth", () => {
  beforeEach(() => sessionStorage.clear());

  it("returns null when no token", () => {
    const { result } = renderHook(() => useAuth());
    expect(result.current.token).toBeNull();
  });

  it("returns the token when stored", () => {
    setToken("tok-abc");
    const { result } = renderHook(() => useAuth());
    expect(result.current.token).toBe("tok-abc");
  });

  it("logout() clears token + dispatches goldens:logout event", () => {
    setToken("tok-abc");
    const { result } = renderHook(() => useAuth());
    act(() => result.current.logout());
    expect(sessionStorage.getItem("goldens.api_token")).toBeNull();
  });

  it("re-reads token on goldens:logout event", () => {
    setToken("tok-abc");
    const { result } = renderHook(() => useAuth());
    expect(result.current.token).toBe("tok-abc");
    act(() => {
      sessionStorage.removeItem("goldens.api_token");
      window.dispatchEvent(new Event("goldens:logout"));
    });
    expect(result.current.token).toBeNull();
  });
});
