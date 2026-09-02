import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import StudyEntityContext from "./StudyEntityContext";
import type { StudyCatalog, StudyOfferTarget } from "../types";

type StudyTeacher = StudyCatalog["teachers"][number];

const docente: StudyTeacher = {
  badge: "12345",
  name: "Ana Ribeiro",
  status: "ATIVO",
  job_function: "PROFESSOR TITULAR",
  teaching_capacity: 20,
  contracted_capacity: 40,
  manager: "Carlos Menezes",
  profile: "GESTÃO",
};

const curso: StudyOfferTarget = {
  code: "ADM",
  name: "Administração",
  course_code: "ADM",
  course_name: "Administração",
  modules: [
    { module: 51, offers: 4, unassigned: 1 },
    { module: 53, offers: 2, unassigned: 0 },
  ],
  days: ["SEGUNDA", "QUARTA"],
  times: ["19:00"],
  orders: ["1"],
  total_offers: 6,
  total_unassigned: 1,
};

describe("StudyEntityContext", () => {
  it("mostra o registro completo do docente sem exigir outra aba", () => {
    render(<StudyEntityContext teacher={docente} fieldName="STATUS" />);

    expect(screen.getByText("Ana Ribeiro")).toBeInTheDocument();
    expect(screen.getByText("12345")).toBeInTheDocument();
    expect(screen.getByText("PROFESSOR TITULAR")).toBeInTheDocument();
    expect(screen.getByText("Carlos Menezes")).toBeInTheDocument();
    expect(screen.getByText("20 h")).toBeInTheDocument();
    expect(screen.getByText("40 h")).toBeInTheDocument();
  });

  it("destaca o campo em edição com o valor atual ao lado do novo", () => {
    render(
      <StudyEntityContext teacher={docente} fieldName="STATUS" newValue="DEMITIDO" />,
    );

    expect(screen.getByText("DEMITIDO", { selector: "b" })).toBeInTheDocument();
    // O valor que sai fica riscado ao lado, para que a troca seja explícita.
    expect(screen.getByText("ATIVO", { selector: "s" })).toBeInTheDocument();
  });

  it("resolve o ajuste relativo de CH para onde o docente vai parar", () => {
    render(
      <StudyEntityContext
        teacher={docente}
        fieldName="CH_LETIVA"
        chMode="adjust"
        adjustment="-4"
      />,
    );

    expect(screen.getByText("16 h", { selector: "b" })).toBeInTheDocument();
  });

  it("resume o curso e diz em que módulos do estudo ele existe", () => {
    render(
      <StudyEntityContext
        target={curso}
        targetKind="COURSE"
        studyModules={[51, 52, 53]}
        fieldName="DIA_AULA"
        newValue="SEXTA"
      />,
    );

    expect(screen.getByText("Administração")).toBeInTheDocument();
    expect(screen.getByText("1 de 6 oferta(s) sem docente")).toBeInTheDocument();
    expect(screen.getByText("SEGUNDA / QUARTA", { selector: "s" })).toBeInTheDocument();
    expect(screen.getByText("SEXTA", { selector: "b" })).toBeInTheDocument();

    // O módulo em que o curso não existe precisa aparecer marcado: é ele que
    // explica a premissa "sem efeito" depois da simulação.
    expect(screen.getByText("não existe neste módulo")).toBeInTheDocument();
    expect(screen.getByText("4 oferta(s) · 1 sem docente")).toBeInTheDocument();
    expect(screen.getByText("2 oferta(s)")).toBeInTheDocument();
  });

  it("não renderiza nada sem alvo escolhido", () => {
    const { container } = render(<StudyEntityContext fieldName="STATUS" />);
    expect(container).toBeEmptyDOMElement();
  });
});
