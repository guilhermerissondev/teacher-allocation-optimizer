import type { EligibilityCriterion, ExecutionProfile } from "../types";

/**
 * As duas decisões da importação, em um só lugar.
 *
 * Rodada única e lote fazem exatamente as mesmas perguntas ao operador. Tê-las
 * duplicadas em duas telas foi o que deixou uma com radio explicado e a outra
 * com um select seco; manter um componente só torna a divergência impossível.
 */

export const CRITERIA: {
  value: EligibilityCriterion;
  label: string;
  tag?: string;
  hint: string;
}[] = [
  {
    value: "PERFIL_EXATO",
    label: "Perfil da disciplina",
    tag: "padrão",
    hint: "Só entra na disputa quem tem o perfil exato da disciplina. Máxima aderência pedagógica, e a menor cobertura das três.",
  },
  {
    value: "CLUSTER_PREFERENCIAL",
    label: "Cluster com perfil preferencial",
    hint: "Aceita qualquer perfil do cluster da disciplina, mas escolhe o perfil exato sempre que houver empate. Cobre mais sem abrir mão da aderência onde ela é possível.",
  },
  {
    value: "CLUSTER_PURO",
    label: "Cluster puro",
    hint: "Aceita qualquer perfil do cluster, sem preferir o perfil exato. Cobre exatamente o mesmo que a opção acima; muda apenas quais docentes ficam com quais disciplinas.",
  },
];

export const PROFILES: {
  value: ExecutionProfile;
  label: string;
  tag?: string;
  official?: boolean;
  hint: string;
}[] = [
  {
    value: "PROVA_COMPLETA",
    label: "Prova completa",
    tag: "padrão",
    official: true,
    hint: "Prova que nenhuma alocação melhor existe sob as regras atuais. É a única que pode virar o resultado oficial do módulo.",
  },
  {
    value: "COBERTURA_PROVADA",
    label: "Cobertura provada",
    hint: "Prova que ninguém cobre mais disciplinas que isto, mas não prova a escolha entre soluções de mesma cobertura. Não pode ser homologada.",
  },
  {
    value: "MARGEM_ACEITA",
    label: "Margem aceita",
    hint: "Aceita ficar até N disciplinas abaixo do melhor possível, com essa diferença provada. Útil quando o tempo importa mais que o último ponto de cobertura. Não pode ser homologada.",
  },
  {
    value: "EXPLORACAO_RAPIDA",
    label: "Exploração rápida",
    hint: "Entrega uma alocação utilizável, sem provar que é a melhor. Serve para testar uma base nova ou uma premissa. Não pode ser homologada.",
  },
];

export type RunOptionsProps = {
  criterion: EligibilityCriterion;
  profile: ExecutionProfile;
  marginOffers: number;
  disabled?: boolean;
  /** Sufixo dos atributos `name`, para os dois modos coexistirem na página. */
  scope: string;
  onCriterion: (value: EligibilityCriterion) => void;
  onProfile: (value: ExecutionProfile) => void;
  onMarginOffers: (value: number) => void;
};

export default function RunOptions({
  criterion,
  profile,
  marginOffers,
  disabled = false,
  scope,
  onCriterion,
  onProfile,
  onMarginOffers,
}: RunOptionsProps) {
  return (
    <>
      <fieldset className="option-group" disabled={disabled}>
        <legend>Quem pode assumir cada disciplina?</legend>
        {CRITERIA.map((item) => (
          <label className="option" key={item.value}>
            <input
              type="radio"
              name={`criterio-elegibilidade-${scope}`}
              value={item.value}
              checked={criterion === item.value}
              onChange={() => onCriterion(item.value)}
            />
            <span className="option-text">
              <span className="option-title">
                {item.label}
                {item.tag && <small className="is-default">{item.tag}</small>}
              </span>
              <p>{item.hint}</p>
            </span>
          </label>
        ))}
      </fieldset>

      <fieldset className="option-group" disabled={disabled}>
        <legend>Quanta prova a rodada precisa entregar?</legend>
        {PROFILES.map((item) => (
          <label className="option" key={item.value}>
            <input
              type="radio"
              name={`perfil-execucao-${scope}`}
              value={item.value}
              checked={profile === item.value}
              onChange={() => onProfile(item.value)}
            />
            <span className="option-text">
              <span className="option-title">
                {item.label}
                {item.tag && <small className="is-default">{item.tag}</small>}
                {item.official && <small className="is-official">homologável</small>}
              </span>
              <p>{item.hint}</p>
            </span>
          </label>
        ))}
      </fieldset>

      {profile === "MARGEM_ACEITA" && (
        <label className="field">
          <span>Margem aceita, em ofertas</span>
          <input
            type="number"
            min={1}
            max={100}
            disabled={disabled}
            value={marginOffers}
            onChange={(event) => onMarginOffers(Math.max(1, Number(event.target.value) || 1))}
          />
        </label>
      )}
    </>
  );
}
