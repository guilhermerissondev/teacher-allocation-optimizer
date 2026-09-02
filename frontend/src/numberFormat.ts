/**
 * Formatação numérica pt-BR.
 *
 * A interface é em português e alimenta o report semanal, que escreve
 * "64,23%" e "3.988h". `toFixed` produz o separador inglês e não agrupa
 * milhares, então todo número que chega à tela passa por aqui.
 *
 * Os formatadores são criados uma vez e reaproveitados: montar um
 * Intl.NumberFormat é caro e as tabelas repetem a mesma chamada por linha.
 */

const cache = new Map<string, Intl.NumberFormat>();

function formatter(minimumFractionDigits: number, maximumFractionDigits: number): Intl.NumberFormat {
  const key = `${minimumFractionDigits}:${maximumFractionDigits}`;
  let instance = cache.get(key);
  if (!instance) {
    instance = new Intl.NumberFormat("pt-BR", { minimumFractionDigits, maximumFractionDigits });
    cache.set(key, instance);
  }
  return instance;
}

/** Casas fixas: uma tabela de percentuais não pode ter linhas com larguras diferentes. */
export function decimal(value: number, decimals = 0): string {
  return formatter(decimals, decimals).format(value);
}

/** Percentual já em escala 0–100, como vem da API. */
export function percent(value: number, decimals = 1): string {
  return `${decimal(value, decimals)}%`;
}

/** Horas letivas. O agrupamento de milhar importa: 3988 vira "3.988h". */
export function hours(value: number, decimals = 0): string {
  return `${decimal(value, decimals)}h`;
}

/** Contagem inteira com agrupamento de milhar. */
export function count(value: number): string {
  return decimal(value, 0);
}

/**
 * Variações precisam do sinal explícito, inclusive o "+", porque o número
 * sozinho não diz se subiu ou desceu em relação à referência.
 */
export function signedDecimal(value: number, decimals = 0, suffix = ""): string {
  return `${value > 0 ? "+" : ""}${decimal(value, decimals)}${suffix}`;
}

export function signedHours(value: number, decimals = 0): string {
  return signedDecimal(value, decimals, "h");
}

/** Pontos percentuais: a unidade de comparação entre duas taxas. */
export function signedPoints(value: number, decimals = 1): string {
  return signedDecimal(value, decimals, " pp");
}

/**
 * Casas variáveis (0 a 2), para deltas que tanto vêm inteiros — ofertas
 * recuperadas — quanto fracionários — pontos percentuais de cobertura.
 */
export function natural(value: number): string {
  return formatter(0, 2).format(value);
}

export function signedNatural(value: number, suffix = ""): string {
  return `${value > 0 ? "+" : ""}${natural(value)}${suffix}`;
}

/** Segundos com uma casa, para o tempo do motor. */
export function seconds(value: number): string {
  return `${decimal(value, 1)}s`;
}

/** Tamanho de arquivo em MB, usado no seletor de planilha. */
export function megabytes(bytes: number): string {
  return `${decimal(bytes / 1024 / 1024, 2)} MB`;
}
