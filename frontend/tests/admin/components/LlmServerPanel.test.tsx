import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { LlmServerPanel } from "../../../src/admin/components/LlmServerPanel";

/**
 * LlmServerPanel — Start/Stop button + status pill for the local vLLM
 * subprocess. Tests cover initial render with each state and that the
 * Start button posts to /api/admin/llm/start.
 */

const server = setupServer();
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return (
    <QueryClientProvider client={qc}>
      <LlmServerPanel token="tok" />
    </QueryClientProvider>
  );
}

describe("LlmServerPanel", () => {
  it("renders Stopped pill when backend reports stopped", async () => {
    server.use(
      http.get("*/api/admin/llm/status", () =>
        HttpResponse.json({
          state: "stopped",
          pid: null,
          model: "Qwen/Qwen2.5-3B-Instruct",
          base_url: "http://127.0.0.1:8000/v1",
          healthy: false,
          error: null,
          log_tail: [],
          vllm_cli_available: true,
        }),
      ),
    );
    render(wrap());
    expect(
      await screen.findByText("Qwen/Qwen2.5-3B-Instruct"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("llm-state-pill")).toHaveTextContent("Gestoppt");
  });

  it("Start button is enabled when stopped, disabled when running", async () => {
    server.use(
      http.get("*/api/admin/llm/status", () =>
        HttpResponse.json({
          state: "running",
          pid: 1234,
          model: "Qwen/Qwen2.5-3B-Instruct",
          base_url: "http://127.0.0.1:8000/v1",
          healthy: true,
          error: null,
          log_tail: ["INFO: Started server"],
          vllm_cli_available: true,
        }),
      ),
    );
    render(wrap());
    await waitFor(() =>
      expect(screen.getByTestId("llm-state-pill")).toHaveTextContent("Laeuft"),
    );
    expect(screen.getByRole("button", { name: /vllm starten/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /vllm stoppen/i })).not.toBeDisabled();
  });

  it("Start button POSTs /api/admin/llm/start", async () => {
    let startCalled = false;
    server.use(
      http.get("*/api/admin/llm/status", () =>
        HttpResponse.json({
          state: "stopped",
          pid: null,
          model: "Qwen/Qwen2.5-3B-Instruct",
          base_url: "http://127.0.0.1:8000/v1",
          healthy: false,
          error: null,
          log_tail: [],
          vllm_cli_available: true,
        }),
      ),
      http.post("*/api/admin/llm/start", () => {
        startCalled = true;
        return HttpResponse.json({
          state: "starting",
          pid: 1234,
          model: "Qwen/Qwen2.5-3B-Instruct",
          base_url: "http://127.0.0.1:8000/v1",
          healthy: false,
          error: null,
          log_tail: [],
          vllm_cli_available: true,
        });
      }),
    );
    render(wrap());
    await waitFor(() => expect(screen.getByTestId("llm-state-pill")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /vllm starten/i }));
    await waitFor(() => expect(startCalled).toBe(true));
  });

  it("error state shows the error message and auto-expands logs", async () => {
    server.use(
      http.get("*/api/admin/llm/status", () =>
        HttpResponse.json({
          state: "error",
          pid: null,
          model: "Qwen/Qwen2.5-3B-Instruct",
          base_url: "http://127.0.0.1:8000/v1",
          healthy: false,
          error: "vllm exited with code 137",
          log_tail: ["CUDA OOM", "exit 137"],
          vllm_cli_available: true,
        }),
      ),
    );
    render(wrap());
    await waitFor(() =>
      expect(screen.getByTestId("llm-state-pill")).toHaveTextContent("Fehler"),
    );
    expect(screen.getByText(/vllm exited with code 137/)).toBeInTheDocument();
    // Logs auto-expanded on error.
    expect(screen.getByText(/CUDA OOM/)).toBeInTheDocument();
  });

  it("warns when vllm CLI is not on PATH", async () => {
    server.use(
      http.get("*/api/admin/llm/status", () =>
        HttpResponse.json({
          state: "stopped",
          pid: null,
          model: "Qwen/Qwen2.5-3B-Instruct",
          base_url: "http://127.0.0.1:8000/v1",
          healthy: false,
          error: null,
          log_tail: [],
          vllm_cli_available: false,
        }),
      ),
    );
    render(wrap());
    await waitFor(() =>
      expect(screen.getByText(/vllm-server\/README\.md/)).toBeInTheDocument(),
    );
  });
});
