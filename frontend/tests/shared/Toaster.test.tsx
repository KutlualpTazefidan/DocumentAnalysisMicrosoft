import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toaster, ToastProvider } from "../../src/shared/components/Toaster";
import { useToast } from "../../src/shared/components/useToast";

function Demo() {
  const { success } = useToast();
  return <button onClick={() => success("hello")}>fire</button>;
}

describe("Toaster", () => {
  it("shows toast text on fire", async () => {
    render(<ToastProvider><Demo /><Toaster /></ToastProvider>);
    await userEvent.click(screen.getByText("fire"));
    expect(await screen.findByText("hello")).toBeInTheDocument();
  });
});
