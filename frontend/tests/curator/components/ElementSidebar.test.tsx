import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { ElementSidebar } from "../../../src/curator/components/ElementSidebar";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function renderSidebar(props: { slug: string; activeElementId?: string; onSelect?: (id: string) => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ElementSidebar
          slug={props.slug}
          activeElementId={props.activeElementId}
          onSelect={props.onSelect ?? (() => {})}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ElementSidebar", () => {
  it("renders one row per element with type and page", async () => {
    server.use(
      http.get("http://localhost/api/curate/docs/foo/elements", () =>
        HttpResponse.json([
          {
            element_id: "p1-aaa",
            page_number: 1,
            element_type: "heading",
            content: "Title",
          },
          {
            element_id: "p2-bbb",
            page_number: 2,
            element_type: "table",
            content: "x | y",
            table_dims: [4, 3],
          },
        ]),
      ),
    );
    renderSidebar({ slug: "foo" });
    expect(await screen.findByText("Title")).toBeInTheDocument();
    expect(screen.getByText("x | y")).toBeInTheDocument();
    expect(screen.getByText(/p\.1/)).toBeInTheDocument();
    expect(screen.getByText(/p\.2/)).toBeInTheDocument();
  });

  it("highlights the active element", async () => {
    server.use(
      http.get("http://localhost/api/curate/docs/foo/elements", () =>
        HttpResponse.json([
          {
            element_id: "p1-aaa",
            page_number: 1,
            element_type: "heading",
            content: "Active",
          },
        ]),
      ),
    );
    renderSidebar({ slug: "foo", activeElementId: "p1-aaa" });
    const item = await screen.findByRole("button", { name: /active/i });
    expect(item).toHaveAttribute("aria-current", "true");
  });

  it("calls onSelect with element_id on click", async () => {
    const events: string[] = [];
    server.use(
      http.get("http://localhost/api/curate/docs/foo/elements", () =>
        HttpResponse.json([
          {
            element_id: "p3-ccc",
            page_number: 3,
            element_type: "paragraph",
            content: "Some text",
          },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderSidebar({ slug: "foo", onSelect: (id) => events.push(id) });
    const item = await screen.findByRole("button", { name: /some text/i });
    await user.click(item);
    expect(events).toEqual(["p3-ccc"]);
  });
});
