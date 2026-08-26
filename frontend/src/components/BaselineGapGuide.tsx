import type { Summary } from "../types";

/**
 * Cada motivo de pendência tem um movimento que o ataca. Sem isso, escolher
 * entre os seis movimentos é chute: a tela mostrava quantas ofertas ficaram
 * sem docente, mas não por quê — e é o porquê que decide o movimento.
 */
const MOTIVOS: Record<string, { rotulo: string; movimento: string }> = {
  SEM_DOCENTE_COM_PERFIL_E_CARGA: {
    rotulo: "Sem docente com perfil compatível e carga livre",
    movimento: "Ampliar compatibilidade ou Alocar docentes do cluster",
  },
  CAPACIDADE_LETIVA_ESGOTADA: {
    rotulo: "Capacidade letiva esgotada",
    movimento: "Reforçar capacidade",
  },
  CHOQUE_DE_HORARIO: {
    rotulo: "Choque de horário",
    movimento: "Reorganizar agenda",
  },
  CAPACIDADE_E_HORARIO_COMBINADOS: {
    rotulo: "Capacidade e horário combinados",
    movimento: "Reforçar capacidade e reorganizar agenda",
  },
  AGENDA_INVALIDA: {
    rotulo: "Agenda inválida na origem",
    movimento: "Reorganizar agenda",
  },
};

export default function BaselineGapGuide({ summary }: { summary: Summary | null }) {
  if (!summary) return null;

  const motivos = Object.entries(summary.unassigned_reasons ?? {})
    .filter(([, total]) => total > 0)
    .sort((a, b) => b[1] - a[1]);

  if (!motivos.length) {
    return (
      <section className="gap-guide is-clean" aria-label="Diagnóstico da rodada-base">
        <div className="gap-guide-head">
          <strong>A rodada-base não tem pendências</strong>
          <span>Todas as ofertas receberam docente.</span>
        </div>
        <p>
          Cenários aqui servem para testar alternativas de distribuição, não para
          recuperar lacunas — não há lacuna a recuperar.
        </p>
      </section>
    );
  }

  const total = motivos.reduce((soma, [, valor]) => soma + valor, 0);

  return (
    <section className="gap-guide" aria-label="Diagnóstico da rodada-base">
      <div className="gap-guide-head">
        <strong>Por que {total} oferta{total > 1 ? "s" : ""} ficaram sem docente</strong>
        <span>O motivo indica qual movimento tem chance de recuperar cada grupo.</span>
      </div>
      <ul>
        {motivos.map(([codigo, quantidade]) => {
          const info = MOTIVOS[codigo];
          const proporcao = Math.round((100 * quantidade) / total);
          return (
            <li key={codigo}>
              <div className="gap-guide-row">
                <b>{info?.rotulo ?? codigo.replaceAll("_", " ").toLowerCase()}</b>
                <span className="gap-guide-count">
                  {quantidade} oferta{quantidade > 1 ? "s" : ""}
                </span>
              </div>
              <div className="gap-guide-track" aria-hidden="true">
                <i style={{ width: `${Math.max(proporcao, 4)}%` }} />
              </div>
              {info && <small>Movimento indicado: {info.movimento}</small>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
