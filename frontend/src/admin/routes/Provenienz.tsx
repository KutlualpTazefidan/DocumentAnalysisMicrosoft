import { useParams } from "react-router-dom";

import { useAuth } from "../../auth/useAuth";
import { DocStepTabs } from "../components/DocStepTabs";

export function Provenienz(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const { token } = useAuth();
  if (!token) {
    return (
      <div className="p-6 text-slate-300">
        Bitte zuerst anmelden.
      </div>
    );
  }
  return (
    <div className="flex flex-col h-full bg-navy-900">
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white border-b border-navy-700">
        <DocStepTabs slug={slug} />
      </div>
      <div className="flex-1 flex items-center justify-center text-slate-400 italic">
        Provenienz — Skeleton (Sessions-Liste folgt in 7.2)
      </div>
    </div>
  );
}
