---
title: End-to-End Smoke Walkthrough
audience: Operators verifying a fresh deploy or a feature-branch merge
last_reviewed: 2026-06-03
covers: PR #51 (Statistik + Voting), PR #52 (MinerU table-cell fix), PR #53 (mypy/pre-commit alignment)
---

# End-to-End Smoke Walkthrough

A guided manual run that drives a real document through every pipeline stage —
Extract → Synthese → Voting → Provenienz → Statistik — and checks each step's
output against an explicit rubric. Designed for ~30 minutes if no failures
surface, longer if anything breaks (failure paths are inline).

Pair this with the automated suites (`pytest` + `vitest`). The suites catch
contract breaks; this catches the visual, the cross-feature, and the
anti-anchoring kind of regression that an isolated unit test cannot.

### Schnellpfad — die zwei automatisierten Smokes statt manuell

Wenn du nur prüfen willst, dass die Konturen halten (nicht jeden visuellen
Schritt drücken), zwei Scripts erledigen das in ~30 Sekunden zusammen:

```bash
# 1. Backend-API-Kontrakt (14 Assertions, no browser)
.venv/bin/python scripts/smoke/backend_e2e.py
# → expects backend on $LOCAL_PDF_API_BASE (default :8000) with PR #51 code
#   Pre-merge note: see the script's module docstring for PYTHONPATH override.

# 2. Frontend UI-Kontrakt — anti-anchoring, stripes, tabs, auth-gate
# Seed first (the spec needs a pre-existing question to vote on):
.venv/bin/python scripts/smoke/backend_e2e.py --keep   # prints slug=smoke-…

# Then run the Playwright tests:
LOCAL_PDF_E2E=1 \
LOCAL_PDF_TEST_TOKEN=$GOLDENS_API_TOKEN \
LOCAL_PDF_TEST_SLUG=<slug from step above> \
LOCAL_PDF_API_BASE=http://localhost:8000 \
npm run e2e -- --grep "Statistik|Voting"
```

Manueller Walkthrough (unten) bleibt nötig wenn du die fancy charts visuell
beurteilen willst, oder die zweite Browser-Session für cross-user Voting.

---

## 0. Vorbereitung

### 0.1 Branch-State

This walkthrough assumes all three PRs from the 2026-06-03 batch have landed
on `main` (or you're testing the merged result):

- [ ] **#51** `feat/statistics-and-voting` — sechster `Statistik` DocStepTab,
  Voting-UI in QuestionList, vote-summary on /questions
- [ ] **#52** `fix/mineru-superscript-table-context` — `<td>col1</td>` stays
  literal (no false superscript)
- [ ] **#53** `fix/mypy-cleanup` — env-aligned mypy, no stale ignores

Pre-flight assertion:

```bash
git log --oneline -3
git status --short    # must be clean
```

### 0.2 Services hochfahren

```bash
# Terminal A — Backend
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
export GOLDENS_API_TOKEN="dev-token"
export LOCAL_PDF_DATA_ROOT="/home/ktazefid/Documents/local-pdf-test/data"
source .venv/bin/activate
uvicorn local_pdf.api.app:create_app --factory --reload --port 8000 \
        --app-dir features/pipelines/local-pdf/src
```

```bash
# Terminal B — Frontend
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft/frontend
npm run dev
```

Health-Check:
```bash
curl -s -H "X-Auth-Token: dev-token" http://localhost:8000/api/health
# ⇒ {"data_root":"/home/ktazefid/Documents/local-pdf-test/data"}
```

### 0.3 Accounts

Two browser sessions (use a normal window + a private window, or two different
Chrome profiles — they must not share cookies):

| Session | Tenant | Username | Password | Role | Pseudonym |
|---------|--------|----------|----------|------|-----------|
| A | default | `admin` | `dev-admin-pw` | admin | Sorgsamer Bär |
| B | default | `wt-kurator` | `dev-curator-pw` | curator | Heiterer Wisent |

(Beide Passwörter sind Dev-only und wurden in `/home/ktazefid/Documents/local-pdf-test/data/_meta/auth.db` gesetzt.)

### 0.4 Test-PDF

Pick or upload a multi-page PDF that contains at least:

- One table mit Spaltenheader (z.B. "col1", "col2") — verifiziert PR #52
- One paragraph and one heading — Synthese hat genug Inhalt für Q/A-Gen
- Eine Bibliography-Seite ODER ein Inhaltsverzeichnis — Register-Detection sichtbar
- Mindestens 3 Seiten — Statistik-Diagramme haben genug Datenpunkte

Notiere den späteren Slug — du brauchst ihn für direkte URL-Sprünge.

---

## 1. Login + Inbox (Session A: admin)

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 1.1 | `http://localhost:5173/` → Login form | Username/Password Felder + Tenant-Dropdown | 401 — Backend nicht erreichbar oder GOLDENS_API_TOKEN-Mismatch |
| 1.2 | Login als admin/default/dev-admin-pw | Redirect zu `/admin/inbox` | Wrong-password-Toast: prüfe Hash-Reset aus 0.3 lief durch |
| 1.3 | Inbox sichtbar, Doc-Liste rendered | Tabelle / Grid mit existierenden Docs | Leerer Screen: dev-DB enthält ggf. keine Docs — weiter mit Schritt 2 |

**Sign-off 1**: ☐ Login funktioniert, Inbox lädt ohne Konsolen-Errors.

---

## 2. PDF hochladen (Session A: admin)

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 2.1 | Upload-Button → PDF auswählen | POST `/api/admin/docs` returns 201 mit `{slug}` | 413 = Datei zu groß; 415 = nicht-PDF-Mimetype |
| 2.2 | Doc erscheint in Inbox | Status `uploaded` / `extracted` | Doc-Card fehlt: react-query-Cache invalidation könnte hängen — Inbox refresh erzwingen |
| 2.3 | Notiere den Slug | z.B. `walkthrough-mqxxxxxxx` | — |

**Sign-off 2**: ☐ Doc-Slug `_________________` notiert.

---

## 3. Extrahieren (Session A: admin)

Click den Doc → landet auf `/admin/doc/{slug}/extract`.

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 3.1 | Seite-1 PDF rendered | PdfPage mit Bounding-Box-Overlay sichtbar | Schwarzer Canvas: pdfjs-dist asset-path; check Browser-Console |
| 3.2 | YOLO-Boxen overlay liegt drüber | Farbige Rechtecke per Box-Kind | Keine Boxen: YOLO-Pipeline nicht durchgelaufen — Backend-Log prüfen |
| 3.3 | Box-Kind-Legende rechts | paragraph / heading / table / figure ... | — |
| 3.4 | Click auf eine Table-Box | Box-Properties-Panel öffnet sich | — |
| 3.5 | **PR #52 Check**: Box mit Tabelle `col1`/`col2` als Header → HtmlEditor zeigt | Literal `col1`, **NICHT** `col¹` | Wenn `col¹` sichtbar → MinerU-Bug in dieser Branch nicht gefixt; PR #52 fehlt |
| 3.6 | Bibliography- oder ToC-Seite ansehen | Box-Kind = `toc` / `bibliography` automatisch | Kind = `paragraph` → Register-Detection-Klassifikator hat danebengehauen, sammeln für späteren Stats-Check |

**Sign-off 3**: ☐ MinerU-Tabellen-Fix verifiziert (PR #52). ☐ Mindestens 1 Register-Box klassifiziert.

---

## 4. Synthese (Session A: admin)

Click "Synthese" Tab.

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 4.1 | HTML-Preview links, Question-Sidebar rechts | Read-only Doc-HTML | Leerer Preview = mineru-out.json fehlt |
| 4.2 | Click eine Box im Preview | Sidebar zeigt diese Box's Frage(n) ODER "Noch keine Fragen" + Generate-Button | Sidebar bleibt leer = box_id-Mapping kaputt |
| 4.3 | Generate Q/A für eine Paragraph-Box | LlmStream-Events scrollen, danach 1-3 Fragen mit Antworten | Stream bricht ab = AI_FOUNDRY_KEY env-var fehlt im Backend-Process; Backend-Log "auth failure" |
| 4.4 | Pencil-Icon → Frage editieren → Save | Frage-Text aktualisiert ohne Reload | — |
| 4.5 | Trash-Icon → Frage deprecate | Frage verschwindet aus Sidebar | events.jsonl hat jetzt `created` + `deprecated` Pair |

**Sign-off 4**: ☐ Mindestens 3 Fragen für 2+ Boxen generiert. ☐ 1 Frage editiert. ☐ 1 Frage deprecated.

---

## 5. Voting (Anti-Anchoring) — Kern-Test PR #51

Zwei Browser-Sessions parallel: **A=admin**, **B=wt-kurator**, beide auf
`/admin/doc/{slug}/synthesise`, gleiche Box geöffnet, gleiche Frage sichtbar.

### 5.1 Vor irgendeinem Vote (beide Sessions)

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 5.1.1 | Frage-Karte ansehen | Linker Rand der `<li>` = `border-l-transparent` (kein Stripe) | Stripe sichtbar = vote_summary.my_vote != null falsch |
| 5.1.2 | Zwei Vote-Buttons im Footer-Toolbar | Grünes CheckCircle2 + rotes XCircle, rechts neben Edit/Trash | Buttons fehlen = onVote-Prop nicht gewired in Synthesise.tsx |
| 5.1.3 | Counts-Sektion **NICHT** sichtbar | Anti-Anchoring: bis user gevotet hat, keine Zahlen | Counts sichtbar = Decision 14 verletzt |

### 5.2 Session A votet "Einverstanden"

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 5.2.1 | Click Einverstanden in A | Optimistisches Update: Stripe wird `emerald-500`, Button-State wechselt zu cast (gefüllt) | Stripe bleibt transparent = mutation invalidation queryKey falsch |
| 5.2.2 | Counts-Sektion erscheint | `1 ✓ · 0 ✗` rechts unten unter Footer-Toolbar | Counts zeigen 0/0 = vote-summary-Refetch hat den eigenen Event noch nicht gesehen, kurz warten |
| 5.2.3 | Session B (wt-kurator) reload | Frage-Karte zeigt Stripe **NICHT** (er hat noch nicht gevotet) | Stripe in B sichtbar = my_vote-Berechnung leakt fremde Stimme |
| 5.2.4 | Session B Counts sind weiter **versteckt** | Anti-Anchoring: B sieht "1 ✓" nicht, bis B selbst votet | Counts in B sichtbar = anti-anchoring kaputt |

### 5.3 Session B votet "Disqualifizieren"

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 5.3.1 | Click Disqualifizieren in B | B's Stripe wird `red-500`, B's Counts erscheinen jetzt: `1 ✓ · 1 ✗` | — |
| 5.3.2 | Session A reload | A's Counts updaten: `1 ✓ · 1 ✗` | Wenn A weiter `1 ✓ · 0 ✗` zeigt → invalidation in B's mutation invalidiert nur B's QueryClient (sollte aber backend-side neu gefetched werden bei reload) |
| 5.3.3 | A's Stripe bleibt emerald | A's my_vote bleibt "approved" | — |
| 5.3.4 | B's Stripe bleibt red | B's my_vote bleibt "rejected" | — |

### 5.4 Toggle-off via revoked (Session A)

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 5.4.1 | Click Einverstanden nochmal in A | Mutation feuert mit `action: "revoked"` | Backend bekommt "approved" statt "revoked" = QuestionList toggle-Berechnung kaputt |
| 5.4.2 | A's Stripe verschwindet | `border-l-transparent` zurück | — |
| 5.4.3 | A's Counts verschwinden | Anti-Anchoring greift wieder (my_vote=null) | Counts bleiben sichtbar = condition `{my != null && ...}` falsch |
| 5.4.4 | Session B reload | B sieht `0 ✓ · 1 ✗` (nur B's Stimme zählt) | Wenn `1 ✓ · 1 ✗` → revoked-Event wird in `_collapse_votes_for_entries` nicht ausgeschlossen |

### 5.5 Backend-Trace (optional)

```bash
tail -5 /home/ktazefid/Documents/local-pdf-test/data/{slug}/datasets/golden_events_v1.jsonl
# letzten 5 Events lesen — sollte enthalten:
#   {"event_type":"reviewed","payload":{"action":"approved","actor":{"pseudonym":"Sorgsamer Bär",...}}}
#   {"event_type":"reviewed","payload":{"action":"rejected","actor":{"pseudonym":"Heiterer Wisent",...}}}
#   {"event_type":"reviewed","payload":{"action":"revoked","actor":{"pseudonym":"Sorgsamer Bär",...}}}
```

**Sign-off 5**: ☐ Anti-Anchoring funktioniert (5.1.3 + 5.2.4 + 5.4.3). ☐ Toggle-to-revoked funktioniert (5.4.x). ☐ Cross-Session-Zahlen stimmen.

---

## 6. Provenienz (Session A: admin)

Click "Provenienz" Tab.

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 6.1 | Sessions-Liste rendert | Existierende Agent-Sessions oder leerer Screen mit "Keine Sessions" | — |
| 6.2 | (Falls leer) Generate-Action triggern aus Synthese (LLM-driven) | Eine neue Session erscheint mit Nodes: chunk → plan_proposal → ... | — |
| 6.3 | Click eine Session | Agent-Canvas rendert ReactFlow-Graph | Black canvas = Layout-Walker hat keine ViewNodes — Console nach "view:" prefixed errors prüfen |
| 6.4 | Sub-Tab "Wünsche" (Capability-Wünsche) | Tabelle mit angefragten Skills, count_by_actor pro Wish | Leere Tabelle = noch keine capability_request Events in dev-DB |
| 6.5 | Plan-Proposal-Knoten clicken | PlanProposalPanel öffnet sich rechts mit Override-Option | — |

**Sign-off 6**: ☐ Provenienz-Tab lädt, mindestens 1 Session sichtbar oder Erklärung warum nicht.

---

## 7. Statistik (NEU — PR #51 Kern-Test)

Click "Statistik" Tab (sechster + neuester Tab — `BarChart3` Icon rechts).

### 7.1 Tab-Bar persistiert

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 7.1.1 | DocStepTabs oben | 6 Tabs sichtbar, Statistik als 6. | Tab-Bar fehlt = Statistics.tsx rendered DocStepTabs nicht (siehe Task-10-Fix) |
| 7.1.2 | "Statistik" Tab aktiv markiert | Weisser Unterstrich | — |

### 7.2 Auth-Gate

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 7.2.1 | Eingeloggt: 3 Sektionen rendern (siehe 7.3) | — | — |
| 7.2.2 | Logout-und-direkt-URL `/admin/doc/{slug}/statistics` | "Bitte zuerst anmelden." | Komplett leere Seite = useAuth().token==null nicht abgefangen |

### 7.3 Sektion 1 — Extrahieren

| Sub-Element | Erwartet | Failure-Mode |
|-------------|----------|--------------|
| Heading `Extrahieren` | links oben, navy-100 Farbe | — |
| **DiagnosticBar** (Stacked-Bar) | Horizontaler Stacked-Bar: clean (gradient emerald) + no_decomposition (rot) + split (amber) | Komplett emerald = keine Diagnostics vorhanden (Doc war perfekt) — OK |
| **MetricCounter** (Register-Boxen) | Count-Up-Animation, dann z.B. "2 / 15" (2 Register-Boxen / 15 total) | Counter bleibt bei 0 = mineru/segments.json haben keine register-kinds; oder Register-Detection ist degenerate |
| Lädt-State während fetch | "Lädt…" vor Datenankunft | Permanent "Lädt…" = endpoint 401 — X-Auth-Token wird nicht vom Frontend weitergereicht |

### 7.4 Sektion 2 — Synthese

| Sub-Element | Erwartet | Failure-Mode |
|-------------|----------|--------------|
| Heading `Synthese` | — | — |
| **MetricGauge "Curator-Überleben"** | Radial-Bar, % je nach (created-deprecated)/created | Bei 0 deprecates: 100% — OK |
| **MetricGauge "Reviewer-Zustimmung"** | Bei 1 ✓ · 1 ✗ aus Schritt 5: zeigt 50%, gauge mid (accent-Farbe) | Bei zero votes: "Keine Daten" + en-dash | Beide Gauges "Keine Daten" = vote-summary nicht persistiert |
| **VoteDistributionBar** | Stacked-Bar mit den Fragen die Votes haben (sortiert nach Kontroversität) | "Noch keine Reviewer-Stimmen vorhanden." wenn nichts gevotet | Empty-State trotz Votes = vote_distribution feld leer im API-Response |

### 7.5 Sektion 3 — Provenienz

| Sub-Element | Erwartet | Failure-Mode |
|-------------|----------|--------------|
| Heading `Provenienz` | — | — |
| **MetricGauge "Experten-Korrekturen"** | Radial-Bar je nach (overrides/plan_proposals) — bei frischem Doc: "Keine Daten" | Permanent "Keine Daten" wenn doch Sessions vorhanden = `_EXPERT_OVERRIDE_KINDS` matched die Node-Kinds nicht |
| **CapabilityWishesSunburst** (eigentlich Treemap-Fallback) | Verschachtelte Rechtecke per skill_bucket → wish-name, navy/brand Palette | Empty-State "Noch keine Wünsche" wenn keine `capability_request` events | Schwarzer Bereich = Recharts Treemap data-shape falsch (siehe TreemapDataType-Index-Signature) |

### 7.6 Tenant-Weite Capability-Wishes

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 7.6.1 | Sunburst-Inhalt gehört allen Tenant-Docs (nicht nur dem aktuellen) | Sub-Header / Hinweis "(Über alle Dokumente)" | Fehlt = Decision 1 verletzt: tenant-widget-embedding nicht implementiert |

**Sign-off 7**: ☐ 3 Sektionen rendern. ☐ Mindestens 1 Gauge zeigt konkreten %-Wert. ☐ Sunburst rendert (mit Daten oder mit Empty-State). ☐ Auth-Gate verifiziert (7.2.2).

---

## 8. Compare (Optional, nicht-PR-Scope)

Click "Vergleich" Tab. Out-of-Scope für diese PR-Batch, aber als Smoke-Check
sinnvoll dass die Navigation nicht crasht.

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 8.1 | Tab lädt | Page rendert (Inhalt feature-abhängig) | 500 = Comparison-Hook regressed |

**Sign-off 8**: ☐ Vergleich-Tab crasht nicht.

---

## 9. Logout + Re-Login

| Schritt | Aktion | Erwartet | Failure-Mode |
|---------|--------|----------|--------------|
| 9.1 | Logout aus beiden Sessions | Redirect zum Login | — |
| 9.2 | Re-Login als admin | Direkter Tiefenlink: `/admin/doc/{slug}/statistics` → lädt 7.3 Daten | Verlust der Daten = `_meta/auth.db` wurde regneriert; Hash-Reset prüfen |

**Sign-off 9**: ☐ Logout/Login Cycle clean.

---

## 10. Abschluss-Rubrik

Mindest-Pass-Kriterien für diese 3-PR-Batch:

- [ ] **PR #52**: Tabellen-Inhalt bleibt literal (`col1`, nicht `col¹`) — Schritt 3.5
- [ ] **PR #53**: `mypy features/pipelines/local-pdf/src features/goldens/src` zeigt 0 errors UND `pre-commit run mypy --all-files` zeigt Passed (CLI-Sanity)
- [ ] **PR #51 Statistics-Tabs**:
  - 6. DocStepTab `Statistik` sichtbar (7.1.1)
  - Auth-Gate bei logout (7.2.2)
  - 3 Sektionen rendern (7.3 / 7.4 / 7.5)
  - Mindestens 1 Gauge zeigt %-Wert nicht "Keine Daten"
  - Sunburst (oder Empty-State) rendert
- [ ] **PR #51 Voting**:
  - Anti-Anchoring: Counts versteckt vor eigenem Vote (5.1.3, 5.2.4, 5.4.3)
  - Toggle-to-revoked via 2x-Klick funktioniert (5.4)
  - Cross-Session-Counts stimmen (5.3.2, 5.4.4)
  - Border-Stripe per-User korrekt gefärbt
  - Backend-events.jsonl enthält `approved`/`rejected`/`revoked` Events (5.5)

Wenn alle ☐ ticked: **Sign-off-Bereich** unten — merge-ready für die 3 PRs.

---

## Anhang A: Backend-Logs zur schnellen Triage

```bash
# Frontend Console: F12 → Network → filter on /api/admin
# Backend Logs:
journalctl --user -u local-pdf-backend  # falls als service
# oder direkt im Terminal A wo uvicorn läuft

# events.jsonl Inhalt für Doc {slug}:
ls -la /home/ktazefid/Documents/local-pdf-test/data/{slug}/datasets/
wc -l /home/ktazefid/Documents/local-pdf-test/data/{slug}/datasets/golden_events_v1.jsonl

# Auth-DB Inhalt:
source .venv/bin/activate
python -c "
import sqlite3
c = sqlite3.connect('/home/ktazefid/Documents/local-pdf-test/data/_meta/auth.db')
c.row_factory = sqlite3.Row
for r in c.execute('SELECT username, level, active FROM users'):
    print(dict(r))
"
```

## Anhang B: Häufige False-Negatives

- **"Statistik tab fehlt"** → wahrscheinlich auf einem Branch ohne PR #51 gemerged. Check: `git log --oneline | grep statistics`.
- **"Counts immer 0/0"** → react-query staleTime > 0 hält alten Cache. Hard-Reload (Ctrl+Shift+R).
- **"Sunburst leer obwohl Capability-Wishes existieren"** → das `list_capability_requests` aggregator walkt nur `{cfg.data_root}/{slug_dir}/provenienz/`. Wenn deine Sessions woanders liegen → empty.
- **"Sweep-Test-Count 806 statt 825"** → pytest --no-cov vs mit-coverage produziert unterschiedliche collection counts. Egal solange exit-code 0.

## Anhang C: Reset-Pfad (falls Dev-DB korrupt)

```bash
# WARNUNG: alle dev-data weg
rm -rf /home/ktazefid/Documents/local-pdf-test/data/{slug}/
# Auth-DB regenerieren:
rm /home/ktazefid/Documents/local-pdf-test/data/_meta/auth.db
# Backend neu starten → Migration v1+v2 läuft automatisch
# Neu seeden via admin API (POST /api/admin/users) oder Python:
source .venv/bin/activate
python -c "
from local_pdf.auth.db import open_auth_db, ensure_schema
from local_pdf.auth.tenants import create_tenant
from local_pdf.auth.users import create_user
from pathlib import Path
root = Path('/home/ktazefid/Documents/local-pdf-test/data')
with open_auth_db(root) as conn:
    ensure_schema(conn)
    t = create_tenant(conn, slug='default', name='Default')
    create_user(conn, tenant_id=t.tenant_id, username='admin', password='dev-admin-pw', role='admin', level='other')
    create_user(conn, tenant_id=t.tenant_id, username='wt-kurator', password='dev-curator-pw', role='curator', level='other')
"
```

---

## Sign-off

| Tester | Datum | PR #51 | PR #52 | PR #53 | Bemerkungen |
|--------|-------|--------|--------|--------|-------------|
|        |       | ☐      | ☐      | ☐      |             |
