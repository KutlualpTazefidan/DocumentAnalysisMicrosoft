# Phasenübersicht — Goldset-System

> **Letzte Aktualisierung:** 2026-05-03 (A.1.0 Coherence + Roles + Extract-Pipeline-Hardening als PR offen — bündelt Admin/Curator-Shells, role-prefixed Backend-Routes, VLM-getriebenen Extract-Pfad mit Per-Sub-Block-Boxen, MathML-Rendering, Aux-Row-Layout, Footnote-Heuristiken, Segment-Route-Entfernung. Davor: A.0 Local PDF Pipeline via PR #26 + Model-Lifecycle/Progress via PR #27. Phase A: A.0 → A.8 + A-Plus.1/.2 alle merged. Phase B/C/D als nächstes.)
> **Detail-Specs:** [`docs/superpowers/specs/`](superpowers/specs/) — vollständige Design-Dokumente pro Phase
> **Pläne:** [`docs/superpowers/plans/`](superpowers/plans/) — granulare Implementations-Pläne

Dieses Dokument ist die **Kurzfassung** für schnelles Nachschlagen: was jede Phase ist, warum sie existiert, wie sie benutzt wird. Detaillierte Begründungen stehen in den verlinkten Specs.

## Was wird hier gebaut?

Ein **Goldset-System mit Evaluierung** für die Microsoft-Azure-Search-Index-Kollaboration.

- **Goldset** = kuratierte Liste von Fragen, bei denen wir genau wissen, welche Chunks die richtige Antwort enthalten.
- **Evaluierung** = wir lassen den Index die Fragen beantworten und messen, wie oft er die erwarteten Chunks liefert.
- **System** = Speicherung, Erstellung, Pflege und Auswertung der Goldsets, plus eine pipeline-agnostische Architektur, damit dieselben Goldsets gegen verschiedene Suchsysteme evaluiert werden können.

## Architektur — vier Schichten

```
features/
├── core/                       Basis-Infrastruktur (LLM-Clients)
├── goldens/                    Datenmodell + Speicherung der Goldsets
├── pipelines/microsoft/        Das aktuelle Suchsystem (Azure)
└── evaluators/chunk_match/     Bewertungslogik (Recall@k etc.)
```

**Abhängigkeiten fließen nach unten**: `evaluators` benutzt `goldens` und `pipelines`. `goldens` benutzt nur `core`. Keine Rückkanten.

## Glossar — wichtige Begriffe

| Begriff | Was es ist | Beispiel-ID |
|---|---|---|
| **Quell-Dokument** | Eine PDF-Datei in unserer Sammlung — z.B. ein technisches Handbuch | `tragkorb-b-147-2001-rev-1.pdf` |
| **Element** | Strukturelle Einheit eines Quell-Dokuments — Absatz, Überschrift, Tabelle, Bild, Listenelement. Aus Document Intelligence. **Pipeline-unabhängig** | `p47-p4` (Seite 47, vierter Absatz) |
| **Chunk** | Pipeline-spezifische Gruppierung mehrerer Elemente, die zusammen indexiert werden. Verschiedene Pipelines bilden unterschiedliche Chunks aus denselben Elementen. **Pipeline-spezifisch** | `B7-12` (in unserem Microsoft-Index) |
| **Test-Frage** (Goldset-Eintrag, `RetrievalEntry`) | Eine kuratierte Frage mit Bezug auf das Element, aus dem sie entstand | `Frage 42: "Wo steht die maximale Zugkraft für M6?"` |
| **Source-Element** einer Test-Frage | Das Element, das die Antwort enthält. Pipeline-unabhängiger Wahrheits-Anker | Frage 42 → `source_element = p47-p4` |
| **Signal** | User-Feedback im Frontend: "einverstanden" (positiv) oder "disqualifizieren" (negativ, mit Pflicht-Notiz) auf eine Test-Frage oder ein Element | Bob klickt "einverstanden" auf Frage 42 |
| **Match-Typ** | Beziehung zwischen zurückgegebenem Pipeline-Material und Source-Element der Frage: EXACT, CONTAINED, CONTAINS, OVERLAP, MISS | Pipeline gibt nur p47-p4 zurück → CONTAINED |

**Kernregel:** die Wahrheit lebt auf **Element-Ebene** (Pipeline-unabhängig). Chunks sind nur Verpackung. Eine präzisere Pipeline (CONTAINED-Match) wird **nicht bestraft**, weil sie das gefragte Element findet ohne Drumherum-Rauschen.

## Status-Übersicht

| Phase | Modul | Status | PR | Detail-Spec |
|---|---|---|---|---|
| A.0 | `pipelines/local-pdf/` (DocLayout-YOLO + MinerU 3 + visual review UI) | ✅ merged | [#26](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/26) + [#27](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/27) (model lifecycle + progress UI follow-up) | [local-pdf-pipeline-design.md](superpowers/specs/2026-04-30-local-pdf-pipeline-design.md), [model-lifecycle-and-progress-design.md](superpowers/specs/2026-05-01-a-0-model-lifecycle-and-progress-design.md) |
| A.1 | `core/llm_clients/` | ✅ merged | [#7](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/7) | [a1-llm-clients-design.md](superpowers/specs/2026-04-28-a1-llm-clients-design.md) |
| A.2 | `goldens/schemas/` | ✅ merged | [#8](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/8) | [a2-goldens-schemas-design.md](superpowers/specs/2026-04-28-a2-goldens-schemas-design.md) |
| A.3 | `goldens/storage/` | ✅ merged | [#9](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/9) | [a3-goldens-storage-design.md](superpowers/specs/2026-04-29-a3-goldens-storage-design.md) |
| A.3.1 | `goldens/schemas/` — `SourceElement` additiv | ✅ merged | [#12](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/12) | (Mini-PR; Begründung in `project_evaluation_ground_truth.md`-Memory) |
| A.4 | `goldens/creation/curate.py` | ✅ merged | [#14](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/14) | [a4-curate-design.md](superpowers/specs/2026-04-29-a4-curate-design.md), [plan](superpowers/plans/2026-04-29-a4-curate.md) |
| A.5 | `goldens/creation/synthetic.py` | ✅ merged | [#13](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/13) | [a5-synthetic-design.md](superpowers/specs/2026-04-29-a5-synthetic-design.md), [plan](superpowers/plans/2026-04-29-a5-synthetic.md) |
| A.6 | `goldens/operations/` | ✅ merged | [#10](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/10) | (Spec/Plan im Branch committed) |
| A.7 | `evaluators/chunk_match/` Rewire | ✅ merged | [#11](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/11) | [a7-chunk-match-rewire-design.md](superpowers/specs/2026-04-29-a7-chunk-match-rewire-design.md) |
| A.8 | Pydantic v2 core migration (prerequisite for A-Plus) | ✅ merged | [#22](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/22) | [pydantic-core-migration-design.md](superpowers/specs/2026-04-30-pydantic-core-migration-design.md), [plan](superpowers/plans/2026-04-30-pydantic-core-migration.md) |
| A-Plus.1 | `goldens/api/` (FastAPI backend) | ✅ merged | [#24](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/24) | [a-plus-1-backend-design.md](superpowers/specs/2026-04-30-a-plus-1-backend-design.md), [plan](superpowers/plans/2026-04-30-a-plus-1-backend.md) |
| A-Plus.2 | `frontend/` (React SPA) | ✅ merged | [#25](https://github.com/KutlualpTazefidan/DocumentAnalysisMicrosoft/pull/25) | [a-plus-2-frontend-design.md](superpowers/specs/2026-04-30-a-plus-2-frontend-design.md), [plan](superpowers/plans/2026-04-30-a-plus-2-frontend.md) |
| A.1.0 | Coherence + roles + UI polish + extract-pipeline hardening (admin/curator shells, role-prefixed routes, MinerU VLM-driven extract, MathML, footnote heuristics, segment-route removal) | 🚧 PR open | (TBD) | [coherence-and-roles-design.md](superpowers/specs/2026-05-01-coherence-and-roles-design.md) |
| B | Answer-Quality + LLM-Judge | 📅 später | — | (in Restructure-Spec §7 skizziert) |
| C | Klassifikation + Multi-Agent | 📅 später | — | (in Restructure-Spec §7 skizziert) |
| D | User-Signale auf Chunks und Test-Fragen | 💭 Idee, Brainstorming offen | — | (Skizze unten) |
| E | Pipeline-agnostische Bewertung (`span_match`) | 💭 Idee, Brainstorming offen | — | (Skizze unten) |
| F | Query-Decomposition-Agent | 💭 Idee, Brainstorming offen | — | (Skizze unten) |

**Status-Legende:** ✅ merged · 🚧 in Arbeit · ⏳ geplant (Phase A) · 📅 später (geplant, Spec steht) · 💭 Idee (Brainstorming offen)

## Per Phase — was, warum, wie

### Phase A.1 — `core/llm_clients/` ✅

**Was:** Eine einheitliche Schnittstelle für vier LLM-Anbieter (Azure OpenAI, OpenAI direkt, Anthropic, Ollama lokal). Egal welcher Anbieter dahinter steht, der Aufruf sieht gleich aus: `client.complete(messages, model="gpt-4o")`.

**Warum:** Spätere Phasen brauchen LLMs (A.5 für Synthese, B für Quality-Judge). Eine einheitliche Schicht macht Anbieter-Wechsel trivial und Anbieter-Mix möglich (z.B. Azure für Embeddings, Anthropic für Bewertung).

**Wie:** `from llm_clients import AzureOpenAIClient, AzureOpenAIConfig` → Config aus Env-Vars laden → Client instanziieren → `complete()` oder `embed()` aufrufen. Tenacity-Retry bei 429/5xx ist eingebaut.

---

### Phase A.2 — `goldens/schemas/` ✅

**Was:** Die Datentypen. `RetrievalEntry` = eine kuratierte Frage + erwartete Chunk-IDs + Reviewer-Kette. `Event` = eine rohe Aktion ("Eintrag erstellt", "Review hinzugefügt", "Eintrag verworfen"). `HumanActor` und `LLMActor` für Provenienz (wer hat was gemacht).

**Warum:** Klare Typen ergeben klare APIs. Provenienz ist wichtig für die Microsoft-Kollaboration: ein Expert-Sign-off zählt mehr als ein LLM-Vorschlag — das muss im System sichtbar sein.

**Wie:** `from goldens import RetrievalEntry, Event, HumanActor, LLMActor`. Frozen Dataclasses, alle haben `to_dict()`/`from_dict()` für JSON. Validierung in `__post_init__` (ISO-Timestamps, nicht-leere IDs etc.).

---

### Phase A.3 — `goldens/storage/` ✅

**Was:** Wo Goldsets auf Festplatte landen. Eine **JSONL-Datei pro Goldset, append-only** — jede Aktion ist eine Zeile. Drumherum: Lese-/Schreibfunktionen mit `fcntl`-Datei-Locking (damit parallele Prozesse nicht durcheinander schreiben), plus Idempotenz (gleiche `event_id` zweimal = ein Eintrag).

**Warum:** Append-only ist einfach, konfliktfrei, auditierbar. Aus dem Event-Log wird per "Projektion" der aktuelle Zustand rekonstruiert (welche Einträge sind aktiv, welche deprecated, was ist die aktuelle Version nach refines).

**Wie:**
- `append_event(path, event)` schreibt eine Zeile (idempotent + locked)
- `read_events(path)` liest alle Events
- `build_state(events)` reduziert zum aktuellen Zustand
- `iter_active_retrieval_entries(path)` ist die kanonische Komposition für Evaluatoren — read + project + filter active

---

### Phase A.4 — `goldens/creation/curate.py` ⏳

**Was:** Eine interaktive CLI: `query-eval curate`. Zeigt dir **ein einzelnes Element** aus dem Quell-Dokument (typisch ein Absatz, optional Tabelle/Bild/Überschrift) und fragt: *"Welche Frage(n) beantwortet dieser Absatz?"*

```
Tragkorb-Handbuch, Seite 47, Absatz 4 (Element-ID: p47-p4)
─────────────────────────────────────
"Die maximale Zugkraft für M6-Verschraubungen liegt
 bei 8.5 kN gemäß DIN 912."

Welche Frage(n) beantwortet dieser Absatz?
[ Frage: Wo steht die maximale Zugkraft für M6? ]

[ Speichern ]    [ Weiter ]
```

**Wichtige Konventionen** (entschieden im Brainstorming 2026-04-29):

- **Element-basiert, nicht Chunk-basiert.** Du siehst einen Absatz, keinen Microsoft-Chunk. Der Absatz ist pipeline-unabhängig (kommt aus Document Intelligence), Chunks sind Microsoft-spezifische Gruppierungen.
- **Single-Element pro Frage als Default.** Schreib Fragen, die durch genau diesen Absatz allein beantwortbar sind. Wenn die Antwort Information aus Nachbar-Absätzen bräuchte → Frage NICHT hier schreiben, "Weiter" klicken.
- **"Weiter" statt "Skip", keine Skip-Metadaten.** Das System speichert nur Fragen, die du aktiv schreibst und speicherst. Kein *"Alice ist hier vorbeigegangen"*-Tracking.
- **Vergleichs-/Multi-Step-Fragen werden NICHT hier kuratiert.** Die kommen zur Laufzeit über **Phase F** (Query-Decomposition-Agent), der sie in Single-Element-Sub-Fragen zerlegt.

**Warum:** Manuelle Goldset-Erstellung mit Mensch-Hirn ist der Goldstandard. Mensch versteht Domäne, sieht Nuancen, formuliert natürlich. Element-basierter Anker macht das Goldset pipeline-unabhängig — dieselbe Test-Frage kann gegen Microsoft, gegen eine zukünftige Custom-Pipeline, gegen verschiedene Indexierungs-Strategien evaluiert werden. Wird der **erste Konsument, der echte Daten produziert** — A.1-A.3 sind Infrastruktur ohne Daten.

**Wie:** `query-eval curate --doc <slug>` öffnet die CLI, navigiert durch Elemente des Dokuments (Absatz für Absatz), du tippst Fragen wo natürlich, klickst "Weiter" wo nichts passt. Eintrag landet als Event im Log unter `outputs/<slug>/datasets/golden_events_v1.jsonl`. Identität (Pseudonym + Level) wird beim ersten Aufruf einmalig konfiguriert und in `~/.config/goldens/identity.toml` gespeichert.

**Datenmodell-Erweiterung:** Phase A.2's `RetrievalEntry` wird beim A.4-Bauen additiv um `source_element: SourceElement` erweitert (singular — ein Element pro Frage). Bestehende Felder (`expected_chunk_ids` etc.) bleiben unverändert; sie werden weiter für Phase A.7's chunk-id-basierte Bewertung genutzt.

---

### Phase A.5 — `goldens/creation/synthetic.py` ⏳

**Was:** Automatische Goldset-Generierung durch LLM. Du gibst dem System einen oder mehrere Chunks, es lässt das LLM 3–5 Fragen pro Chunk vorschlagen, alles landet als `created`-Events mit Action `"synthesised"` und einem `LLMActor`.

**Warum:** Mensch-Kuration skaliert nicht (~10 Einträge pro Tag mühsam). LLM macht 1000 in 10 Minuten. Mensch wird vom **Erfinder zum Reviewer** ("akzeptieren/ablehnen/verfeinern" statt "von Null formulieren") — drastisch effizienter.

**Wie:** `query-eval synthesise --doc <slug> --n 100` — LLM produziert N Vorschläge. Mensch reviewt sie später (in der späteren Web-UI A-Plus, oder per CLI über A.6 Operations).

---

### Phase A.6 — `goldens/operations/` ✅

**Was:** Admin- und Kuratoren-Operationen auf bestehenden Einträgen — zwei Funktionen:

- `refine(old_entry_id, neue_query, neue_chunks, ...)` — Kurator korrigiert eine Frage: legt neue Version an mit Pointer auf alte; alte wird automatisch zurückgezogen
- `deprecate(entry_id, reason)` — Admin zieht eine Frage zurück, ohne Ersatz

**Warum:** Goldset-**Pflege** ist eine eigene Disziplin neben **Erstellung** (A.4/A.5). Wenn Alice merkt, dass die erwarteten Chunks einer Frage falsch sind, ruft sie `refine` auf. Wenn ein Admin eine Frage wegen Disqualifizierungs-Häufung (Phase D) loswerden will, ruft er `deprecate`. Ohne diese Operationen kann das System keine Lebenszyklen verwalten.

**Wie:** `from goldens.operations import refine, deprecate`. Jede Funktion **validiert** zuerst (existiert der Eintrag? nicht schon zurückgezogen?) und wirft `EntryNotFoundError` oder `EntryDeprecatedError` bei Verstoß. Bei `refine`: zwei Aktionen (neue Frage anlegen + alte zurückziehen) werden atomar in einem Schreibvorgang ausgeführt.

**Was bewusst NICHT in A.6 ist:** ein `add_review`-Pfad mit "approved"/"rejected"-Aktionen. Das wäre formales Reviewer-Sign-off — entschieden gegen am 2026-04-29 ("Welt 1": niemand approved formal, User signalisieren stattdessen einverstanden/disqualifizieren über Frontend in Phase D).

---

### Phase A.7 — `evaluators/chunk_match/` Rewire ✅

**Was chunk_match ist (unverändert von A.7):**

`chunk_match` ist **der Evaluator**, der die Suchqualität in Zahlen ausdrückt. Pro Goldset-Frage:

1. ruft `hybrid_search(frage, top_k=20)` auf der Microsoft-Pipeline auf
2. bekommt eine Liste der **Top-K-Chunks** zurück, sortiert nach Score
3. prüft, ob der **erwartete Chunk** unter den Top-K ist und an welcher Position
4. aggregiert über alle Fragen: **Recall@5**, **Recall@10**, **Recall@20**, **MAP**, **MRR**, **Hit-Rate@1**
5. produziert einen **MetricsReport** als JSON-Datei (z.B. für Drift-Tracking über Zeit)

**Was A.7 ändert (nur die Datenquelle):**

Vorher las der Evaluator das **alte `EvalExample`-JSONL** (Phase-0-Format, ein Beispiel pro Zeile, hand-genummerierte IDs wie `g0001`).

Nachher liest er das **Event-Log via `iter_active_retrieval_entries(path)`** (A.3-Storage). Die Goldsets kommen jetzt projiziert aus dem Append-only-Event-Log statt direkt aus einer EvalExample-Datei.

**Was gleich bleibt:**

- Die Eval-Logik selbst (Top-K-Vergleich)
- Die Metriken (Recall@k, MRR etc.)
- Der `hybrid_search`-Aufruf
- Das Report-Format (bis auf den Feld-Rename `query_id` → `entry_id`)
- Das CLI-Interface: `query-eval eval --doc <slug>` läuft für den Nutzer genauso wie vorher

**Warum:** Der Evaluator ist der **letzte Konsument**, der noch das alte EvalExample-Format liest. Nach A.7 redet die ganze Codebasis konsistent über `RetrievalEntry`. Außerdem wird das alte `EvalExample` und `datasets.py` in derselben PR gelöscht — kein Doppelvokabular mehr.

**Begleitende Aufräumarbeiten in derselben PR:**
- `query_id` → `entry_id` Rename in `QueryRecord` und `RunMetadata` (das neue Vokabular)
- `filter`-Feld pro Beispiel entfernt (war Microsoft-OData-spezifisch, niemand nutzte es)
- `EvalExample`, `datasets.py`, alte Tests gelöscht
- `DEFAULT_REPORTS_DIR` von altem Phase-0-Pfad auf `outputs/reports` umgestellt

---

## Was nach Phase A kommt

### Phase A-Plus — HTTP-API + Frontend 📅

**Was:** FastAPI-Backend (`goldens/api/`) + Browser-Frontend. Backend wrappt A.4-A.6-Operationen als HTTP-Endpoints. Frontend zeigt eine **element-zentrische UI**, die Curate und Review **in einer einzigen Sicht** kombiniert.

**Kombiniertes Curate+Review-UI** (Brainstorming-Ergebnis 2026-04-29):

```
User öffnet Element p47-p4 im Browser:
  ┌──────────────────────────────────────────────────────────┐
  │  Tragkorb-Handbuch, Seite 47, Absatz 4                   │
  │  ─────────────────────────────────────────────           │
  │  "Die maximale Zugkraft für M6-Verschraubungen liegt     │
  │   bei 8.5 kN gemäß DIN 912."                             │
  │                                                          │
  │  Diesen Absatz: [ einverstanden ] [ disqualifizieren ]   │
  │                                                          │
  │  Schon vorhandene Test-Fragen zu diesem Absatz:          │
  │  ─────────────────────────────────────                   │
  │  Frage 42: "Wo steht die maximale Zugkraft für M6?"      │
  │            [ einverstanden ] [ disqualifizieren ]        │
  │  Frage 87: "Welche Norm definiert die Zugkraft für M6?"  │
  │            [ einverstanden ] [ disqualifizieren ]        │
  │                                                          │
  │  Eigene neue Frage zu diesem Absatz hinzufügen:          │
  │  [ neue Frage tippen... ]              [ Speichern ]     │
  │                                                          │
  │                                          [ Weiter ]      │
  └──────────────────────────────────────────────────────────┘
```

In einer Session kann der User **sowohl bewerten als auch erstellen**:
- Klick auf einverstanden/disqualifizieren bei Frage 42 → User-Signal (Phase D)
- Tippt eine neue Frage darunter → Curate-Aktion (analog A.4)
- Klick auf Element-disqualifizieren → Element-Feedback (Phase D)
- Klick "Weiter" → nächstes Element, kein Eintrag

**Warum:** CLI ist gut für dich als Solo-Developer. Für Microsoft-Kollaboratoren (~20 Reviewer) ist Browser-UI nötig — sie sollen nicht CLI lernen müssen. Die **Vereinheitlichung von Curate und Review** entspricht der natürlichen Reviewer-Sicht: man arbeitet sich durch ein Dokument, sieht Absatz für Absatz, und macht spontan was passt — bewerten, ergänzen, weiterklicken.

**Datenmodell trägt das schon:** das Event-Log aus Phase A.3 ist append-only, mehrere Events aus einer Session landen einfach nebeneinander. Nur die zwei neuen Aktions-Typen (`signal_einverstanden`, `signal_disqualifiziert`) müssen additiv ins Schema (Phase D).

**Wann:** Nach A.4-A.7 abgeschlossen. Erste echte **Backend/Frontend-Parallelisierungs-Chance** mit zwei Worktrees.

### Phase B — Answer-Quality + LLM-Judge 📅

**Was:** Statt nur "wurde der richtige Chunk gefunden", auch "war die finale Antwort gut". Neuer Entry-Typ `AnswerQualityEntry` (Frage + Referenz-Antwort + Bewertungs-Rubrik), neuer Evaluator `llm_judge` der die Antwort des Suchsystems mit der Referenz vergleicht.

**Warum:** Retrieval-Qualität ≠ Antwort-Qualität. Auch wenn der richtige Chunk gefunden wird, kann die finale Antwort des LLM falsch interpretieren. Beide Dimensionen brauchen Messung.

### Phase C — Klassifikation + Multi-Agent 📅

**Was:** Neuer Entry-Typ `ClassificationEntry` (Chunk + erwartete Labels), Multi-Agent-Evaluator (mehrere LLMs als Jury, Aggregation der Urteile).

**Warum:** Manche Eval-Aufgaben haben mehr Varianz (subjektive Quality-Calls). Mehrere LLM-Judges + Aggregation reduziert Bias und gibt Konfidenz-Intervalle.

### Phase D — User-Signale auf Chunks und Test-Fragen 💭

> **Status:** Konzept entschieden (2026-04-29), Detail-Spec steht aus. Brainstorming-Runde wird nach A-Plus stattfinden, wenn Frontend-Realität klarer ist.

**Was:** Ein zweiter Bewertungs-Pfad parallel zu den Kurator-Operationen (refine/deprecate aus A.6) — diesmal getrieben von **User-Signalen aus dem Frontend**. Reviewer öffnen einen Chunk im Browser, sehen den Chunk-Inhalt selbst plus alle Test-Fragen, die ihn als erwartete Antwort haben, und können beides bewerten.

**Konkretes Frontend-Bild:**

```
User Bob öffnet Chunk B7-12 im Frontend.

Bildschirm zeigt:
  ┌────────────────────────────────────────────────────────┐
  │  Chunk B7-12 (aus Tragkorb-Handbuch, Seite 47)         │
  │  ─────────────────────────────────────────────────     │
  │  "Die maximale Zugkraft für M6-Verschraubungen liegt   │
  │   bei 8.5 kN gemäß DIN 912. Bei verzinkten Ausführungen│
  │   ist eine Reduktion um 15% zu berücksichtigen…"       │
  │                                                        │
  │  Diesen Chunk: [ einverstanden ] [ disqualifizieren ]  │
  │                                                        │
  │  Zugehörige Test-Fragen (3):                           │
  │  ────────────────────────────────                      │
  │  Frage 42: "Wo steht die maximale Zugkraft für M6?"    │
  │            [ einverstanden ] [ disqualifizieren ]      │
  │  Frage 87: "Welches Drehmoment für M6 verzinkt?"       │
  │            [ einverstanden ] [ disqualifizieren ]      │
  │  Frage 120: "Material-Spezifikation M6?"               │
  │            [ einverstanden ] [ disqualifizieren ]      │
  └────────────────────────────────────────────────────────┘
```

Bob klickt sich durch — pro Chunk und pro Frage entweder **einverstanden**, **disqualifizieren** mit Notiz, oder gar nichts (= skip, wird nicht aufgezeichnet).

**Was im Datenmodell aufgezeichnet wird:**

```
20.04. 14:02   Bob: einverstanden auf Chunk B7-12
20.04. 14:02   Bob: einverstanden auf Frage 42
20.04. 14:02   Bob: disqualifiziert Frage 120 ("zu allgemein, deckt mehr als nur diesen Chunk ab")
              (Frage 87 → Bob klickt nichts → kein Eintrag)
21.04. 09:15   Carol: disqualifiziert Chunk B7-12 ("der Satz ist abgeschnitten")
22.04. 11:30   Doktor Müller (PhD): disqualifiziert Frage 42 ("Antwort ist in B7-13, nicht B7-12")
```

Doktor Müller (Domänen-Experte mit `level="phd"`) klickt **dieselben Knöpfe** wie Bob. Es gibt **kein separates Expert-Approval** — entschieden am 2026-04-29 als "Welt 1". Im Aggregat zählt seine Stimme stärker, weil das System sein Level kennt; aber die Aktion selbst ist dieselbe.

**Admin-Sicht (sortiert nach Disqualifizierungs-Anzahl):**

```
Chunk B7-12:   5 disqualifiziert (3× "abgeschnitten", 2× andere)  → muss neu chunked werden
Frage 120:     8 disqualifiziert (5× "zu allgemein")               → muss präzisiert oder gelöscht werden
Frage 42:      1 disqualifiziert (Doktor Müller, mit Begründung)   → Korrektur nötig
```

Admin entscheidet pro Eintrag: **refine** (Korrektur via A.6-Funktion), **deprecate** (zurückziehen via A.6-Funktion), oder bei Chunks: neu chunken (zurück in Phase 2 Ingestion).

**Warum:**

- **Skalierbare Qualitätskontrolle.** Bei tausenden Chunks und Fragen ist manuelle Inspektion unmöglich. Aggregat-Signale = Triage-Werkzeug.
- **User-Engagement.** Reviewer können beitragen ohne Schreib-Rechte — Klicken statt Editieren senkt Hemmschwelle.
- **Chunk-Qualität ist eine Schicht tiefer.** Wenn Chunk B7-12 kaputt ist (abgeschnitten, Layout-Müll), sind alle Fragen darauf implizit kaputt. Direkt-Flagging am Chunk fängt das früher ab als über die Fragen.
- **Es matched die natürliche Reviewer-Sicht.** Reviewer denken kontextuell ("ich gucke mir Chunk B7-12 an und alle Fragen dazu"), nicht atomar ("ich gucke mir Frage 42 isoliert an").

**Wie (Grobskizze, vor Detail-Spec):**

- **Zwei mögliche Listen** (Detail offen): entweder eine zweite Datei `chunk_feedback_v1.jsonl` parallel zu `golden_events_v1.jsonl`, ODER neue Aktions-Typen im selben Log. Diskussion verschoben aufs spätere Brainstorming.
- **Zwei Aktions-Typen für User-Signale:**
  - `signal_einverstanden` — auf Chunk oder Frage, ohne Notiz
  - `signal_disqualifiziert` — auf Chunk oder Frage, mit Pflicht-Notiz
- **Skip wird nicht aufgezeichnet** — Absence eines Eintrags vom User X für Element Y bedeutet: nichts geklickt (oder nicht gesehen, das System unterscheidet das nicht).
- **Aggregat-Sicht:** sortierbar nach Anzahl, filterbar nach Notiz-Texten, Drilldown auf einzelne Einträge.
- **Verknüpfung Chunks ↔ Fragen** über das bestehende `expected_chunk_ids`-Feld in `RetrievalEntry`. Wenn ein Admin einen Chunk neu erzeugt (= alte ID weg, neue ID), werden alle Fragen mit der alten ID für einen Nachzug-Review markiert.

**Abhängigkeiten:**

- **Braucht Phase A-Plus (Frontend)** — ohne Browser-UI gibt's nichts zum Klicken. Dieses Phase D ist im Wesentlichen die Frontend-getriebene Aufzeichnungs-Schicht.
- **Braucht A.4-A.7 abgeschlossen** — die Verknüpfung Chunk↔Frage funktioniert nur, wenn Test-Fragen im neuen Goldset-System leben.
- **Berührt Phase 2 (Ingestion)** für Chunk-Reparaturen — "Chunk neu erzeugen" heißt Re-Ingestion oder ein Chunk-Edit-Modus. Eigener Aufwand.

**Unabhängig von Phase B und C** — drei separate Erweiterungs-Tracks nach A-Plus. Reihenfolge ergibt sich aus Bedarf.

**Offene Fragen für späteres Brainstorming** (in der nächsten Runde durchgegangen):

- Eine Liste neben Goldsets oder im selben Log mit neuen Aktions-Typen?
- Disqualifizieren mit Freitext-Notiz oder strukturierten Kategorien ("abgeschnitten" / "falscher Inhalt" / "Layout-Müll" als vorgegebene Optionen)?
- Wer darf disqualifizieren — jeder eingeloggter User, oder nur ab Mindest-Level?
- Was passiert mit Test-Fragen, deren Chunk gelöscht (nicht ersetzt) wird? Auto-disqualifizieren?
- Können User ihren eigenen Klick rückgängig machen, oder ist jede Aktion final?
- Was bedeutet "einverstanden" konkret im Aggregat — gewichtete Stimme nach Level, oder einfache Zählung?

### Phase E — Pipeline-agnostische Bewertung (`evaluators/span_match/`) 💭

> **Status:** Konzept entschieden (2026-04-29), Detail-Spec steht aus. Wird relevant, wenn eine zweite Pipeline (z.B. `pipelines/custom/`) zum Vergleichen existiert.

**Was:** Ein zweiter Evaluator neben `chunk_match` (aus Phase A.7) — `span_match`. Statt Chunk-IDs vergleicht er **Source-Element-IDs**. Damit können verschiedene Pipelines mit unterschiedlichen Chunking-Strategien gegen dasselbe Goldset gemessen werden.

**Match-Typ-Klassifikation** (Kern der neuen Bewertung):

| Match | Bedeutung | Beispiel |
|---|---|---|
| **EXACT** | Pipeline gibt genau das Source-Element zurück | Pipeline-Chunk = `{p47-p4}`, Goldset-Source = `p47-p4` |
| **CONTAINED** | Pipeline gibt Sub-Bereich zurück (präziser) | Pipeline-Chunk enthält nur einen Satz aus `p47-p4` → wird auf `p47-p4` hochgemappt |
| **CONTAINS** | Pipeline gibt Übermenge zurück (sprawling) | Pipeline-Chunk = `{p47-h1, p47-p1, ..., p47-p7}`, enthält `p47-p4` plus 6 weitere |
| **OVERLAP** | Teilüberlappung, weder Sub noch Super | (relevant nur bei Multi-Element-Goldsets) |
| **MISS** | Keine Überlappung | Pipeline-Chunk hat das gefragte Element nicht |

**Kernregel:** CONTAINED ist **kein Schaden, sondern oft ein Vorteil** — Pipeline arbeitet präziser als das Goldset es verlangt. Wenn die funktionale Prüfung (Phase B, LLM-Judge) bestätigt, dass die präzisere Antwort ausreicht, ist die Pipeline **besser** als eine, die EXACT zurückgibt mit mehr Drumherum.

**Konkretes Beispiel:**

```
Goldset Frage 42:
  source_element: p47-p4    ("Die maximale Zugkraft für M6 liegt bei 8.5 kN…")

Microsoft Pipeline gibt B7-12 zurück = {p47-h1, p47-p1, ..., p47-p5}
  → CONTAINS  (richtig gefunden, aber sprawling)
  → Recall = 100%, Precision = 1/7 = 14%

Andere Pipeline gibt M-742 zurück = {p47-p4}
  → EXACT
  → Recall = 100%, Precision = 100%

Andere-präzise Pipeline gibt nur ersten Satz von p47-p4 zurück
  → CONTAINED (auf p47-p4 hochgemappt)
  → Recall = 100%, Precision = 100%
  → funktionale Prüfung (Phase B): kann LLM mit nur dem Satz die Frage beantworten?
     - Falls ja → Pipeline war präziser UND korrekt → BESSER als EXACT
     - Falls nein → Pipeline war zu kurz → schlechter als EXACT
```

**Warum:** Cross-Pipeline-Vergleich war im Restructure-Spec immer als Ziel formuliert (`pipelines/custom/` als Erweiterungspunkt). `chunk_match` allein kann das nicht — Chunk-IDs sind pipeline-spezifisch. `span_match` macht's möglich.

**Wann:** wird gebaut, wenn ein zweiter Pipeline-Kandidat existiert. Vorher kein konkreter Use-Case. Datenmodell-Vorbereitung (`source_element` im Goldset) passiert aber **bereits in Phase A.4** — damit später keine Migrations-Arbeit nötig ist.

### Phase F — Query-Decomposition-Agent 💭

> **Status:** Idee skizziert, Brainstorming + Spec stehen aus. Wird nach Phase B relevant.

**Was:** Eine Agent-Schicht, die zur Laufzeit (nicht beim Curate!) **Vergleichs- und Multi-Step-Fragen** in Single-Element-Sub-Fragen zerlegt.

**Konkret:**

```
User stellt: "Vergleiche die Zugkraft für M6 verzinkt vs. nicht-verzinkt."

Agent-Decomposer (LLM-basiert):
  → Sub-Frage 1: "Was ist die Zugkraft für M6 nicht-verzinkt?"
  → Sub-Frage 2: "Welche Reduktion gilt bei verzinkten M6-Verschraubungen?"

Jede Sub-Frage geht durch die Retrieval-Pipeline (jede hat eine
Antwort in einem einzelnen Element). Der Agent kombiniert die beiden
Antworten zu einer Vergleichs-Antwort.
```

**Warum:**

- **Goldset bleibt schlank.** Single-Element-Fragen sind kurzbar, atomar, evaluierbar. Compound-Fragen blähen das Datenmodell auf und sind schwer zu bewerten.
- **Bewertbarkeit auf Sub-Frage-Ebene** ist sauber: jede Sub-Frage hat einen Single-Element-Match. Compound-Antwort-Qualität wird aggregiert.
- **Komplexität in der Anwendungsschicht**, nicht im Daten-Modell. Trennt strukturelle Bewertung (chunk_match / span_match) von semantischer Komposition (Agent).

**Wann:** nach Phase B (LLM-Judge), weil B die LLM-basierte Logik-Infrastruktur bereitstellt. Phase F nutzt diese Infrastruktur für die Decomposition.

---

## Workflow-Bild (nach A.4–A.7)

```
┌─────────────────────────────────────────────────┐
│  1. Goldsets entstehen lassen                   │
│     (a) Manuell: query-eval curate              │ ← A.4
│     (b) Automatisch: query-eval synthesise      │ ← A.5
│         → Events landen im Log                  │
└─────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────┐
│  2. Pflegen / Reviewen                          │
│     - approve / reject / refine / deprecate     │ ← A.6
│     - Frontend zeigt's mit Checkboxen           │ ← A-Plus
└─────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────┐
│  3. Evaluieren                                  │
│     query-eval eval → MetricsReport             │ ← A.7
│     (Recall@k, MRR, ...)                        │
└─────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────┐
│  4. Bei Index-Drift (Chunks haben sich geändert)│
│     → Drift-Warning im Report                   │
│     → Eintrag refinen oder deprecaten           │ ← A.6
└─────────────────────────────────────────────────┘
```

## Wartung dieses Dokuments

Diese Übersicht wird **automatisch nach jedem Phase-Statuswechsel** aktualisiert (Phase mergen → Status auf ✅, neue PR-Nummer eintragen, ggf. Spec-Link ergänzen). Das passiert in derselben Session, in der der Phase-Status sich ändert; nicht als separate PR.

Wenn diese Übersicht und ein Detail-Spec sich widersprechen, **gilt der Detail-Spec**. Die Übersicht ist Kurzfassung, nicht Vertrag.
