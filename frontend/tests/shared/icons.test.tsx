import { describe, it, expect } from "vitest";
import * as icons from "../../src/shared/icons";

describe("shared/icons re-exports", () => {
  it.each(["Inbox", "Users", "BarChart3", "Cpu", "LogOut", "Plus", "Trash2", "Edit3", "Save", "Play", "RefreshCcw", "CheckCircle2", "XCircle", "Clock", "AlertTriangle", "Circle"])(
    "%s exported", (name) => {
      expect((icons as Record<string, unknown>)[name]).toBeDefined();
    },
  );
});
