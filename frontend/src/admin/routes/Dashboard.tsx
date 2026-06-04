import { T } from "../styles/typography";

export function Dashboard() {
  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-2xl">
        <section className="card px-4 py-6">
          <h2 className="bam-title mb-2">Übersicht</h2>
          <p className={`${T.body} text-ink-muted`}>
            Diese Ansicht folgt in Kürze.
          </p>
        </section>
      </div>
    </div>
  );
}
