import { CRITERION_LABELS, PROFILE_LABELS } from "./types";
import type { Job } from "./types";

export function formatJobDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export function jobContextLabel(job: Job) {
  if (job.kind === "SCENARIO") return job.is_official ? "OFICIAL · CENÁRIO" : "SIMULAÇÃO";
  return job.is_official ? "OFICIAL · RODADA-BASE" : "RODADA-BASE";
}

export function criterionLabel(job: Job) {
  return CRITERION_LABELS[job.criterion] ?? job.criterion;
}

export function profileLabel(job: Job) {
  return PROFILE_LABELS[job.profile] ?? job.profile;
}

export function formatAnalysisJobLabel(job: Job) {
  const round = job.round ?? "Sem número de rodada";
  // O critério entra no rótulo porque rodadas de métodos diferentes não são
  // comparáveis entre si, e a seleção acontece por esta lista.
  return `${jobContextLabel(job)} · Módulo ${job.module} · ${criterionLabel(job)} · ${profileLabel(job)} · ${round} · ${formatJobDate(job.created_at)} · ${job.filename}`;
}
