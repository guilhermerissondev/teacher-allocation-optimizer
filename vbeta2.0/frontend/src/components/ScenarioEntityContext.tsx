import type { ScenarioCatalog } from "../types";

type Offer = ScenarioCatalog["offers"][number];
type Teacher = ScenarioCatalog["teachers"][number];

/** Campo do formulário -> propriedade correspondente no registro. */
const OFFER_FIELD_MAP: Record<string, keyof Offer> = {
  DIA_AULA: "day",
  "HORÁRIO": "time",
  ORDEM: "order",
  PERFIL_DISCIPLINA: "profile",
};

const TEACHER_FIELD_MAP: Record<string, keyof Teacher> = {
  STATUS: "status",
  CH_LETIVA: "teaching_capacity",
  PERFIL_DISCIPLINA: "profile",
};

/**
 * Valor que o campo tem hoje na rodada-base, normalizado para comparação.
 *
 * Fica aqui, junto dos mapas de campo, porque quem compara e quem exibe
 * precisam concordar. Manter as duas leituras em arquivos diferentes foi o que
 * deixou, antes, a legenda do gráfico divergir da barra.
 */
export function valorAtualDoCampo(
  entidade: Offer | Teacher | null | undefined,
  fieldName: string,
): string | null {
  if (!entidade) return null;
  const chave = "name" in entidade
    ? TEACHER_FIELD_MAP[fieldName]
    : OFFER_FIELD_MAP[fieldName];
  if (!chave) return null;
  return String((entidade as Record<string, unknown>)[chave] ?? "").trim();
}

/** Comparação insensível a caixa e a espaços repetidos. */
export function mesmoValor(atual: string | null, novo: string | number): boolean {
  if (atual === null) return false;
  const a = atual.replace(/\s+/g, " ").trim().toLocaleUpperCase("pt-BR");
  const b = String(novo ?? "").replace(/\s+/g, " ").trim().toLocaleUpperCase("pt-BR");
  if (a === "" || b === "") return false;
  const numA = Number(a);
  const numB = Number(b);
  if (!Number.isNaN(numA) && !Number.isNaN(numB)) return numA === numB;
  return a === b;
}

function vazio(valor: unknown) {
  const texto = String(valor ?? "").trim();
  return texto === "" ? "—" : texto;
}

type Linha = { rotulo: string; valor: string; chave?: string };

function linhasDaOferta(offer: Offer): Linha[] {
  return [
    { rotulo: "Curso", valor: vazio(offer.course_name || offer.course) },
    { rotulo: "Código do curso", valor: vazio(offer.course_code) },
    { rotulo: "Disciplina", valor: vazio(offer.discipline_name) },
    { rotulo: "Código", valor: vazio(offer.discipline_code) },
    { rotulo: "Dia", valor: vazio(offer.day), chave: "day" },
    { rotulo: "Horário", valor: vazio(offer.time), chave: "time" },
    { rotulo: "Ordem", valor: vazio(offer.order), chave: "order" },
    { rotulo: "Cluster", valor: vazio(offer.cluster) },
    { rotulo: "Perfil", valor: vazio(offer.profile), chave: "profile" },
    { rotulo: "Linha na planilha", valor: String(offer.row_number) },
  ];
}

function linhasDoDocente(teacher: Teacher): Linha[] {
  return [
    { rotulo: "Chapa", valor: vazio(teacher.badge) },
    { rotulo: "Função", valor: vazio(teacher.job_function) },
    { rotulo: "Status", valor: vazio(teacher.status), chave: "status" },
    {
      rotulo: "CH letiva",
      valor: `${teacher.teaching_capacity} h`,
      chave: "teaching_capacity",
    },
    { rotulo: "Perfil", valor: vazio(teacher.profile), chave: "profile" },
    { rotulo: "Linha na planilha", valor: String(teacher.row_number) },
  ];
}

/**
 * Mostra o registro completo da entidade escolhida.
 *
 * Decidir "mudar a ORDEM desta disciplina" exige saber em que dia e horário ela
 * está, a que cluster pertence e se já tem docente — informação que existe no
 * catálogo desde sempre, mas que a lista suspensa não cabia. O campo em edição
 * aparece destacado, com o valor atual ao lado do novo.
 */
export default function ScenarioEntityContext({
  offer,
  teacher,
  fieldName,
  newValue,
}: {
  offer?: Offer | null;
  teacher?: Teacher | null;
  fieldName?: string;
  newValue?: string | number;
}) {
  if (!offer && !teacher) return null;

  const linhas = offer ? linhasDaOferta(offer) : linhasDoDocente(teacher!);
  const chaveEditada = offer
    ? OFFER_FIELD_MAP[fieldName ?? ""]
    : TEACHER_FIELD_MAP[fieldName ?? ""];
  const novo = String(newValue ?? "").trim();

  const alocada = offer?.baseline_status === "ALOCADA";

  return (
    <div className="entity-context" aria-live="polite">
      <div className="entity-context-head">
        <strong>{offer ? offer.discipline_name : teacher!.name}</strong>
        {offer && (
          <span className={`pill-state ${alocada ? "is-allocated" : "is-open"}`}>
            {alocada
              ? `Alocada · ${offer.baseline_teacher_name || "docente não informado"}`
              : "Sem docente na rodada-base"}
          </span>
        )}
        {teacher && (
          <span
            className={`pill-state ${
              teacher.status.trim().toUpperCase() === "ATIVO" ? "is-allocated" : "is-open"
            }`}
          >
            {vazio(teacher.status)}
          </span>
        )}
      </div>

      <dl className="entity-context-grid">
        {linhas.map((linha) => {
          const editando = Boolean(chaveEditada) && linha.chave === chaveEditada;
          return (
            <div
              key={linha.rotulo}
              className={editando ? "is-editing" : undefined}
            >
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
    </div>
  );
}
