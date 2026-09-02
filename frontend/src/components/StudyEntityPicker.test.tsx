import { useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StudyEntityPicker, { StudyFacetDef, StudyTarget } from "./StudyEntityPicker";

/**
 * Cursos como o estudo os enxerga: uma chave de negócio que existe em alguns
 * módulos e não em outros. É esse eixo que o seletor do cenário avulso não tem,
 * porque lá tudo vive dentro de um módulo só.
 */
function curso(
  code: string,
  name: string,
  modules: string[],
  days: string[],
  comLacuna: boolean,
): StudyTarget {
  return {
    key: code,
    label: `${name} (${code})`,
    detail: modules.join(" "),
    facets: {
      module: modules,
      day: days,
      gap: [comLacuna ? "Com lacuna na base" : "Totalmente alocado"],
    },
  };
}

const targets: StudyTarget[] = [
  curso("ADM", "Administração", ["M51", "M52", "M53", "M54"], ["SEGUNDA"], true),
  curso("ENF", "Enfermagem", ["M51", "M52"], ["TERÇA"], true),
  curso("AGR", "Agronomia", ["M53", "M54"], ["SEGUNDA", "QUINTA"], false),
  curso("DIR", "Direito", ["M51"], ["QUINTA"], false),
];

const facetDefs: StudyFacetDef[] = [
  { key: "module", label: "Existe no módulo" },
  { key: "gap", label: "Situação na base" },
  { key: "day", label: "Dia praticado" },
];

function Harness({ items = targets }: { items?: StudyTarget[] }) {
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <StudyEntityPicker
      label="Cursos"
      targets={items}
      facetDefs={facetDefs}
      selected={selected}
      onSelectedChange={setSelected}
    />
  );
}

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

describe("StudyEntityPicker", () => {
  it("conta um alvo em cada módulo em que ele existe", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    // ADM está nos quatro; ENF em dois; AGR em dois; DIR só no 51.
    expect(opcoesDe(await abrirFiltro(user, "Existe no módulo"))).toEqual([
      "M51 · 3", "M52 · 2", "M53 · 2", "M54 · 2",
    ]);
  });

  it("restringe os dias aos cursos que existem no módulo escolhido", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const modulos = await abrirFiltro(user, "Existe no módulo");
    await user.click(within(modulos).getByRole("checkbox", { name: /^M54/ }));

    // No módulo 54 só existem ADM (segunda) e AGR (segunda e quinta).
    expect(opcoesDe(await abrirFiltro(user, "Dia praticado"))).toEqual([
      "QUINTA · 1", "SEGUNDA · 2",
    ]);
  });

  it("cruza a lacuna com o módulo, que é a pergunta do estudo de agenda", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const lacuna = await abrirFiltro(user, "Situação na base");
    await user.click(within(lacuna).getByRole("checkbox", { name: /^Com lacuna/ }));

    // Só ADM e ENF têm lacuna, e ENF não chega ao 53 nem ao 54.
    expect(opcoesDe(await abrirFiltro(user, "Existe no módulo"))).toEqual([
      "M51 · 2", "M52 · 2", "M53 · 1", "M54 · 1",
    ]);
  });

  it("mantém as opções irmãs do próprio filtro após a primeira escolha", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const modulos = await abrirFiltro(user, "Existe no módulo");
    await user.click(within(modulos).getByRole("checkbox", { name: /^M51/ }));

    expect(opcoesDe(await abrirFiltro(user, "Existe no módulo"))).toEqual([
      "M51 · 3", "M52 · 2", "M53 · 2", "M54 · 2",
    ]);
  });

  it("seleciona de uma vez os alvos que sobraram do filtro", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const lacuna = await abrirFiltro(user, "Situação na base");
    await user.click(within(lacuna).getByRole("checkbox", { name: /^Com lacuna/ }));

    await user.click(screen.getByRole("button", { name: /Selecionar os 2 filtrados/ }));
    expect(screen.getByText(/selecionado\(s\) de 2 exibido\(s\)/)).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("omite o filtro que tem um valor só e não restringe nada", async () => {
    render(<Harness items={[
      curso("ADM", "Administração", ["M51"], ["SEGUNDA"], true),
      curso("ENF", "Enfermagem", ["M51"], ["TERÇA"], true),
    ]} />);
    // Todos no mesmo módulo e todos com lacuna: só o dia separa alguma coisa.
    expect(screen.queryByRole("group", { name: "Opções de Existe no módulo" })).toBeNull();
    expect(screen.queryByRole("group", { name: "Opções de Situação na base" })).toBeNull();
    expect(screen.getByRole("group", { name: "Opções de Dia praticado" })).toBeInTheDocument();
  });
});
