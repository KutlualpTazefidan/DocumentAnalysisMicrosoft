import { Sparkles } from "lucide-react";
import { Synthesise } from "../../routes/Synthesise";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "synthesise", label: "Synthese", icon: Sparkles,
  order: 2, requiresFile: true, Component: Synthesise,
};
export default descriptor;
