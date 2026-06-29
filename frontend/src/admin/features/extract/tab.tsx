import { FileText } from "lucide-react";
import { Extract } from "../../routes/extract";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "extract", label: "Extrahieren", icon: FileText,
  order: 1, requiresFile: true, Component: Extract,
};
export default descriptor;
