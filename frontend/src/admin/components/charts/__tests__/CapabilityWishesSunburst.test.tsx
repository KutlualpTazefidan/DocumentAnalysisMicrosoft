// frontend/src/admin/components/charts/__tests__/CapabilityWishesSunburst.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CapabilityWishesSunburst } from "../CapabilityWishesSunburst";

describe("CapabilityWishesSunburst", () => {
  it("renders empty-state when wishes is empty", () => {
    render(<CapabilityWishesSunburst wishes={[]} />);
    expect(screen.getByText("Noch keine Wünsche")).toBeInTheDocument();
  });

  it("renders heading when wishes are present", () => {
    render(
      <CapabilityWishesSunburst
        wishes={[
          { name: "RegisterLookup", count: 3, by_actor: { human: 0, agent: 3 }, skill_bucket: "register" },
        ]}
      />
    );
    expect(screen.getByText(/Capability-Wünsche/)).toBeInTheDocument();
  });
});
