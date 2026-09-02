import type { StudyCatalog, StudyOfferTarget } from "../types";

type StudyTeacher = StudyCatalog["teachers"][number];

/**
 * Registro completo do alvo escolhido no estudo em lote.
 *
 * O modo "um módulo" já mostrava o registro inteiro ao selecionar uma entidade;
 * o lote mostrava só a linha resumida da lista suspensa, e conferir a CH de um
 * docente ou as lacunas de um curso obrigava a voltar em outra aba. O painel é
 * o mesmo em espírito, mas o alvo aqui vale para o ano inteiro: em vez da linha
 * da planilha, ele responde em que módulos o alvo existe e o que já falta em
 * cada um.
 */

/** Campo do formulário -> propriedade do docente. */
const TEACHER_FIELD_MAP: Record<string, keyof StudyTeacher> = {
  STATUS: "status",
  CH_LETIVA: "teaching_capacity",
  PERFIL_DISCIPLINA: "profile",
};

/** Campo do formulário -> lista praticada da oferta. */
const OFFER_FIELD_MAP: Record<string, keyof StudyOfferTarget> = {
  DIA_AULA: "days",
  "HORÁRIO": "times",
  ORDEM: "orders",
};

function vazio(valor: unknown) {
  const texto = String(valor ?? "").trim();
  return texto === "" ? "—" : texto;
}

function lista(valores: string[] | undefined) {
  const limpos = (valores ?? []).map((item) => item.trim()).filter(Boolean);
  return limpos.length ? limpos.join(" / ") : "—";
}

type Linha = { rotulo: string; valor: string; chave?: string };

function linhasDoDocente(teacher: StudyTeacher): Linha[] {
  return [
    { rotulo: "Chapa", valor: vazio(teacher.badge) },
    { rotulo: "Cargo", valor: vazio(teacher.job_function) },
    { rotulo: "Status", valor: vazio(teacher.status), chave: "status" },
    {
      rotulo: "CH letiva",
      valor: `${teacher.teaching_capacity} h`,
      chave: "teaching_capacity",
    },
    {
      rotulo: "Teto contratado",
      valor: teacher.contracted_capacity !== null ? `${teacher.contracted_capacity} h` : "—",
    },
    { rotulo: "Gestor", valor: vazio(teacher.manager) },
    { rotulo: "Perfil", valor: vazio(teacher.profile), chave: "profile" },
  ];
}

function linhasDaOferta(target: StudyOfferTarget, kind: "COURSE" | "DISCIPLINE"): Linha[] {
  const linhas: Linha[] = [
    { rotulo: kind === "COURSE" ? "Código do curso" : "Código", valor: vazio(target.code) },
  ];
  if (kind === "DISCIPLINE") {
    linhas.push({ rotulo: "Curso", valor: vazio(target.course_name || target.course_code) });
  }
  linhas.push(
    { rotulo: "Ofertas no ano", valor: String(target.total_offers) },
    { rotulo: "Sem alocação", valor: String(target.total_unassigned) },
    { rotulo: "Módulos", valor: lista(target.modules.map((row) => `M${row.module}`)) },
    { rotulo: "Dias praticados", valor: lista(target.days), chave: "days" },
    { rotulo: "Horários praticados", valor: lista(target.times), chave: "times" },
    { rotulo: "Ordens praticadas", valor: lista(target.orders), chave: "orders" },
  );
  return linhas;
}

/**
 * Texto do valor novo, já resolvido para a forma como o campo é editado.
 *
 * A CH letiva aceita as duas formas — definir o valor ou somar horas — e a
 * segunda só faz sentido ao lado da carga atual do docente, senão "-4h" não
 * diz onde o docente vai parar.
 */
function novoValorDoDocente(
  teacher: StudyTeacher,
  fieldName: string,
  newValue: string,
  chMode: "set" | "adjust",
  adjustment: string,
): string {
  if (fieldName === "CH_LETIVA" && chMode === "adjust") {
    const delta = Number(adjustment);
    if (adjustment.trim() === "" || Number.isNaN(delta) || delta === 0) return "";
    const destino = Number(teacher.teaching_capacity ?? 0) + delta;
    return `${destino} h`;
  }
  const texto = String(newValue ?? "").trim();
  if (texto === "") return "";
  return fieldName === "CH_LETIVA" ? `${texto} h` : texto;
}

export default function StudyEntityContext({
  teacher,
  target,
  targetKind = "COURSE",
  studyModules = [],
  fieldName,
  newValue = "",
  chMode = "set",
  adjustment = "",
}: {
  teacher?: StudyTeacher | null;
  target?: StudyOfferTarget | null;
  targetKind?: "COURSE" | "DISCIPLINE";
  /** Módulos que o estudo vai simular, para marcar o alcance real do alvo. */
  studyModules?: number[];
  fieldName?: string;
  newValue?: string;
  chMode?: "set" | "adjust";
  adjustment?: string;
}) {
  if (!teacher && !target) return null;

  const linhas = teacher ? linhasDoDocente(teacher) : linhasDaOferta(target!, targetKind);
  const chaveEditada = teacher
    ? TEACHER_FIELD_MAP[fieldName ?? ""]
    : OFFER_FIELD_MAP[fieldName ?? ""];
  const novo = teacher
    ? novoValorDoDocente(teacher, fieldName ?? "", newValue, chMode, adjustment)
    : String(newValue ?? "").trim();

  const ativo = teacher ? teacher.status.trim().toLocaleUpperCase("pt-BR") === "ATIVO" : false;
  const semLacuna = target ? target.total_unassigned === 0 : false;

  // Em que módulos do estudo o alvo realmente aparece. Um curso que só existe
  // em dois dos seis módulos simulados explica sozinho por que a premissa vai
  // ficar "sem efeito" nos outros quatro.
  type ModuleRow = StudyOfferTarget["modules"][number];
  const porModulo = new Map<number, ModuleRow>(
    (target?.modules ?? []).map((row): [number, ModuleRow] => [row.module, row]),
  );
  const modulosExibidos = studyModules.length
    ? studyModules
    : target?.modules.map((row) => row.module) ?? [];

  return (
    <div className="entity-context" aria-live="polite">
      <div className="entity-context-head">
        <strong>{teacher ? teacher.name : target!.name}</strong>
        {teacher && (
          <span className={`pill-state ${ativo ? "is-allocated" : "is-open"}`}>
            {vazio(teacher.status)}
          </span>
        )}
        {target && (
          <span className={`pill-state ${semLacuna ? "is-allocated" : "is-open"}`}>
            {semLacuna
              ? `${target.total_offers} oferta(s) · tudo alocado`
              : `${target.total_unassigned} de ${target.total_offers} oferta(s) sem docente`}
          </span>
        )}
      </div>

      <dl className="entity-context-grid">
        {linhas.map((linha) => {
          const editando = Boolean(chaveEditada) && linha.chave === chaveEditada;
          return (
            <div key={linha.rotulo} className={editando ? "is-editing" : undefined}>
              <dt>{linha.rotulo}</dt>
              <dd>
                {editando && novo !== "" ? (
                  <>
                    <s>{linha.valor}</s>
                    <span aria-hidden="true"> → </span>
                    <b>{novo}</b>
                    <span className="sr-only">
                      {` alterado de ${linha.valor} para ${novo}`}
                    </span>
                  </>
                ) : (
                  linha.valor
                )}
              </dd>
            </div>
          );
        })}
      </dl>

      {target && modulosExibidos.length > 0 && (
        <div className="entity-context-modules">
          <span className="entity-context-modules-label">Presença por módulo</span>
          <ul>
            {modulosExibidos.map((modulo) => {
              const row = porModulo.get(modulo);
              return (
                <li key={modulo} className={row ? (row.unassigned ? "has-gap" : "is-full") : "is-absent"}>
                  <strong>M{modulo}</strong>
                  <small>
                    {row
                      ? `${row.offers} oferta(s)${row.unassigned ? ` · ${row.unassigned} sem docente` : ""}`
                      : "não existe neste módulo"}
                  </small>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
