import { describe, expect, it } from "vitest";
import {
  criterionLabel,
  formatRoundOptionLabel,
  jobContextLabel,
  profileLabel,
} from "./jobPresentation";
import type { Job } from "./types";

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "j1",
    upload_id: "u1",
    filename: "BASE_DEMONSTRACAO_ANONIMIZADA_LOTE_ANUAL_M54.xlsx",
    module: 54,
    status: "CONCLUIDA",
    message: "",
    validation_status: "APROVADO",
    require_optimal: true,
    time_limit_seconds: null,
    kind: "PRIMARY",
    batch_id: null,
    criterion: "PERFIL_EXATO",
    profile: "PROVA_COMPLETA",
    margin_offers: null,
    scenario_id: null,
    is_official: false,
    round: "rodada_001",
    exit_code: 0,
    created_at: "2026-08-31T12:18:00+00:00",
    updated_at: "2026-08-31T12:18:00+00:00",
    history: [],
    terminal: true,
    ...overrides,
  } as Job;
}

describe("formatRoundOptionLabel", () => {
  it("guarda só o que distingue uma rodada da outra", () => {
    // Um lote gera rodadas identicas em criterio, perfil, data e arquivo: o
    // que as separa e o modulo e o numero da rodada. Tudo o mais no rotulo so
    // faria o select cortar justamente a parte util.
    expect(formatRoundOptionLabel(job())).toBe("Módulo 54 · rodada_001");
  });

  it("cabe numa largura de campo estreita", () => {
    // O rotulo antigo concatenava contexto, criterio, perfil, rodada, data e
    // arquivo — passava de 140 caracteres e era cortado em todas as abas.
    const antigo = [
      jobContextLabel(job()), `Módulo ${job().module}`, criterionLabel(job()),
      profileLabel(job()), job().round, job().filename,
    ].join(" · ");
    expect(antigo.length).toBeGreaterThan(100);
    expect(formatRoundOptionLabel(job()).length).toBeLessThan(40);
  });

  it("marca cenário e resultado oficial", () => {
    expect(formatRoundOptionLabel(job({ kind: "SCENARIO" }))).toBe(
      "Cenário · Módulo 54 · rodada_001",
    );
    expect(formatRoundOptionLabel(job({ is_official: true }))).toBe(
      "★ Módulo 54 · rodada_001",
    );
  });

  it("não quebra quando a rodada ainda não tem número", () => {
    expect(formatRoundOptionLabel(job({ round: null }))).toBe("Módulo 54 · sem rodada");
  });
});

describe("rótulos de contexto", () => {
  it("distingue rodada-base, cenário e oficial", () => {
    expect(jobContextLabel(job())).toBe("RODADA-BASE");
    expect(jobContextLabel(job({ is_official: true }))).toBe("OFICIAL · RODADA-BASE");
    expect(jobContextLabel(job({ kind: "SCENARIO" }))).toBe("SIMULAÇÃO");
    expect(jobContextLabel(job({ kind: "SCENARIO", is_official: true }))).toBe(
      "OFICIAL · CENÁRIO",
    );
  });

  it("traduz critério e perfil, e devolve o código cru quando não conhece", () => {
    expect(criterionLabel(job())).toBe("Perfil da disciplina");
    expect(profileLabel(job())).toBe("Prova completa");
    expect(criterionLabel(job({ criterion: "INVENTADO" as Job["criterion"] }))).toBe(
      "INVENTADO",
    );
  });
});
