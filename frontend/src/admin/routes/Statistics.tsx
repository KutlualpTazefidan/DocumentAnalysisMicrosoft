import { useParams } from "react-router-dom";

import { useAuth } from "../../auth/useAuth";
import { DocStepTabs } from "../components/DocStepTabs";
import { CapabilityWishesSunburst } from "../components/charts/CapabilityWishesSunburst";
import { DiagnosticBar } from "../components/charts/DiagnosticBar";
import { MetricCounter } from "../components/charts/MetricCounter";
import { MetricGauge } from "../components/charts/MetricGauge";
import { VoteDistributionBar } from "../components/charts/VoteDistributionBar";
import {
  useCapabilityWishes,
  useExtractStats,
  useProvenienzStats,
  useSyntheseStats,
} from "../hooks/useStatistics";
import { T } from "../styles/typography";

function SectionStatus({
  isLoading,
  isError,
}: {
  isLoading: boolean;
  isError: boolean;
}): JSX.Element | null {
  if (isLoading) {
    return <div className="text-ink-muted text-sm">Lädt…</div>;
  }
  if (isError) {
    return <div className="text-ink-muted text-sm">Konnte nicht laden</div>;
  }
  return null;
}

export function Statistics(): JSX.Element {
  const { slug = "" } = useParams<{ slug: string }>();
  const { token } = useAuth();
  const tokenStr = token ?? "";
  const extract = useExtractStats(slug, tokenStr);
  const synthese = useSyntheseStats(slug, tokenStr);
  const provenienz = useProvenienzStats(slug, tokenStr);
  const wishes = useCapabilityWishes(tokenStr);

  if (token === null) {
    return <div className="p-6 text-ink">Bitte zuerst anmelden.</div>;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-4 py-2 bg-white flex-shrink-0">
        <DocStepTabs slug={slug} />
      </div>

      <div className="p-4 space-y-6">
        <section>
          <h2 className={`${T.cardTitle} text-bam-navy mb-3`}>Extrahieren</h2>
          <SectionStatus isLoading={extract.isLoading} isError={extract.isError} />
          {extract.data && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <DiagnosticBar data={extract.data.diagnostics} />
              <MetricCounter
                value={extract.data.register_boxes}
                label="Register-Boxen"
                suffix={`/ ${extract.data.total_boxes}`}
              />
            </div>
          )}
        </section>

        <section>
          <h2 className={`${T.cardTitle} text-bam-navy mb-3`}>Synthese</h2>
          <SectionStatus isLoading={synthese.isLoading} isError={synthese.isError} />
          {synthese.data && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <MetricGauge
                  value={synthese.data.survival_rate}
                  label="Curator-Überleben"
                  subtitle={`${synthese.data.questions_created - synthese.data.questions_deprecated} / ${synthese.data.questions_created}`}
                />
                <MetricGauge
                  value={synthese.data.vote_approval_rate}
                  label="Reviewer-Zustimmung"
                  subtitle={`${synthese.data.vote_approved} / ${synthese.data.vote_approved + synthese.data.vote_rejected}`}
                />
              </div>
              <VoteDistributionBar rows={synthese.data.vote_distribution} />
            </div>
          )}
        </section>

        <section>
          <h2 className={`${T.cardTitle} text-bam-navy mb-3`}>Provenienz</h2>
          <SectionStatus
            isLoading={provenienz.isLoading || wishes.isLoading}
            isError={provenienz.isError || wishes.isError}
          />
          {provenienz.data && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MetricGauge
                value={provenienz.data.correction_rate}
                label="Experten-Korrekturen"
                subtitle={`${provenienz.data.expert_overrides} / ${provenienz.data.plan_proposals}`}
              />
            </div>
          )}
          {wishes.data && <CapabilityWishesSunburst wishes={wishes.data.wishes} />}
        </section>
      </div>
    </div>
  );
}
