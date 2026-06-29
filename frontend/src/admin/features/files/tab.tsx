import { Folder } from "lucide-react";
import { Inbox } from "../../routes/inbox";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "files",
  label: "Dateien",
  icon: Folder,
  order: 0,
  requiresFile: false,
  Component: Inbox,
};
export default descriptor;
