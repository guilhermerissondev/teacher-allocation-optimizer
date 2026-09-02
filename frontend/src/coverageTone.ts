/**
 * Escala de cobertura, única para toda a aplicação.
 *
 * Dashboard e Insights pintavam o mesmo `coverage_pct` com regras diferentes:
 * uma rodada a 95% saía verde numa tela e âmbar na outra. Duas leituras do
 * mesmo número treinam o operador a desconfiar da cor.
 *
 * A escala tem três faixas porque "coberto" e "quase coberto" pedem ações
 * diferentes: verde só quando não sobrou lacuna para tratar.
 */
export type CoverageTone = "tone-success" | "tone-warning" | "tone-critical";

export function toneByCoverage(pct: number): CoverageTone {
  if (pct >= 99.5) return "tone-success";
  if (pct >= 90) return "tone-warning";
  return "tone-critical";
}
