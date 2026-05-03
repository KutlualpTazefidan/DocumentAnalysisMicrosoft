import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { apiFetch, ApiError } from "../../../src/curator/api/curatorClient";

const server = setupServer();

beforeEach(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  server.close();
});

describe("apiFetch", () => {
  it("includes X-Auth-Token header from sessionStorage", async () => {
    sessionStorage.setItem("goldens.api_token", "tok-test");
    server.use(
      http.get("http://localhost/api/health", ({ request }) => {
        expect(request.headers.get("X-Auth-Token")).toBe("tok-test");
        return HttpResponse.json({ status: "ok", goldens_root: "outputs" });
      }),
    );
    const result = await apiFetch<{ status: string }>("/api/health");
    expect(result.status).toBe("ok");
  });

  it("throws ApiError with detail on non-ok response", async () => {
    sessionStorage.setItem("goldens.api_token", "tok-test");
    server.use(
      http.get("http://localhost/api/entries/missing", () =>
        HttpResponse.json({ detail: "entry not found" }, { status: 404 }),
      ),
    );
    await expect(apiFetch("/api/entries/missing")).rejects.toMatchObject({
      status: 404,
      detail: "entry not found",
    });
  });

  it("clears token and dispatches a logout event on 401", async () => {
    sessionStorage.setItem("goldens.api_token", "tok-old");
    const onLogout = vi.fn();
    window.addEventListener("goldens:logout", onLogout);
    server.use(
      http.get("http://localhost/api/anything", () =>
        HttpResponse.json({ detail: "invalid token" }, { status: 401 }),
      ),
    );
    await expect(apiFetch("/api/anything")).rejects.toBeInstanceOf(ApiError);
    expect(sessionStorage.getItem("goldens.api_token")).toBeNull();
    expect(onLogout).toHaveBeenCalled();
    window.removeEventListener("goldens:logout", onLogout);
  });
});
