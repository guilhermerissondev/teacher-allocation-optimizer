import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import SelectionSummary, { ResumoItem } from "./SelectionSummary";

function docente(
  chave: string,
  nome: string,
  status: string,
  ch: string,
  destino?: string,
): ResumoItem {
  return {
    chave,
    titulo: `${nome} · ${chave}`,
    selo: { texto: status, tom: status === "ATIVO" ? "ok" : "atencao" },
    campos: [
      { rotulo: "Cargo", valor: "PROFESSOR TITULAR" },
      { rotulo: "Status", valor: status },
      { rotulo: "CH letiva", valor: ch, editando: true, destino },
      { rotulo: "Gestor", valor: "Carlos Menezes" },
    ],
  };
}

const itens = [
  docente("111", "Ana Ribeiro", "ATIVO", "20 h de 40 h"),
  docente("222", "Bruno Alves", "DEMITIDO", "12 h de 40 h"),
];

const base = { total: 2, substantivo: "docentes", itens };

describe("SelectionSummary", () => {
  it("não aparece com um alvo só: aí quem responde é o painel do registro", () => {
    const { container } = render(<SelectionSummary {...base} total={1} itens={[itens[0]]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("dá uma faixa própria a cada alvo, em vez de empilhar o agregado", () => {
    render(<SelectionSummary {...base} />);

    const faixas = screen.getAllByRole("listitem");
    expect(faixas).toHaveLength(2);
    expect(within(faixas[0]).getByText("Ana Ribeiro · 111")).toBeInTheDocument();
    expect(within(faixas[1]).getByText("Bruno Alves · 222")).toBeInTheDocument();
  });

  it("repete os campos do registro em cada faixa", () => {
    render(<SelectionSummary {...base} />);

    const faixas = screen.getAllByRole("listitem");
    // Cada faixa carrega o proprio valor: e isso que permite reconhecer o
    // docente sem voltar para outra aba.
    expect(within(faixas[0]).getByText("20 h de 40 h")).toBeInTheDocument();
    expect(within(faixas[1]).getByText("12 h de 40 h")).toBeInTheDocument();
    expect(within(faixas[0]).getAllByText("ATIVO").length).toBeGreaterThan(0);
    expect(within(faixas[1]).getAllByText("DEMITIDO").length).toBeGreaterThan(0);
  });

  it("mostra o destino de cada alvo separadamente", () => {
    // O ajuste relativo de CH leva cada docente a um numero diferente; o
    // destino por faixa e o que torna isso legivel antes de enviar.
    render(
      <SelectionSummary
        {...base}
        itens={[
          docente("111", "Ana Ribeiro", "ATIVO", "20 h de 40 h", "24 h"),
          docente("222", "Bruno Alves", "DEMITIDO", "12 h de 40 h", "16 h"),
        ]}
      />,
    );

    const faixas = screen.getAllByRole("listitem");
    expect(within(faixas[0]).getByText("20 h de 40 h", { selector: "s" })).toBeInTheDocument();
    expect(within(faixas[0]).getByText("24 h", { selector: "b" })).toBeInTheDocument();
    expect(within(faixas[1]).getByText("16 h", { selector: "b" })).toBeInTheDocument();
  });

  it("resume o conjunto no cabeçalho e avisa sobre premissa sem efeito", () => {
    render(
      <SelectionSummary
        {...base}
        destaque={{ texto: "1 ativo(s) · 1 fora de atividade", tom: "atencao" }}
        aviso="1 de 2 já usam ATIVO em STATUS e serão ignorados."
      />,
    );

    expect(screen.getByText("2 docentes selecionados")).toBeInTheDocument();
    expect(screen.getByText("1 ativo(s) · 1 fora de atividade")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("serão ignorados");
  });
});
