import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { FileSearch, Sparkles, Workflow, X } from "../shared/icons";
import { LoginForm } from "../auth/LoginForm";

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
  const [loginOpen, setLoginOpen] = useState(false);

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      <main className="flex-1 flex items-center">
        <div className="w-full max-w-5xl mx-auto px-6 py-16">
          <section className="text-center space-y-6 mb-20">
            <img
              src="/brand/bam-logo.png"
              alt="BAM"
              className="h-12 w-auto mx-auto mb-2"
            />
            <h1 className="text-6xl font-bold uppercase tracking-[0.1em] text-bam-navy">
              Goldens
            </h1>
            <p className="text-lg text-ink-muted max-w-2xl mx-auto">
              KI-gestützte Datenextraktion und digitale Abbilder für
              Engineering-Workflows.
            </p>
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setLoginOpen(true)}
                className="btn-primary inline-flex items-center px-8 py-3 text-base"
              >
                Anmelden
              </button>
            </div>
          </section>

          <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <article
                key={title}
                className="card p-6 space-y-3 hover:border-bam-cyan transition-colors"
              >
                <Icon className="w-8 h-8 text-bam-cyan" aria-hidden />
                <h2 className="text-lg font-semibold text-bam-navy">{title}</h2>
                <p className="text-sm text-ink-muted leading-relaxed">{body}</p>
              </article>
            ))}
          </section>
        </div>
      </main>
      <footer className="border-t border-line py-6 text-center text-xs text-ink-muted">
        GOLDENS — interne Anwendung. Audit-Logs verwenden Pseudonyme.
      </footer>

      <Dialog.Root open={loginOpen} onOpenChange={setLoginOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/50 z-40" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg shadow-xl p-8 w-full max-w-sm z-50">
            <Dialog.Close
              className="absolute right-3 top-3 p-1 text-ink-muted hover:text-bam-navy"
              aria-label="Schließen"
            >
              <X className="w-4 h-4" />
            </Dialog.Close>
            <div className="flex flex-col items-center gap-3 mb-5">
              <img src="/brand/bam-logo.png" alt="BAM" className="h-9 w-auto" />
              <Dialog.Title className="text-lg font-bold uppercase tracking-[0.18em] text-bam-navy">
                Goldens
              </Dialog.Title>
            </div>
            <Dialog.Description className="sr-only">
              Mit Fachbereich, Benutzername und Passwort anmelden. Schließen mit
              Escape.
            </Dialog.Description>
            <LoginForm onSuccess={() => setLoginOpen(false)} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
