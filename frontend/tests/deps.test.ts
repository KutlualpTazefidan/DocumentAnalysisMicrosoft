import { describe, it, expect } from "vitest";
import pkg from "../package.json";

describe("Phase A.1.0 deps", () => {
  it.each([
    "lucide-react",
    "framer-motion",
    "@radix-ui/react-dialog",
    "@radix-ui/react-dropdown-menu",
    "@radix-ui/react-toast",
    "@radix-ui/react-tabs",
    "clsx",
  ])("%s installed", (name) => {
    expect((pkg.dependencies as Record<string, string>)[name]).toBeDefined();
  });
});
