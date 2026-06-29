import { GitMerge } from "lucide-react";
import { Provenienz } from "../../routes/Provenienz";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "provenienz", label: "Provenienz", icon: GitMerge,
  order: 4, requiresFile: true, Component: Provenienz,
};
export default descriptor;
