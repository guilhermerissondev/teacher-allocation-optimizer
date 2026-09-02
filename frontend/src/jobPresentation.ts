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

/**
 * Rotulo curto da opcao no seletor de rodadas.
 *
 * Um lote gera uma rodada por modulo, identicas em criterio, perfil, data e
 * arquivo; o que as separa e o modulo e o numero da rodada. Deixar so isso na
 * opcao evita que o select corte justamente a parte que distingue as rodadas.
 */
export function formatRoundOptionLabel(job: Job) {
  const round = job.round ?? "sem rodada";
  const scope = job.kind === "SCENARIO" ? "Cenário · " : "";
  const official = job.is_official ? "★ " : "";
  return `${official}${scope}Módulo ${job.module} · ${round}`;
}
