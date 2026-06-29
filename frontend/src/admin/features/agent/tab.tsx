import { Bot } from "lucide-react";
import { Agent } from "../../routes/Agent";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "agent", label: "Agent", icon: Bot,
  order: 5, requiresFile: true, Component: Agent,
};
export default descriptor;
