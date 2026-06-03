import { useParams } from "react-router-dom";

import { useAuth } from "../../auth/useAuth";
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

export function Statistics(): JSX.Element {
  const { slug = "" } = useParams<{ slug: string }>();
  const { token } = useAuth();
  const tokenStr = token ?? "";
  const extract = useExtractStats(slug, tokenStr);
  const synthese = useSyntheseStats(slug, tokenStr);
  const provenienz = useProvenienzStats(slug, tokenStr);
  const wishes = useCapabilityWishes(tokenStr);

  return (
    <div className="p-4 space-y-6">
      <section>
        <h2 className={`${T.cardTitle} text-navy-100 mb-3`}>Extrahieren</h2>
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
        <h2 className={`${T.cardTitle} text-navy-100 mb-3`}>Synthese</h2>
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
        <h2 className={`${T.cardTitle} text-navy-100 mb-3`}>Provenienz</h2>
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
  );
}
