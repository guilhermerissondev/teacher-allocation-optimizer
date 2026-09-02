import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { Job, ModuleBatch } from "../types";

const listModuleBatches = vi.fn();
vi.mock("../api", () => ({ listModuleBatches: () => listModuleBatches() }));

const { default: RoundPicker } = await import("./RoundPicker");

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "j1",
    upload_id: "u1",
    filename: "BASE_ANUAL_M54.xlsx",
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

const lote = {
  id: "b1",
  name: "Ano letivo 2026",
  criterion: "PERFIL_EXATO",
  profile: "PROVA_COMPLETA",
  margin_offers: null,
  require_optimal: true,
  time_limit_seconds: null,
  created_at: "2026-08-31T12:18:00+00:00",
  status: "CONCLUIDO",
  modules: [],
  totals: {
    modules: 4, runnable: 4, queued_or_running: 0, concluded: 4,
    offers: 0, allocated: 0, coverage_pct: 0,
  },
} as unknown as ModuleBatch;

describe("RoundPicker", () => {
  beforeEach(() => {
    listModuleBatches.mockReset();
    listModuleBatches.mockResolvedValue([lote]);
  });

  it("agrupa as rodadas pelo lote que as gerou", async () => {
    render(
      <RoundPicker
        label="Rodada analisada"
        jobs={[
          job({ id: "a", module: 54, batch_id: "b1" }),
          job({ id: "b", module: 53, batch_id: "b1" }),
          job({ id: "c", module: 52, batch_id: null }),
        ]}
        value="a"
        onChange={() => undefined}
      />,
    );

    // Um lote produz rodadas identicas em tudo menos o modulo: agrupar por
    // lote e o que devolve a diferenca entre elas.
    await waitFor(() => {
      const grupos = [...document.querySelectorAll("optgroup")].map((g) => g.label);
      expect(grupos[0]).toContain("Lote · Ano letivo 2026");
      expect(grupos[1]).toBe("Rodadas avulsas");
    });
    const opcoes = [...document.querySelectorAll("optgroup")].map((g) =>
      [...g.children].map((o) => o.textContent),
    );
    expect(opcoes[0]).toEqual(["Módulo 54 · rodada_001", "Módulo 53 · rodada_001"]);
    expect(opcoes[1]).toEqual(["Módulo 52 · rodada_001"]);
  });

  it("mostra o contexto completo da rodada escolhida fora do campo", async () => {
    render(
      <RoundPicker
        label="Rodada analisada"
        jobs={[job({ id: "a" })]}
        value="a"
        onChange={() => undefined}
      />,
    );

    // O que nao cabe na opcao vive na legenda, onde quebra em varias linhas
    // em vez de ser cortado pela largura do select.
    expect(await screen.findByText("RODADA-BASE")).toBeInTheDocument();
    expect(screen.getByText("Perfil da disciplina")).toBeInTheDocument();
    expect(screen.getByText("Prova completa")).toBeInTheDocument();
    expect(screen.getByTitle("BASE_ANUAL_M54.xlsx")).toBeInTheDocument();
  });

  it("continua utilizável quando a lista de lotes falha", async () => {
    listModuleBatches.mockRejectedValue(new Error("rede fora"));
    render(
      <RoundPicker
        label="Rodada analisada"
        jobs={[job({ id: "a", batch_id: "b1" })]}
        value="a"
        onChange={() => undefined}
      />,
    );

    // Sem o nome do lote o agrupamento perde o rotulo amigavel, mas o seletor
    // nao pode deixar de funcionar por causa disso.
    await waitFor(() => {
      expect(document.querySelector("optgroup")?.label).toContain("Sem nome");
    });
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("anuncia a lista vazia em vez de um campo mudo", async () => {
    render(
      <RoundPicker
        label="Rodada-base"
        jobs={[]}
        value=""
        onChange={() => undefined}
        emptyLabel="Execute uma rodada primeiro"
      />,
    );
    expect(await screen.findByText("Execute uma rodada primeiro")).toBeInTheDocument();
    // A busca de lotes resolve depois da montagem; esperar evita atualizacao
    // de estado fora de act e o aviso que mascara problemas reais.
    await waitFor(() => expect(listModuleBatches).toHaveBeenCalled());
  });
});
