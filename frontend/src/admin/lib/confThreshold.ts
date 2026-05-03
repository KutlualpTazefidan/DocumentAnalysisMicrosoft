// frontend/src/admin/lib/confThreshold.ts
// Per-doc confidence threshold state: a doc default plus per-page overrides.

export interface ConfThresholdState {
  default: number;
  perPage: Record<number, number>;
}

const DEFAULT_CONF = 0.70;

function storageKey(slug: string): string {
  return `segment.confThreshold.${slug}`;
}

export function loadConf(slug: string): ConfThresholdState {
  try {
    const raw = localStorage.getItem(storageKey(slug));
    if (!raw) return { default: DEFAULT_CONF, perPage: {} };
    const parsed = JSON.parse(raw) as Partial<ConfThresholdState>;
    return {
      default: typeof parsed.default === "number" ? parsed.default : DEFAULT_CONF,
      perPage: parsed.perPage && typeof parsed.perPage === "object" ? parsed.perPage : {},
    };
  } catch {
    return { default: DEFAULT_CONF, perPage: {} };
  }
}

export function saveConf(slug: string, state: ConfThresholdState): void {
  localStorage.setItem(storageKey(slug), JSON.stringify(state));
}

export function effectiveThreshold(state: ConfThresholdState, page: number): number {
  return state.perPage[page] ?? state.default;
}

export function setPageThreshold(slug: string, page: number, value: number): ConfThresholdState {
  const state = loadConf(slug);
  const next: ConfThresholdState = { ...state, perPage: { ...state.perPage, [page]: value } };
  saveConf(slug, next);
  return next;
}

export function setDefaultThreshold(slug: string, value: number): ConfThresholdState {
  const state = loadConf(slug);
  const next: ConfThresholdState = { ...state, default: value };
  saveConf(slug, next);
  return next;
}

export function clearPageOverride(slug: string, page: number): ConfThresholdState {
  const state = loadConf(slug);
  const { [page]: _removed, ...rest } = state.perPage;
  const next: ConfThresholdState = { ...state, perPage: rest };
  saveConf(slug, next);
  return next;
}
