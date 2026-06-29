import { Bot } from "lucide-react";
import { Agent } from "../../routes/Agent";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "agent", label: "Agent", icon: Bot,
  order: 5, requiresFile: true, // gated behind a selected file for UX consistency; the agent endpoints are document-agnostic
  Component: Agent,
};
export default descriptor;
