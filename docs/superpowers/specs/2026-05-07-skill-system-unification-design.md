# Skill System — Vereinheitlichung & No-Code-Erweiterbarkeit

> **For agentic workers:** Dieser Spec wird via `superpowers:writing-plans` in einen
> Implementierungs-Plan umgewandelt. Spec-Status: **Draft, await user review**.

**Goal (one sentence):** Eine *einzige* Skill-Abstraktion, die die heutigen drei
Mechanismen (Approach passive, Approach active, Reactive Capability, Reasons)
ersetzt — mit einem UI das Domain-Experten ohne Programmierung bedienen können.

**Architektur in drei Sätzen:** Ein Skill ist `(when, behavior, output)`-Tripel,
gespeichert als event-sourced JSONL. Backend hat *einen* Dispatcher der
`behavior` zu Pfaden routet (Prompt-Overlay, eigener LLM-Call, Annotation,
Reaktive Re-Evaluation, Notiz). Frontend versteckt Komplexität durch ~5
Templates die je 2-4 sichtbare Felder haben.

**Tech Stack:** Python 3.12 (FastAPI, Pydantic v2), TypeScript/React (existing).
Storage: JSONL append-only (existing pattern).

---

## 1. Motivation & Anti-Goals

### Was treibt diesen Spec
- **Vision (ii)**: Domain-Experten (Reaktortechnik, Geologie, …) sollen
  Anwendungs-Logik **ohne Dev-Hilfe** ergänzen können.
- **Konzeptueller Wildwuchs**: Heute drei verschiedene Storage-Files +
  drei verschiedene UIs für ein und dasselbe Konzept ("Skill, der
  Logik ergänzt").
- **UX-Komplexität**: ApproachFormModal hat aktuell ~700 Zeilen mit 15+
  Feldern, davon braucht ein Standard-User ~3.

### Was dieser Spec NICHT will
- ❌ **Workflow-Engine** mit Tool-Calls (Web-Search, externe APIs) →
  separate Phase, falls überhaupt.
- ❌ **Visueller Drag-and-Drop-Builder** → over-engineered für (ii).
- ❌ **Skill-Marketplace / Versionierung mit Diff** → später, nicht jetzt.
- ❌ **Backwards-Compat-Bruch ohne Migration** → existing data muss durch.

---

## 2. Status quo (was wegfällt)

### Heute existierende Mechanismen

| Mechanismus | Storage | UI | Use-Case |
|---|---|---|---|
| Approach (passive) | `approaches.jsonl` | ApproachFormModal | Prompt-Overlay pro step_kind |
| Approach (active) | `approaches.jsonl` (mode=active) | ApproachFormModal | Eigener Sub-Agent vor next_step |
| Reactive Capability | `approaches.jsonl` (triggers ≠ {}) | ApproachFormModal (🔧-Block) | Post-evaluate Re-Eval mit Domain-Rules |
| Reason | `reasons.jsonl` (separate dir) | inline „Reason aufzeichnen"-Button | Lehr-Notiz fürs nächste Mal |
| Hardcoded `_llm_extract_claim_backgrounds` | n/a | n/a | Aussage-Hintergrund (gerade gebaut, halb-Skill) |

Probleme:
- 4 Datenformate, 4 Storage-Pfade, 4 Read-Pipelines.
- ApproachFormModal ist überladen (passive/active/reactive in einem Form).
- Reasons können nichts was Approaches könnten — duplizierte Logik im Backend.
- claim_background ist hardcoded → user kann den Prompt-Kern nicht editieren
  (extra_system funktioniert, aber das fühlt sich „angeflanscht" an).

---

## 3. Target-Architektur

### 3.1 Das Skill-Datenmodell

```
Skill {
  # Identität (alle bestehenden Approach-Felder bleiben)
  skill_id: str (ULID)
  name: str (unique within skill_kind)
  version: int (monotonic per name)
  enabled: bool
  description: str (1 Satz für Cards/Listen)
  created_at, updated_at: ISO8601

  # WANN
  skill_kind: SkillKind  # Diskriminator, s.u.
  fires_on: list[str]    # ['extract_claims', 'evaluate', ...] — step_kinds
  conditions: TriggerConditions {
    verdicts: list[str]
    sentence_regex: list[str]
    claim_regex: list[str]
    topic_keywords: list[str]
    anchor_kinds: list[str]      # nur diese anchor-Typen
    goal_contains: list[str]      # Sitzungs-Ziel-Match
    text_contains: list[str]      # Anker-Text-Match
  }
  parent_skill: str | ""  # für hierarchische Skills (war: parent_capability)

  # WAS
  prompt: SkillPrompt {
    free_text: str            # für prompt-overlay, note, reactive
    questions: list[str]      # für enrichment (strukturierte Fragen)
    domain_rules: str         # für reactive (Re-Eval-Regeln)
  }

  # WOHIN
  output: SkillOutput {
    annotation_kind: str      # nur enrichment: 'claim_background', 'chunk_summary', ...
    attaches_to: str          # nur enrichment: 'claim' | 'chunk' | 'search_result'
    consumed_by: list[str]    # welche Steps die Annotation als context bekommen
  }
}

SkillKind = enum:
  prompt-overlay   # = Approach passive
  subagent         # = Approach active
  enrichment       # NEU: produziert Annotation-Node
  reactive         # = Reactive Capability
  note             # = Reason (kurze Lehr-Notiz)
```

### 3.2 Behavior-Pfade (Backend-Dispatcher)

Ein zentraler Dispatcher `apply_skills(step_kind, anchor, …)` fragt die
Skill-Library ab und routet je nach `skill_kind`:

```
prompt-overlay:
  → System-Prompt von step_kind erweitern um skill.prompt.free_text
  → Audit als guidance_consulted

subagent:
  → vor next_step: separater LLM-Call mit skill.prompt.free_text als System
  → Output landet als capability_request oder direkt im next_step-Ranking

enrichment:
  → nach Step (z.B. extract_claims accept):
    LLM-Call mit System=Default + skill.prompt.questions, Output JSON
  → Persist als Node kind=skill.output.annotation_kind, anchored an
    skill.output.attaches_to
  → Auto-included in skill.output.consumed_by step prompts
    (via _build_decision_context-ähnlicher Helper)

reactive:
  → nach evaluate: scan_capabilities (existing) gegen skill.conditions
  → Match → capability_gate-Node + skill.prompt.domain_rules in Re-Eval

note:
  → Kurz-Notiz, in jedem Step von skill.fires_on als auxiliary block injiziert
  → Wie heute Reasons, nur unter dem Skill-Dach
```

### 3.3 Storage

**Eine Datei**: `{data_root}/skills/skills.jsonl` (event-sourced wie heute
`approaches.jsonl`).

Records:
```json
{"skill_id": "01K…", "kind": "skill", ...}
{"skill_id": "01K…", "_tombstone": true}
```

Read-Pipeline: replay → latest non-tombstoned per name → return.

**Migration**: Beim ersten Start nach dem Update wird ein One-Shot Reader
gestartet:
1. `approaches.jsonl` einlesen → für jeden Approach den entsprechenden
   `skill_kind` ableiten (passive/active/reactive) → in `skills.jsonl` schreiben.
2. `reasons.jsonl` einlesen → als kind=`note` Skills migrieren.
3. Alte Files renamen: `approaches.jsonl.legacy`, `reasons.jsonl.legacy` (nicht
   löschen — Audit).

Keine Daten gehen verloren, alte Files bleiben für historische Reads.

---

## 4. UI-Design — der schwierige Teil

### 4.1 Eine Skill-Bibliothek

`/admin/provenienz/skills` (replaces ApproachLibrary):

```
┌─────────────────────────────────────────────────────────┐
│ Skill-Bibliothek                              [+ Neu]   │
│                                                         │
│ Filter: [Alle Kinds ▾] [Alle Steps ▾] [aktiv only ☐]    │
│                                                         │
│ ▼ 📜 Aussage anreichern (3 aktiv)                       │
│   ┌─ Reaktor-Hintergrund                v3 [aktiv] ✏    │
│   │  Holt Reaktor-Typ, Werte-Klasse, Standort           │
│   │  Feuert: extract_claims                             │
│   ├─ Geologie-Kontext                  v1 [aktiv] ✏    │
│   └─ ...                                                │
│                                                         │
│ ▼ 🔍 Such-Anfrage verbessern (1 aktiv)                  │
│   └─ Nuklear-Suchtipps                  v2 [aktiv] ✏    │
│                                                         │
│ ▼ ⚖ Bewertung neu fassen (2 aktiv)                     │
│   └─ ...                                                │
│                                                         │
│ ▼ 📌 Lehr-Notizen (5 aktiv)                             │
│   └─ ...                                                │
│                                                         │
│ ▼ 🛠 Eigene Skills (1 aktiv)                            │
│   └─ ...                                                │
└─────────────────────────────────────────────────────────┘
```

Gruppierung nach Template-Kategorie, NICHT nach `skill_kind` (das ist
intern). Templates UND `skill_kind` bestimmen zusammen die Gruppe.

### 4.2 Template-Picker (Neu-Knopf)

```
┌──────────────────────────────────────────────┐
│ Was soll dein Skill tun?                     │
│                                              │
│ ┌────────────────────────────────────────┐   │
│ │ 📜 Aussage anreichern                  │   │
│ │ Holt zusätzliche Infos aus dem Chunk,  │   │
│ │ schreibt sie an die Aussage. Beispiel: │   │
│ │ Reaktor-Typ, Werte-Klasse, Standort.   │   │
│ └────────────────────────────────────────┘   │
│ ┌────────────────────────────────────────┐   │
│ │ 🔍 Such-Anfrage verbessern             │   │
│ │ Lehrt den Agent, wie er Anfragen für   │   │
│ │ ein Thema formuliert.                  │   │
│ └────────────────────────────────────────┘   │
│ ┌────────────────────────────────────────┐   │
│ │ ⚖ Bewertung neu fassen                │   │
│ │ Reagiert auf bestimmte Verdicts und    │   │
│ │ wendet Domain-Wissen an.               │   │
│ └────────────────────────────────────────┘   │
│ ┌────────────────────────────────────────┐   │
│ │ 📌 Lehr-Notiz                          │   │
│ │ Kurze Regel, die in alle Prompts       │   │
│ │ eines Step-Typs aufgenommen wird.      │   │
│ └────────────────────────────────────────┘   │
│ ┌────────────────────────────────────────┐   │
│ │ 🧠 Agent-Denkregel                     │   │
│ │ Beeinflusst, WIE der Agent             │   │
│ │ den nächsten Schritt wählt.            │   │
│ └────────────────────────────────────────┘   │
│ ┌────────────────────────────────────────┐   │
│ │ 🛠 Eigener Skill (alle Felder offen)  │   │
│ │ Für Power-User. Volle Kontrolle.       │   │
│ └────────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

Klick auf Template → vorausgefülltes Form.

### 4.3 Template-Forms (das ist der Kern)

#### Template „📜 Aussage anreichern" (3 Felder)

```
Name:       [_____________________________]

Welche Fragen soll der Skill für jede Aussage
beantworten?
  ╔══════════════════════════════════════════╗
  ║ 1. ______________________________________║
  ║ 2. ______________________________________║
  ║ 3. ______________________________________║
  ╚══════════════════════════════════════════╝
                              (eine pro Zeile)

Optional: Wann soll der Skill feuern?
  ☐ Nur in Sitzungen mit Ziel:
       [Komma-getrennt: Reaktor, Brennelement…]

[Abbrechen]                          [Speichern]
```

Hinten dran (vor User versteckt):
```
skill_kind = enrichment
fires_on = ['extract_claims']
output.annotation_kind = 'claim_background'
output.attaches_to = 'claim'
output.consumed_by = ['formulate_task', 'evaluate']
prompt.questions = [user-input parsed]
```

#### Template „🔍 Such-Anfrage verbessern" (3 Felder)

```
Name:       [_____________________________]

Was soll der Agent beim Formulieren der Suchanfrage
beachten?
  ╔══════════════════════════════════════════╗
  ║                                          ║
  ║  Beispiel: Bei Reaktor-Aussagen den      ║
  ║  Reaktor-Typ und Standort als Suchbegriff║
  ║  mit aufnehmen. Bei Zahlen die Einheit   ║
  ║  immer mit suchen.                       ║
  ║                                          ║
  ╚══════════════════════════════════════════╝

Optional: Wann soll der Skill feuern?
  ☐ Nur in Sitzungen mit Ziel: [_____________]

[Abbrechen]                          [Speichern]
```

Hinten:
```
skill_kind = prompt-overlay
fires_on = ['formulate_task']
prompt.free_text = [user-input]
```

#### Template „⚖ Bewertung neu fassen" (5 Felder — der reactive Skill)

```
Name:       [_____________________________]

Wann soll der Skill reagieren? (mind. eine Bedingung)
  ☑ Verdict war:  ☑ widerspricht  ☐ teilweise stützt
  ☐ Aussage erwähnt: [_______________________]
  ☐ Treffer enthält Regex: [___________________]
                                  (eine pro Zeile)
  ☐ Sitzungs-Topic: [____________________________]

Welche Domain-Regel soll der Agent dann anwenden?
  ╔══════════════════════════════════════════╗
  ║                                          ║
  ║  Beispiel: Bei Wärmeleistung gilt:       ║
  ║  Aufrundung des Auslegungswerts ist      ║
  ║  konservativ wenn der tatsächliche Wert  ║
  ║  kleiner ist. Verdict ggf. flippen.      ║
  ║                                          ║
  ╚══════════════════════════════════════════╝

Optional: Übergeordneter Skill (falls dieser ein
Sub-Skill ist):
  [_____________________________]

[Abbrechen]                          [Speichern]
```

#### Template „📌 Lehr-Notiz" (3 Felder, super-simpel)

```
Name:       [_____________________________]

Bei welchem Schritt soll die Notiz gelten?
  ◯ Aussagen extrahieren
  ◯ Aufgabe formulieren
  ◯ Bewerten
  ◯ Stopp vorschlagen
  ◯ Bei jedem Step

Notiz:
  ╔══════════════════════════════════════════╗
  ║                                          ║
  ╚══════════════════════════════════════════╝

[Abbrechen]                          [Speichern]
```

#### Template „🧠 Agent-Denkregel"
Wie heute next_step-Approach. ~3 Felder.

#### Template „🛠 Eigener Skill"
Volles Form (~15 Felder, wie heutiges ApproachFormModal). Power-User-Pfad.

### 4.4 Skill-Detail-Panel

Beim Klick auf eine Skill in der Liste: Details + Bearbeiten + Aktivität:

```
┌────────────────────────────────────────────────────┐
│ Reaktor-Hintergrund                          v3 ⚙ │
│                                                    │
│ 📜 Aussage anreichern                              │
│ Feuert nach: Aussagen extrahieren                  │
│                                                    │
│ Konfiguration:                                     │
│   3 Fragen werden pro Aussage beantwortet          │
│   ▶ Welcher Reaktor-Typ / Anlage / Standort?       │
│   ▶ Auslegungs-, Mess- oder Rechenwert?            │
│   ▶ Welches Einheitensystem?                       │
│                                                    │
│ Wirkt sich aus auf:                                │
│   ✓ Aufgabe formulieren (Annotation als Kontext)   │
│   ✓ Bewerten (Annotation als Kontext)              │
│                                                    │
│ Aktivität (letzte 7 Tage):                         │
│   ▣ 23x in Sitzung "GNB B-147" ausgeführt          │
│   ▣ 4x in Sitzung "Vibration Loops"                │
│   ▣ 1x Parsing-Fehler (Aussage zu lang) → Audit    │
│                                                    │
│ [Bearbeiten]  [Deaktivieren]  [Löschen]            │
└────────────────────────────────────────────────────┘
```

### 4.5 Sichtbarkeit pro Skill-Aktivierung

Im Side-Panel eines Aussage-Tiles (oder anderem Anker), zusätzlich zu den
schon existierenden Sektionen:

```
🛠 Aktive Skills auf dieser Aussage
   • 📜 Reaktor-Hintergrund — 3 Fragen beantwortet  [details ▾]
   • 📌 Einheits-Notiz — angewandt                   [details ▾]
```

Klick aufs `details ▾` → zeigt die Skill-Output-Details, Skill-Audit-Trail
(welcher Skill-Version, welcher LLM-Call), Re-Run-Button.

---

## 5. Migration

### 5.1 Datenmigration (One-shot)

Beim ersten Start nach Update:

1. Wenn `skills/skills.jsonl` existiert → migration läuft nicht.
2. Sonst: lies `provenienz/approaches.jsonl` + iteriere über alle non-tombstoned Records:
   - `triggers ≠ {}` → `skill_kind = reactive`
   - `mode == 'active'` → `skill_kind = subagent`
   - sonst → `skill_kind = prompt-overlay`
   - Mappe alle Felder 1:1
   - Schreibe als Skill-Record nach `skills/skills.jsonl`
3. Lies `provenienz/reasons.jsonl` (falls existiert) → für jede Reason:
   - `skill_kind = note`
   - `fires_on = [reason.step_kind]`
   - `prompt.free_text = reason.text`
   - Schreibe als Skill-Record
4. Renaim `approaches.jsonl` → `approaches.jsonl.migrated-2026-05-XX`
5. Rename `reasons.jsonl` → `reasons.jsonl.migrated-2026-05-XX`

Idempotenz: Migration setzt ein Flag in `skills/_meta.json` (`{migrated_at: …}`).
Nochmaliger Start = no-op.

### 5.2 API-Migration (Backend)

- Alte Routes (`/approaches`, `/approaches/{id}`, …) bleiben **kompatibel**: lesen
  aus skills.jsonl, übersetzen in alten Approach-Schema-Form.
- Neue Routes (`/skills`, `/skills/{id}`) parallel.
- Frontend wechselt schrittweise von alten auf neue Routes; alte können in
  einer Folge-Phase entfernt werden.

### 5.3 UI-Migration

- ApproachLibrary-Route (`/admin/provenienz/approaches`) bleibt erhalten als
  Redirect → `/admin/provenienz/skills`.
- ApproachFormModal wird intern durch SkillFormModal ersetzt; bestehende
  „Edit"-Klicks landen im neuen Form (das wegen Migration auch alte Records
  bedienen kann).
- Reactive-Capability-spezifische UI (CapabilityGate-Tile, CapabilityGatePanel,
  /re-evaluate) bleibt **unverändert** — nur die Storage liegt jetzt in
  skills.jsonl statt approaches.jsonl.

---

## 6. Implementierungsplan (high-level)

Reihenfolge gewählt für minimale Brüche zwischen den Phasen:

### Phase S-1: Backend-Schema + Storage
- `Skill` Pydantic-Model + `SkillKind` enum
- `skills.jsonl` Storage-Layer (read/write/tombstone — kopiert vom approaches-Pattern)
- `migrate_approaches_and_reasons_to_skills()` One-shot
- Tests: Migration deterministisch, idempotent, alte Daten unverändert

### Phase S-2: Backend-Dispatcher
- `apply_skills(data_root, meta, step_kind, anchor)` — zentraler Hook
- Routet auf existing Pfade je nach `skill_kind`:
  - `prompt-overlay` → `_walk_approaches`-äquivalent
  - `subagent` → existing active-Approach-Pfad
  - `reactive` → existing scan_capabilities
  - `note` → existing reasons-Block-Builder
  - `enrichment` → NEU: `_run_enrichment_skill(skill, claim_texts, chunk_text)`
- Replace `_gather_guidance` Aufrufe mit `apply_skills` (aber gleiche Output-Form)

### Phase S-3: Enrichment-Runtime
- Neuer Step-Inner-Hook nach extract_claims accept (replaces hardcoded
  `_llm_extract_claim_backgrounds`):
  - finde alle Skills mit `skill_kind=enrichment, fires_on contains 'extract_claims'`
  - für jeden: LLM-Call mit `prompt.questions` als System-Erweiterung
  - persist Output als Node `kind=skill.output.annotation_kind`
- `_build_decision_context` liest Annotations aus consumed_by-Skills
- Generic Annotation-Renderer im Frontend SidePanel

### Phase S-4: Backend-API
- `GET /api/admin/provenienz/skills` (replaces `/approaches`)
- `POST /api/admin/provenienz/skills`
- `PATCH /api/admin/provenienz/skills/{id}`
- `DELETE /api/admin/provenienz/skills/{id}`
- Compatibility-Layer: alte `/approaches`-Routes bleiben, mappen intern auf Skills

### Phase S-5: Frontend Skill-Library
- Neue Route `/admin/provenienz/skills` (alte bleibt als Redirect)
- SkillLibrary-Komponente: gruppiert nach Template-Kategorie
- SkillCard mit Skill-Aktivität
- SkillDetailPanel

### Phase S-6: Frontend Templates
- TemplatePicker-Modal (initial 6 Templates)
- Pro Template eine spezifische Form-Variante mit reduzierten Feldern
- „Eigener Skill"-Template = Vollform (= heutiger ApproachFormModal)
- Live-Preview des erzeugten Skill-Rohdaten-Datensatzes (Power-User-Akkordeon)

### Phase S-7: Tests + Migration in Production
- Migrations-Test: alte approaches.jsonl + reasons.jsonl → erwartete skills.jsonl
- E2E-Test: pro Template-Form Skill anlegen + im Backend wirken sehen
- Manual-QA-Plan: pro Template ein Beispiel-Skill bauen, in einer Test-Session
  feuern lassen, Audit-Trail prüfen

---

## 7. Offene Entscheidungen (vor Implementierung)

Diese müssen **vorm** Plan-Schreiben beantwortet werden:

### D-1: Soll `claim_background` jetzt schon migriert werden?

Heute ist `_llm_extract_claim_backgrounds` hardcoded mit `extra_system`-Skill-Hook.
Wir können:
- (a) bestehenden Code als „eingebauter Default-enrichment-Skill" behandeln, der
  beim ersten Start auch in skills.jsonl als pre-seeded Skill landet
- (b) hardcoded löschen, ist nur noch ein User-Skill (default-Skill via
  Migration auto-erstellt)

**Empfehlung**: (b). Sauberer, hardcoded-Sonderfall verschwindet. Migration
seedet den Default-Skill genau einmal, danach ist er user-editierbar.

### D-2: Wie viele Templates initial?

Vorschlag (5+1):
1. 📜 Aussage anreichern
2. 🔍 Such-Anfrage verbessern
3. ⚖ Bewertung neu fassen
4. 📌 Lehr-Notiz
5. 🧠 Agent-Denkregel
6. 🛠 Eigener Skill (= alle Felder)

**Bestätigen oder anpassen?**

### D-3: Sollen Template-Forms „Live-Preview" zeigen?

Power-User wollen ggf. den erzeugten System-Prompt sehen. Wir können:
- (a) verstecken (clean), Preview nur in „Eigener Skill"
- (b) immer einen ausklappbaren „Roh-Daten anzeigen"-Akkordeon

**Empfehlung**: (b). Hilft beim Debug, nur 1 Akkordeon.

### D-4: Wann läuft Migration in Prod?

Optionen:
- (a) Beim ersten API-Call automatisch (lazy)
- (b) Beim Service-Start (eager)
- (c) Manuelles Migrations-Skript (Operator-getrieben)

**Empfehlung**: (b) — Service-Start. Kein Race-Condition-Risiko bei nebenläufigen
Calls.

### D-5: Brauchen wir Template-spezifische `consumed_by`-Defaults?

Heute hardcoded:
- claim_background-Annotations werden von formulate_task + evaluate konsumiert
- chunk_summary (hypothetisch) würde von extract_claims konsumiert

**Vorschlag**: Per Template ein Default-`consumed_by`-Set, im Power-User-Modus
editierbar.

### D-6: Skill-Aktivität: tracken wir?

Pro Skill-Run einen Audit-Eintrag (welcher Skill, welche Version, welche
Eingaben, welche Ausgabe-Node).

**Empfehlung**: Ja, klein halten. `skill_runs.jsonl` separat oder als reguläre
Provenienz-Events markiert.

---

## 8. Erfolgskriterien

Spec ist erfolgreich umgesetzt wenn:

1. ✓ Ein nicht-Programmierer kann in <5 Min einen neuen „Aussage
   anreichern"-Skill anlegen, der bei der nächsten extract_claims-Akzeptanz
   feuert und im Aussage-Panel sichtbar wird.

2. ✓ Bestehende Approaches + Reasons funktionieren unverändert (transparente
   Migration).

3. ✓ Reactive-Capability-Flow (capability_gate → re-evaluate) funktioniert
   unverändert.

4. ✓ Alle bestehenden provenienz-Tests grün.

5. ✓ Es gibt **eine** Skill-Bibliothek-Seite, **einen** „Neu"-Button, **einen**
   Skill-Detail-View.

6. ✓ ApproachFormModal-Code mit ~700 Zeilen wird durch TemplatePicker +
   ~5 Form-Varianten von je <150 Zeilen ersetzt. Power-User-Form bleibt für
   den Edge-Case.

---

## 9. Was NICHT in diesem Spec ist

Bewusst ausgeklammert für Folge-Specs falls jemals nötig:

- **Skill-Versions-Diff-View** (welche Felder hat sich Skill X von v3 auf v4
  geändert)
- **Skill-Klone / Vorlagen** (von einem Skill ausgehend einen neuen erstellen)
- **Multi-Skill-Ketten** (Skill A's Output ist Skill B's Input — geht heute
  nicht im DSL)
- **Externe Tool-Calls** (Web-Search, REST-APIs)
- **Skill-Marketplace / Import-Export** als JSON
- **Live-Preview LLM-Call** im Form (würde Skill direkt feuern, teuer)

---

## 10. Nächster Schritt

Wenn dieser Spec OK ist:
1. User reviewed das Dokument, gibt Feedback zu D-1 bis D-6
2. Ich erstelle den **Implementierungs-Plan** in
   `docs/superpowers/plans/2026-05-XX-skill-system-unification-plan.md`
   mit Step-by-Step-Tasks (TDD, atomic commits)
3. Implementierung beginnt erst nach Plan-Approval

---

**Status Log**
- 2026-05-07: Draft, await user review
