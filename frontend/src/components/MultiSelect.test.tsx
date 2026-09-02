import { useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MultiSelect from "./MultiSelect";

const perfis = [
  "Gestão - Administração",
  "Gestão - Recursos Humanos",
  "Saúde - Enfermagem",
  "Saúde - Nutrição",
  "Educação - Pedagogia",
  "Exatas - Matemática",
  "Exatas - Física",
  "Artes - Música",
  "Direito - Civil",
];

function Harness({ options = perfis }: { options?: string[] }) {
  const [values, setValues] = useState<string[]>([]);
  return (
    <MultiSelect
      label="Perfil"
      values={values}
      options={options.map((value) => ({ value, label: value }))}
      onChange={setValues}
    />
  );
}

function abrir() {
  const grupo = screen.getByRole("group", { name: "Opções de Perfil" });
  const menu = grupo.closest("details") as HTMLDetailsElement;
  menu.open = true;
  return grupo;
}

/** O texto do campo fechado, que resume a selecao. */
function resumo(): string {
  const grupo = screen.getByRole("group", { name: "Opções de Perfil" });
  return (grupo.closest("details")?.querySelector("summary")?.textContent ?? "").trim();
}

describe("MultiSelect", () => {
  it("resume a seleção no campo fechado", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByText("Todos")).toBeInTheDocument();

    const grupo = abrir();
    await user.click(within(grupo).getByRole("checkbox", { name: "Saúde - Enfermagem" }));
    // Um item mostra o proprio nome; a partir de dois, a contagem.
    expect(resumo()).toContain("Saúde - Enfermagem");

    await user.click(within(grupo).getByRole("checkbox", { name: "Saúde - Nutrição" }));
    expect(resumo()).toContain("2 selecionados");
    expect(resumo()).toContain("2/9");
  });

  it("busca ignorando acento e caixa", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    abrir();
    await user.type(screen.getByRole("searchbox"), "saude");

    const grupo = screen.getByRole("group", { name: "Opções de Perfil" });
    expect(within(grupo).getAllByRole("checkbox")).toHaveLength(2);
  });

  it("só oferece busca quando a lista passa de oito opções", () => {
    const { unmount } = render(<Harness options={perfis.slice(0, 7)} />);
    abrir();
    expect(screen.queryByRole("searchbox")).toBeNull();
    unmount();

    render(<Harness />);
    abrir();
    expect(screen.getByRole("searchbox")).toBeInTheDocument();
  });

  it("marcar em massa respeita o que a busca deixou visível", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    abrir();
    await user.type(screen.getByRole("searchbox"), "exatas");

    await user.click(screen.getByRole("button", { name: "Marcar 2 encontrado(s)" }));

    // O que a busca escondeu continua fora da selecao.
    expect(resumo()).toContain("2 selecionados");
  });

  it("limpa a seleção inteira, inclusive o que a busca esconde", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const grupo = abrir();
    await user.click(screen.getByRole("button", { name: "Marcar todos" }));
    expect(resumo()).toContain("9 selecionados");

    await user.type(screen.getByRole("searchbox"), "exatas");
    await user.click(screen.getByRole("button", { name: "Todos, sem restrição" }));

    expect(within(grupo).queryAllByRole("checkbox", { checked: true })).toHaveLength(0);
  });

  it("não perde a seleção ao desmarcar apenas um item", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const grupo = abrir();
    await user.click(screen.getByRole("button", { name: "Marcar todos" }));
    await user.click(within(grupo).getByRole("checkbox", { name: "Artes - Música" }));

    expect(resumo()).toContain("8 selecionados");
  });

  it("fecha com Esc e devolve o foco ao campo", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const grupo = screen.getByRole("group", { name: "Opções de Perfil" });
    const menu = grupo.closest("details") as HTMLDetailsElement;
    const resumoEl = menu.querySelector("summary") as HTMLElement;

    await user.click(resumoEl);
    expect(menu.open).toBe(true);

    await user.keyboard("{Escape}");

    // Um menu que cobre o formulario e so fecha com novo clique no resumo e
    // uma armadilha para quem navega por teclado.
    expect(menu.open).toBe(false);
    expect(document.activeElement).toBe(resumoEl);
  });

  it("fecha ao clicar fora do menu", async () => {
    const user = userEvent.setup();
    render(
      <>
        <button type="button">fora</button>
        <Harness />
      </>,
    );
    const grupo = screen.getByRole("group", { name: "Opções de Perfil" });
    const menu = grupo.closest("details") as HTMLDetailsElement;
    await user.click(menu.querySelector("summary") as HTMLElement);
    expect(menu.open).toBe(true);

    await user.click(screen.getByRole("button", { name: "fora" }));

    expect(menu.open).toBe(false);
  });

  it("desabilita o conjunto quando o formulário está em leitura", () => {
    render(
      <MultiSelect
        label="Perfil"
        values={[]}
        options={perfis.map((value) => ({ value, label: value }))}
        onChange={() => undefined}
        disabled
      />,
    );
    abrir();
    for (const caixa of screen.getAllByRole("checkbox")) {
      expect(caixa).toBeDisabled();
    }
  });
});
