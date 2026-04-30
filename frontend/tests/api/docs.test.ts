import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { listDocs, listElements, getElement } from "../../src/api/docs";

const server = setupServer();

beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok-test");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
});

describe("docs api", () => {
  it("listDocs returns DocSummary array", async () => {
    server.use(
      http.get("http://localhost/api/docs", () =>
        HttpResponse.json([{ slug: "smoke-test-tragkorb", element_count: 9 }]),
      ),
    );
    const docs = await listDocs();
    expect(docs).toEqual([{ slug: "smoke-test-tragkorb", element_count: 9 }]);
  });

  it("listElements returns ElementWithCounts array for a slug", async () => {
    server.use(
      http.get(
        "http://localhost/api/docs/smoke-test-tragkorb/elements",
        () =>
          HttpResponse.json([
            {
              element: {
                element_id: "p1-aaa",
                page_number: 1,
                element_type: "heading",
                content: "Title",
              },
              count_active_entries: 0,
            },
          ]),
      ),
    );
    const elements = await listElements("smoke-test-tragkorb");
    expect(elements).toHaveLength(1);
    expect(elements[0].count_active_entries).toBe(0);
  });

  it("getElement returns element + entries", async () => {
    server.use(
      http.get(
        "http://localhost/api/docs/smoke-test-tragkorb/elements/p1-aaa",
        () =>
          HttpResponse.json({
            element: {
              element_id: "p1-aaa",
              page_number: 1,
              element_type: "heading",
              content: "Title",
            },
            entries: [],
          }),
      ),
    );
    const result = await getElement("smoke-test-tragkorb", "p1-aaa");
    expect(result.element.element_id).toBe("p1-aaa");
  });
});
