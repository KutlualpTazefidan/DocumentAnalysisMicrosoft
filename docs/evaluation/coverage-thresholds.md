# Coverage-Schwellen für `features/goldens/`

Diese Schwellen gelten als Mindest-Anforderung für `pytest --cov` im
`goldens`-Paket. Sie sind nicht willkürlich gesetzt, sondern spiegeln den
Anteil deterministischer, sinnvoll testbarer Logik im jeweiligen Modul.

| Modul | Schwelle | Grund (Stichwort) |
|-------|----------|-------------------|
| `goldens/schemas/` | 100 % | Reine Dataclasses, minimale Branches |
| `goldens/storage/` | 95 %+ | Kritischer Pfad für Datenintegrität |
| `goldens/creation/` | 70 % | LLM-Calls gemockt → kombinatorische Lücke |
| `goldens/operations/` | 90 %+ | Deterministisch, aber mehr Business-Branches |

## `schemas/`: 100 %

Schemas sind reine `@dataclass(frozen=True)` Definitionen mit minimaler Logik:

- Felddeklarationen sind Daten, kein Code, der "verfehlt" werden kann.
- Optional: `__post_init__`-Validierung, derived properties (z. B. `level`),
  serialization helpers.
- Branches sind einfach: Bei `level` z. B. "wenn alle Actors LLM, dann
  `synthetic`, sonst höchstes Human-Level".

100 % ist hier die natürliche Untergrenze. Coverage <100 % bedeutet entweder:
ein Dataclass ist gar nicht getestet, oder ein Branch in `__post_init__` wurde
vergessen. Beides ist mit ~3 Zeilen Test behebbar — die "Kosten" sind
vernachlässigbar.

## `storage/`: 95 %+

Storage ist der **kritische Pfad** für Datenintegrität:

- Concurrent writes ohne Lock → Korruption, Datenverlust.
- Idempotency-Check defekt → doppelte Events, korrupte Projection.
- Read-Parsing scheitert → State kann nicht rekonstruiert werden.

Alle Happy Paths, alle erwarteten Fehlerpfade (idempotency, file missing,
malformed line) werden getestet. Die fehlenden ~5 % sind:

- `OSError` auf `flock()` bei NFS-ähnlichen Filesystems
- `OSError` auf `fsync()` bei Disk-Full
- Linux-spezifische Syscall-Edge-Cases auf macOS-CI

Diese Branches lassen sich nur mit komplexem Monkey-Patching auslösen. Der
Aufwand-Nutzen-Trade-off ist schlecht: die Schutzmechanismen sind im Code,
sie müssen aber nicht zwingend über Tests verifiziert werden — die nächste
Schicht (Filesystem) wird sie selbst korrekt umsetzen.

## `creation/`: 70 %

`creation/` enthält LLM-Aufrufe (synthetic generation, query-suggestion).
LLM-Calls werden gemockt — echte API-Calls sind:

- **teuer** (Token-Kosten pro Test-Run, multipliziert mit CI-Frequenz)
- **nicht-deterministisch** (Output ändert sich zwischen Runs)
- **langsam** (hundert Tests × 2 s API = inakzeptable Test-Suite-Dauer)

Was getestet wird (innerhalb der 70 %):

- Prompt-Konstruktion: Input-Parameter → erwarteter Prompt-String
- Response-Parsing: gemockte API-Response → erwarteter `Entry`
- Retry-Logik bei malformed Output (mit gemockten Fehlern)
- Validierungslogik (z. B. abgelehnte Synthese-Outputs)

Was NICHT getestet wird (die fehlenden ~30 %):

- Tatsächliches LLM-Verhalten: ob ein Prompt-Template gute Queries produziert.
- Robustheit gegenüber realen LLM-Failure-Modes (rate limits, content filters,
  Token-Limits, partial completions).
- Kombinatorische Pfade zwischen mehreren Retries und mehreren Failure-Modes.

Diese Aspekte gehören in **Integration-Tests** (separat, mit echtem API-Key,
manuell oder nightly ausgeführt) und in **Eval-Runs** mit Goldset.

## `operations/`: 90 %+

`operations/` (`add_review`, `refine`, `deprecate`) liegt zwischen Storage und
Creation:

- Deterministische Funktionen über Events.
- Keine LLM-Calls.
- Aber: nicht-triviale Business-Rules — "kann nicht zweimal deprecaten",
  "refine erzeugt neuen Entry + Deprecate-Event auf dem alten" usw.

Alle Business-Rules werden getestet, alle erwarteten Fehlerpfade auch. Die
fehlenden ~10 % sind tief verschachtelte Defensiv-Checks ("falls Storage-Layer
ein malformed Event zurückgibt") — Belt-and-Braces, die in der Praxis durch
die Storage-Tests bereits indirekt abgedeckt sind.

## Durchsetzung

In `features/goldens/pyproject.toml`:

```toml
[tool.coverage.report]
fail_under = 90  # paket-weiter Mindestwert
```

Pro-Modul-Schwellen werden in CI über separate `coverage report`-Aufrufe
erzwungen, z. B.:

```bash
coverage report --include='*/goldens/storage/*' --fail-under=95
coverage report --include='*/goldens/schemas/*' --fail-under=100
coverage report --include='*/goldens/operations/*' --fail-under=90
coverage report --include='*/goldens/creation/*' --fail-under=70
```

Alternativ als weiche Pflicht im Code-Review, falls die CI-Konfiguration zu
brüchig wird.
