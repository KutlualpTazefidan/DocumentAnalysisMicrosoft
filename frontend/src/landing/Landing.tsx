import { Link } from "react-router-dom";
import { FileSearch, Sparkles, Workflow } from "../shared/icons";

interface Feature {
  icon: typeof FileSearch;
  title: string;
  body: string;
}

const FEATURES: Feature[] = [
  {
    icon: FileSearch,
    title: "PDF-Datenextraktion",
    body:
      "KI-gestützte Erfassung von Tabellen, Diagrammen und Fließtext aus technischen PDFs — strukturiert, nachvollziehbar.",
  },
  {
    icon: Sparkles,
    title: "Q&A-Generierung",
    body:
      "Aus extrahierten Inhalten entstehen Frage-Antwort-Paare für Engineering-Aufgaben und Wissensprüfungen.",
  },
  {
    icon: Workflow,
    title: "Digitales Abbild",
    body:
      "Ingenieurprozesse werden als nachverfolgbare Provenienz-Graphen abgebildet — Entscheidungen bleiben prüfbar.",
  },
];

export function Landing() {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <main className="flex-1 flex items-center">
        <div className="w-full max-w-5xl mx-auto px-6 py-16">
          <section className="text-center space-y-6 mb-20">
            <h1 className="text-6xl font-bold tracking-tight text-navy-800">
              GOLDENS
            </h1>
            <p className="text-lg text-slate-600 max-w-2xl mx-auto">
              KI-gestützte Datenextraktion und digitale Abbilder für
              Engineering-Workflows.
            </p>
            <div className="pt-2">
              <Link
                to="/login"
                className="btn-primary inline-flex items-center px-8 py-3 text-base"
              >
                Anmelden
              </Link>
            </div>
          </section>

          <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <article
                key={title}
                className="bg-white border border-slate-200 rounded-lg p-6 space-y-3 hover:border-brand-500 transition-colors"
              >
                <Icon className="w-8 h-8 text-brand-500" aria-hidden />
                <h2 className="text-lg font-semibold text-slate-900">
                  {title}
                </h2>
                <p className="text-sm text-slate-600 leading-relaxed">{body}</p>
              </article>
            ))}
          </section>
        </div>
      </main>
      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-500">
        GOLDENS — interne Anwendung. Audit-Logs verwenden Pseudonyme.
      </footer>
    </div>
  );
}
