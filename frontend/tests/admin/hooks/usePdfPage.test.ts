// frontend/tests/local-pdf/hooks/usePdfPage.test.ts
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePdfPage } from "../../../src/admin/hooks/usePdfPage";

vi.mock("pdfjs-dist/build/pdf.mjs", () => ({
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 3,
      getPage: vi.fn(async (_pageNumber: number) => ({
        getViewport: ({ scale }: { scale: number }) => ({ width: 100 * scale, height: 200 * scale }),
        render: vi.fn(() => ({ promise: Promise.resolve() })),
      })),
    }),
  })),
  GlobalWorkerOptions: { workerSrc: "" },
}));

describe("usePdfPage", () => {
  it("loads document and exposes numPages + viewport", async () => {
    const { result } = renderHook(() => usePdfPage("/api/docs/x/source.pdf", "tok", 1, 1.5));
    await waitFor(() => expect(result.current.numPages).toBe(3));
    expect(result.current.viewport).toEqual({ width: 150, height: 300 });
  });
});
