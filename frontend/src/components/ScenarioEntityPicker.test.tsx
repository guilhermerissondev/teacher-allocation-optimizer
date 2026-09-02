import { useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScenarioEntityPicker from "./ScenarioEntityPicker";
import type { ScenarioCatalog } from "../types";

type Teacher = ScenarioCatalog["teachers"][number];

/**
 * Base minima com o cruzamento que importa: cada cargo pratica um conjunto
 * proprio de CH letiva, que e exatamente o que as facetas devem revelar.
 */
function docente(
  row: number,
  nome: string,
  cargo: string,
  ch: number,
  status = "ATIVO",
  gestor = "Gestor 1",
): Teacher {
  return {
    row_number: row,
    badge: `${row}`.padStart(12, "0"),
    name: nome,
    status,
    job_function: cargo,
    teaching_capacity: ch,
    contracted_capacity: 40,
    manager: gestor,
    profile: "Gestão - Administração",
  };
}

const PRESENCIAL = "PROFESSOR DE ENSINO SUPERIOR PRESENCIAL";
const REGENTE = "PROFESSOR REGENTE";
const EAD = "PROFESSOR DE ENSINO SUPERIOR EAD";

const teachers: Teacher[] = [
  docente(1, "Ana", PRESENCIAL, 0),
  docente(2, "Bruno", PRESENCIAL, 0),
  docente(3, "Carla", REGENTE, 9),
  docente(4, "Diego", REGENTE, 20, "DEMITIDO"),
  docente(5, "Eva", EAD, 4, "ATIVO", "Gestor 2"),
];

function Harness() {
  const [selected, setSelected] = useState<number[]>([]);
  return (
    <ScenarioEntityPicker
      entityType="teacher"
      teachers={teachers}
      offers={[]}
      selected={selected}
      onSelectedChange={setSelected}
    />
  );
}

/** Abre a lista suspensa de um filtro e devolve o menu aberto. */
async function abrirFiltro(user: ReturnType<typeof userEvent.setup>, rotulo: string) {
  const grupo = screen.getByRole("group", { name: `Opções de ${rotulo}` });
  const menu = grupo.closest("details");
  if (!menu) throw new Error(`filtro ${rotulo} sem menu`);
  if (!menu.open) await user.click(menu.querySelector("summary") as HTMLElement);
  return grupo;
}

function opcoesDe(grupo: HTMLElement): string[] {
  return within(grupo)
    .queryAllByRole("checkbox")
    .map((caixa) => (caixa.closest("label")?.textContent ?? "").trim());
}

describe("ScenarioEntityPicker", () => {
  it("oferece todos os filtros como lista suspensa, sem chips nem intervalo", async () => {
    const { container } = render(<Harness />);
    for (const rotulo of ["CH letiva", "Cargo", "Status", "Gestor"]) {
      expect(screen.getByRole("group", { name: `Opções de ${rotulo}` })).toBeInTheDocument();
    }
    expect(container.querySelector(".entity-picker-chip")).toBeNull();
    expect(container.querySelector(".entity-picker-range")).toBeNull();
    expect(container.querySelector(".entity-picker-list")).toBeNull();
  });

  it("mostra a contagem de cada valor antes do clique", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const ch = await abrirFiltro(user, "CH letiva");
    // Ordenacao numerica: 0, 4, 9, 20 — nao alfabetica.
    expect(opcoesDe(ch)).toEqual(["0h · 2", "4h · 1", "9h · 1", "20h · 1"]);
  });

  it("restringe o cargo às opções que praticam a CH escolhida", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const ch = await abrirFiltro(user, "CH letiva");
    await user.click(within(ch).getByRole("checkbox", { name: /^0h/ }));

    const cargo = await abrirFiltro(user, "Cargo");
    // Só o Presencial tem alguém com 0h.
    expect(opcoesDe(cargo)).toEqual([`${PRESENCIAL} · 2`]);
  });

  it("restringe a CH às faixas que o cargo escolhido pratica", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const cargo = await abrirFiltro(user, "Cargo");
    await user.click(within(cargo).getByRole("checkbox", { name: new RegExp(`^${REGENTE}`) }));

    const ch = await abrirFiltro(user, "CH letiva");
    expect(opcoesDe(ch)).toEqual(["9h · 1", "20h · 1"]);
  });

  it("mantém as opções irmãs do próprio filtro após a primeira escolha", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const ch = await abrirFiltro(user, "CH letiva");
    await user.click(within(ch).getByRole("checkbox", { name: /^0h/ }));

    // A propria faceta fica fora do seu calculo: escolher 0h nao pode apagar
    // as outras faixas, senao nao havera como marcar uma segunda.
    expect(opcoesDe(await abrirFiltro(user, "CH letiva"))).toEqual([
      "0h · 2", "4h · 1", "9h · 1", "20h · 1",
    ]);
  });

  it("descarta a escolha que deixou de existir quando a base muda", async () => {
    // Por cliques essa situacao nao acontece: o cross-filtering ja impede a
    // combinacao impossivel. A poda protege o outro caminho — a base trocar
    // sob a selecao, como ao alternar entre docente e oferta ou ao recarregar
    // o catalogo de outra rodada-base.
    const user = userEvent.setup();
    function Trocavel() {
      const [selected, setSelected] = useState<number[]>([]);
      const [reduzida, setReduzida] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setReduzida(true)}>trocar base</button>
          <ScenarioEntityPicker
            entityType="teacher"
            teachers={reduzida ? teachers.filter((item) => item.teaching_capacity !== 0) : teachers}
            offers={[]}
            selected={selected}
            onSelectedChange={setSelected}
          />
        </>
      );
    }
    render(<Trocavel />);

    const ch = await abrirFiltro(user, "CH letiva");
    await user.click(within(ch).getByRole("checkbox", { name: /^0h/ }));
    expect(screen.getByText(/Selecione entre 2 registro/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "trocar base" }));

    // Sem a poda o filtro continuaria pedindo 0h numa base sem ninguem em 0h,
    // e o resultado ficaria em zero sem explicacao.
    expect(screen.getByText(/Selecione entre 3 registro/)).toBeInTheDocument();
    expect(opcoesDe(await abrirFiltro(user, "CH letiva"))).toEqual([
      "4h · 1", "9h · 1", "20h · 1",
    ]);
  });

  it("reduz os registros disponíveis conforme os filtros combinam", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByText(/Selecione entre 5 registro\(s\)/)).toBeInTheDocument();

    const status = await abrirFiltro(user, "Status");
    await user.click(within(status).getByRole("checkbox", { name: /^ATIVO/ }));
    expect(screen.getByText(/Selecione entre 4 registro\(s\)/)).toBeInTheDocument();
  });

  it("seleciona em lote apenas o que os filtros deixaram", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const cargo = await abrirFiltro(user, "Cargo");
    await user.click(within(cargo).getByRole("checkbox", { name: new RegExp(`^${PRESENCIAL}`) }));

    await user.click(screen.getByRole("button", { name: /Selecionar os 2 filtrados/ }));
    expect(screen.getByText(/selecionado\(s\) de 2 exibido\(s\)/)).toHaveTextContent("2 selecionado");
  });
});

describe("ScenarioEntityPicker com ofertas", () => {
  type Offer = ScenarioCatalog["offers"][number];

  function oferta(
    row: number,
    disciplina: string,
    curso: string,
    cluster: string,
    dia: string,
    ordem: string,
    situacao: string,
  ): Offer {
    return {
      row_number: row,
      course: curso,
      course_code: curso,
      course_name: curso,
      discipline_code: `D${row}`,
      discipline_name: disciplina,
      day: dia,
      time: "19:00",
      order: ordem,
      cluster,
      profile: "Gestão - Administração",
      baseline_status: situacao,
      baseline_teacher_badge: situacao === "ALOCADA" ? "000000000001" : "",
      baseline_teacher_name: situacao === "ALOCADA" ? "Ana" : "",
    } as Offer;
  }

  const offers: Offer[] = [
    oferta(2, "Contabilidade", "ADM", "GESTÃO", "SEGUNDA", "1ª", "ALOCADA"),
    oferta(3, "Anatomia", "ENF", "SAÚDE", "TERÇA", "2ª", "ALOCADA"),
    oferta(4, "Fisiologia", "ENF", "SAÚDE", "TERÇA", "ESTENDIDA", "NAO_ALOCADA"),
  ];

  function OfertasHarness() {
    const [selected, setSelected] = useState<number[]>([]);
    return (
      <ScenarioEntityPicker
        entityType="offer"
        teachers={[]}
        offers={offers}
        selected={selected}
        onSelectedChange={setSelected}
      />
    );
  }

  it("usa o mesmo controle suspenso nas cinco facetas de oferta", async () => {
    render(<OfertasHarness />);
    // O componente e o mesmo dos docentes, mas as facetas mudam por completo:
    // sem este teste o lado das ofertas so seria conferido a olho.
    for (const rotulo of ["Cluster", "Curso", "Dia", "Ordem", "Situação na base"]) {
      expect(screen.getByRole("group", { name: `Opções de ${rotulo}` })).toBeInTheDocument();
    }
  });

  it("cruza as facetas de oferta como faz com as de docente", async () => {
    const user = userEvent.setup();
    render(<OfertasHarness />);
    const cluster = await abrirFiltro(user, "Cluster");
    await user.click(within(cluster).getByRole("checkbox", { name: /^SAÚDE/ }));

    // So o curso ENF tem ofertas em SAUDE.
    expect(opcoesDe(await abrirFiltro(user, "Curso"))).toEqual(["ENF · 2"]);
    expect(opcoesDe(await abrirFiltro(user, "Ordem"))).toEqual([
      "2ª · 1", "ESTENDIDA · 1",
    ]);
    expect(screen.getByText(/Selecione entre 2 registro/)).toBeInTheDocument();
  });

  it("descreve a oferta com o docente da baseline na opcao", async () => {
    const user = userEvent.setup();
    render(<OfertasHarness />);
    const menu = screen.getByRole("group", { name: "Opções de Ofertas" });
    const detalhe = menu.closest("details") as HTMLDetailsElement;
    detalhe.open = true;
    const rotulos = within(menu).getAllByRole("checkbox").map(
      (caixa) => (caixa.closest("label")?.textContent ?? "").trim(),
    );
    expect(rotulos[0]).toContain("Contabilidade");
    expect(rotulos[0]).toContain("Ana");
    expect(rotulos[2]).toContain("sem docente");
    await user.click(within(menu).getAllByRole("checkbox")[2]);
    expect(screen.getByText(/selecionado\(s\) de 3 exibido\(s\)/)).toHaveTextContent("1 selecionado");
  });
});
