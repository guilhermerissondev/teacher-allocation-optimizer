import type {
  AllocationPage,
  BatchChangeResult,
  BatchInspection,
  EligibilityCriterion,
  ExecutionProfile,
  ModuleBatch,
  DashboardData,
  DashboardFilters,
  InsightsData,
  Job,
  Scenario,
  ScenarioCatalog,
  ScenarioChange,
  ScenarioPolicy,
  ScenarioComparison,
  Study,
  StudyBaseline,
  StudyCatalog,
  StudyComparison,
  StudyModuleProjection,
  StudyPremiseResult,
  Summary,
  UploadResult,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `Erro ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail ?? message;
    } catch {
      // Mantém a mensagem HTTP quando a resposta não é JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function validateUpload(
  file: File,
  module: number,
  criterion: EligibilityCriterion,
  profile: ExecutionProfile,
  marginOffers: number | null,
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("module", String(module));
  form.append("criterion", criterion);
  form.append("profile", profile);
  if (profile === "MARGEM_ACEITA" && marginOffers) {
    form.append("margin_offers", String(marginOffers));
  }
  return request<UploadResult>("/api/uploads", { method: "POST", body: form });
}

export async function createJob(
  uploadId: string,
  confirmWarnings: boolean,
): Promise<Job> {
  return request<Job>("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      upload_id: uploadId,
      confirm_warnings: confirmWarnings,
      require_optimal: true,
      time_limit_seconds: null,
    }),
  });
}

/** Lê os módulos presentes em cada planilha antes de montar o lote. */
export async function inspectBatchFiles(files: File[]): Promise<BatchInspection> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return request<BatchInspection>("/api/batches/inspect", { method: "POST", body: form });
}

export async function createModuleBatch(
  files: File[],
  modules: number[],
  options: {
    name: string;
    criterion: EligibilityCriterion;
    profile: ExecutionProfile;
    marginOffers: number | null;
  },
): Promise<ModuleBatch> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("modules", modules.join(","));
  form.append("name", options.name);
  form.append("criterion", options.criterion);
  form.append("profile", options.profile);
  if (options.profile === "MARGEM_ACEITA" && options.marginOffers) {
    form.append("margin_offers", String(options.marginOffers));
  }
  return request<ModuleBatch>("/api/batches", { method: "POST", body: form });
}

export const listModuleBatches = () => request<ModuleBatch[]>("/api/batches");
export const deleteModuleBatch = (batchId: string) =>
  request<{ batch_id: string; deleted_rounds: number; deleted_scenarios: number; deleted_jobs: number; cleanup_pending: number }>(
    `/api/batches/${batchId}`,
    { method: "DELETE" },
  );
export const getModuleBatch = (batchId: string) =>
  request<ModuleBatch>(`/api/batches/${batchId}`);
export const runModuleBatch = (batchId: string, confirmWarnings: boolean) =>
  request<ModuleBatch>(`/api/batches/${batchId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm_warnings: confirmWarnings }),
  });

export const listJobs = () => request<Job[]>("/api/jobs");
export const resetPrimaryJobs = (scope: "latest" | "all") =>
  request<{ deleted_rounds: number; deleted_scenarios: number }>(`/api/jobs/primary?scope=${scope}`, { method: "DELETE" });
export const listAnalysisJobs = () => request<Job[]>("/api/analysis-jobs");
export const getJob = (jobId: string) => request<Job>(`/api/jobs/${jobId}`);
export const getSummary = (jobId: string) =>
  request<Summary>(`/api/jobs/${jobId}/summary`);
export const getDashboard = (jobId: string, filters?: DashboardFilters) => {
  const query = new URLSearchParams();
  if (filters) {
    Object.entries(filters).forEach(([key, values]) => {
      values.forEach((value) => query.append(key, value));
    });
  }
  const suffix = query.size ? `?${query}` : "";
  return request<DashboardData>(`/api/dashboard/${jobId}${suffix}`);
};
export const getInsights = (jobId: string) =>
  request<InsightsData>(`/api/insights/${jobId}`);

export const listScenarios = () => request<Scenario[]>("/api/scenarios");
export const resetSavedScenarios = (scope: "latest" | "all") =>
  request<{ deleted_scenarios: number }>(`/api/scenarios?scope=${scope}`, { method: "DELETE" });
export const getScenario = (scenarioId: string) =>
  request<Scenario>(`/api/scenarios/${scenarioId}`);
export const createScenario = (
  baselineJobId: string,
  name: string,
  description: string,
) => request<Scenario>("/api/scenarios", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ baseline_job_id: baselineJobId, name, description }),
});
export const getScenarioCatalog = (scenarioId: string) =>
  request<ScenarioCatalog>(`/api/scenarios/${scenarioId}/catalog`);
/**
 * Aplica a mesma premissa a várias entidades de uma vez.
 *
 * `new_value` define o mesmo valor para todos; `adjustment` soma horas à
 * CH_LETIVA de cada docente, preservando as diferenças de carga entre eles.
 */
export const addScenarioChangesBatch = (
  scenarioId: string,
  payload: {
    change_type: string;
    entity_type: string;
    field_name: string;
    row_numbers: number[];
    new_value?: string | number;
    adjustment?: number;
  },
) => request<BatchChangeResult>(`/api/scenarios/${scenarioId}/changes/batch`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});
export const deleteScenarioChange = (scenarioId: string, changeId: string) =>
  request<void>(`/api/scenarios/${scenarioId}/changes/${changeId}`, { method: "DELETE" });
export const addScenarioPolicy = (
  scenarioId: string,
  payload: {
    policy_type: string;
    target_type: string;
    target_value: string;
    configuration?: Record<string, string | number | boolean>;
  },
) => request<ScenarioPolicy>(`/api/scenarios/${scenarioId}/policies`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});
export const deleteScenarioPolicy = (scenarioId: string, policyId: string) =>
  request<void>(`/api/scenarios/${scenarioId}/policies/${policyId}`, { method: "DELETE" });
export const runScenario = (scenarioId: string) =>
  request<Job>(`/api/scenarios/${scenarioId}/runs`, { method: "POST" });
export const getScenarioComparison = (scenarioId: string) =>
  request<ScenarioComparison>(`/api/scenarios/${scenarioId}/comparison`);
export const promoteScenario = (scenarioId: string) =>
  request<Scenario>(`/api/scenarios/${scenarioId}/promote`, { method: "POST" });

export function getAllocations(
  jobId: string,
  page: number,
  status = "",
  search = "",
): Promise<AllocationPage> {
  const query = new URLSearchParams({ page: String(page), page_size: "25" });
  if (status) query.set("status", status);
  if (search) query.set("search", search);
  return request<AllocationPage>(`/api/jobs/${jobId}/allocations?${query}`);
}

export const artifactUrl = (jobId: string, key: string) =>
  `/api/jobs/${jobId}/artifacts/${key}`;

// ---------------------------------------------------------------------------
// Estudo em lote
// ---------------------------------------------------------------------------

/** Lotes com rodada concluída, elegíveis como base de um estudo. */
export const listStudyBaselines = () =>
  request<StudyBaseline[]>("/api/studies/baselines");

export const listStudies = () => request<Study[]>("/api/studies");

export const getStudy = (studyId: string) =>
  request<Study>(`/api/studies/${studyId}`);

export const createStudy = (
  batchId: string,
  modules: number[],
  name: string,
  description: string,
) => request<Study>("/api/studies", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ batch_id: batchId, modules, name, description }),
});

export const getStudyCatalog = (studyId: string) =>
  request<StudyCatalog>(`/api/studies/${studyId}/catalog`);

/** Reprojeta as premissas e devolve o efeito por módulo, sem executar nada. */
export const getStudyProjection = (studyId: string) =>
  request<{ modules: StudyModuleProjection[] }>(`/api/studies/${studyId}/projection`);

export const addStudyPremise = (
  studyId: string,
  payload: {
    premise_type: string;
    target_type: string;
    target_values: string[];
    field_name: string;
    new_value?: string | number;
    adjustment?: number;
  },
) => request<StudyPremiseResult>(`/api/studies/${studyId}/premises`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

export const deleteStudyPremise = (studyId: string, premiseId: string) =>
  request<void>(`/api/studies/${studyId}/premises/${premiseId}`, { method: "DELETE" });

export const runStudy = (studyId: string) =>
  request<Study>(`/api/studies/${studyId}/runs`, { method: "POST" });

export const getStudyComparison = (studyId: string) =>
  request<StudyComparison>(`/api/studies/${studyId}/comparison`);

export const deleteStudy = (studyId: string) =>
  request<{ study_id: string; deleted_scenarios: number }>(
    `/api/studies/${studyId}`,
    { method: "DELETE" },
  );
