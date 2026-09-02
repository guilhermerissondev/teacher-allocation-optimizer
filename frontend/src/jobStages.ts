/**
 * As etapas do motor, e onde cada estado se encontra nelas.
 *
 * Rodada única e lote desenham o mesmo stepper, porque é o mesmo pipeline.
 * A tabela vive aqui, e não em cada tela, para que um estado novo publicado
 * pelo backend não precise ser lembrado em dois lugares — foi o que o teste
 * de contrato `test_status_contract.py` passou a vigiar.
 */

export const steps = ["Preparando", "Validando", "Otimizando", "Auditando", "Publicando"];

// Os estados terminais de falha precisam apontar a etapa que realmente falhou:
// sem eles, uma auditoria reprovada era desenhada como falha em "Preparando",
// mandando o operador conferir o arquivo de entrada em vez do relatório.
export const STEP_BY_STATUS: Record<string, number> = {
  SELECIONANDO_ENTRADA: 0,
  COPIANDO_ENTRADA: 0,
  FALHA_ENTRADA_CONFIG: 0,
  VALIDANDO: 1,
  FALHA_VALIDACAO: 1,
  VALIDACAO_REPROVADA: 1,
  SNAPSHOT_ALTERADO: 1,
  RESOLVENDO: 2,
  FALHA_SOLVER: 2,
  AUDITANDO: 3,
  FALHA_AUDITORIA: 3,
  AUDITORIA_REPROVADA: 3,
  OTIMO_NAO_COMPROVADO: 3,
  GRAVANDO_ALOCACAO: 4,
};

/** Etapa corrente. Uma rodada concluída passa do fim, marcando todas. */
export function stepIndex(status: string): number {
  if (status === "CONCLUIDA") return steps.length;
  return STEP_BY_STATUS[status] ?? 0;
}

/** Terminou sem concluir — a etapa corrente é onde a falha aconteceu. */
export function jobFailed(status: string, terminal: boolean): boolean {
  return terminal && status !== "CONCLUIDA";
}
