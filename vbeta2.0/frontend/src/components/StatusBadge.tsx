export type StatusTone = "success" | "warning" | "critical" | "info" | "neutral";

function normalizeStatus(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLocaleUpperCase("pt-BR");
}

// Estados terminais que nao comecam por FALHA. Sem esta tabela eles caiam no
// tom neutro, e uma auditoria reprovada aparecia com o mesmo cinza de um
// estado desconhecido — exatamente o oposto do que o operador precisa ver.
const TERMINAL_FAILURE_STATES = [
  "VALIDACAO_REPROVADA",
  "AUDITORIA_REPROVADA",
  "OTIMO_NAO_COMPROVADO",
  "SNAPSHOT_ALTERADO",
  "ERRO_INTERNO",
  "SEM_SOLUCAO",
  "MODEL_INVALID",
];

// Garantias do solver mais fracas que OPTIMAL, porem utilizaveis: sao
// resultados legitimos, e nao falhas, mas nao podem ser homologados.
const PARTIAL_GUARANTEE_STATES = [
  "APROVADO_COM_RESSALVAS",
  "FEASIBLE",
  "RESSALVA",
  "COBERTURA_PROVADA",
  "OTIMO_COM_MARGEM",
  "INTERROMPIDA",
  "UNKNOWN",
];

export function statusTone(value: string): StatusTone {
  const normalized = normalizeStatus(value);

  if (
    normalized.startsWith("FALHA")
    || TERMINAL_FAILURE_STATES.includes(normalized)
    || ["REPROVADO", "FAILED", "INFEASIBLE", "ERRO", "CANCELADO"].includes(normalized)
  ) return "critical";

  if (PARTIAL_GUARANTEE_STATES.includes(normalized)) return "warning";

  if (
    ["APROVADO", "OPTIMAL", "CONCLUIDA", "CONCLUIDO", "HOMOLOGADO", "ATIVO"].includes(normalized)
  ) return "success";

  if (
    normalized === "QUEUED"
    || normalized === "NA FILA"
    || normalized === "EXECUTANDO"
    || normalized === "EM CONFIGURACAO"
    || normalized.startsWith("GRAVANDO")
    || normalized.startsWith("RESOLVENDO")
    || normalized.endsWith("ANDO")
    || normalized.endsWith("ENDO")
  ) return "info";

  return "neutral";
}

export function humanizeStatus(value: string) {
  return value.replaceAll("_", " ");
}

export default function StatusBadge({
  value,
  label,
  className = "",
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  return (
    <span className={`status-badge status-${statusTone(value)} ${className}`.trim()}>
      {label ?? humanizeStatus(value)}
    </span>
  );
}
