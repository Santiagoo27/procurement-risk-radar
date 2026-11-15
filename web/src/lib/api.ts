import type { TargetScore } from "./data";

export const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  "https://procurement-risk-radar-9p25.onrender.com";

const DEFAULT_TIMEOUT_MS = 90_000;

export class ApiTimeout extends Error {}
export class ApiUnavailable extends Error {}
export class UnknownBuyer extends Error {}
export class ApiValidation extends Error {
  fields: Record<string, string>;

  constructor(fields: Record<string, string>) {
    super("Some fields are not valid.");
    this.fields = fields;
  }
}

export interface ContractInput {
  buyer_id: string;
  signed_at?: string;
  procurement_method?: string;
  contract_type?: string;
  award_value?: number;
  tender_budget?: number;
  planned_duration_days?: number;
  n_bidders?: number;
  supplier_is_natural_person?: boolean;
  extendable_clause?: boolean;
}

export interface ContractScore {
  value_addition: TargetScore;
  time_extension: TargetScore;
  warnings: string[];
}

export interface PredictResponse {
  bundle_version: string;
  disclaimer: string;
  results: ContractScore[];
}

export interface BuyerHit {
  buyer_id: string;
  buyer_name: string | null;
  buyer_department: string | null;
  buyer_city: string | null;
}

async function request(path: string, init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) throw new ApiTimeout("The model took too long to answer.");
    throw new ApiUnavailable(`Could not reach the model: ${String(error)}`);
  } finally {
    clearTimeout(timer);
  }
}

export async function wakeUp(timeoutMs = DEFAULT_TIMEOUT_MS): Promise<void> {
  const response = await request("/health", {}, timeoutMs);
  if (!response.ok) throw new ApiUnavailable(`The model answered HTTP ${response.status}.`);
}

export async function searchBuyers(q: string): Promise<BuyerHit[]> {
  const response = await request(`/buyers?q=${encodeURIComponent(q)}&limit=10`, {}, 30_000);
  if (!response.ok) return [];
  return (await response.json()) as BuyerHit[];
}

export async function predict(contract: ContractInput,
  { timeoutMs = DEFAULT_TIMEOUT_MS }: { timeoutMs?: number } = {}): Promise<PredictResponse> {
  const response = await request("/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contracts: [contract] }),
  }, timeoutMs);
  if (response.status === 404) throw new UnknownBuyer("This buyer is not in the model's data.");
  if (response.status === 422) {
    const body = (await response.json()) as { detail: { loc: (string | number)[]; msg: string }[] };
    const fields: Record<string, string> = {};
    for (const d of body.detail ?? []) fields[String(d.loc[d.loc.length - 1])] = d.msg;
    throw new ApiValidation(fields);
  }
  if (!response.ok) throw new ApiUnavailable(`The model answered HTTP ${response.status}.`);
  return (await response.json()) as PredictResponse;
}
