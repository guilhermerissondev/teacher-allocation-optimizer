/**
 * Uma faixa por alvo selecionado.
 *
 * O painel de contexto só existia para um alvo: ao marcar o segundo, a tela
 * voltava ao estado anterior e o operador perdia de vista o que tinha na mão
 * justamente quando a premissa passava a valer para muita gente.
 *
 * A primeira tentativa resolveu isso com números do conjunto — distribuição do
 * campo, faixa de CH, contagem de gestores. Respondia "como é o grupo", que não
 * é a pergunta: quem revê uma premissa quer conferir *cada* registro, e ler
 * "132 valores · maior: 9 Educação" não diz nada sobre o docente que se quer
 * lembrar. Agora cada alvo ganha a própria faixa, com os mesmos campos que o
 * painel de um registro mostra, e o campo em edição traz o valor atual ao lado
 * do novo — em cada linha, porque o valor de partida muda de um para outro.
 *
 * Serve às duas abas de cenário: cada uma monta as próprias faixas, porque o
 * alvo do módulo único é a linha da planilha e o do lote é a chave de negócio,
 * mas a leitura na tela é a mesma.
 */

export type ResumoCampo = {
  rotulo: string;
  valor: string;
  /** Marca o campo que o formulário está alterando. */
  editando?: boolean;
  /**
   * Valor de destino deste alvo. Fica por campo, e não no painel inteiro,
   * porque o ajuste relativo de CH leva cada docente a um número diferente.
   */
  destino?: string;
};

/**
 * Teto de faixas desenhadas de uma vez.
 *
 * "Selecionar os 187 filtrados" e um clique so, e desenhar 187 faixas trava a
 * aba: cada uma traz cabecalho, selo e cinco campos. Alem do teto a leitura
 * tambem ja tinha se perdido — ninguem confere duzentos registros rolando uma
 * lista. O corte mantem as primeiras e diz quantas ficaram de fora.
 */
const LIMITE_FAIXAS = 25;

export type ResumoItem = {
  chave: string;
  titulo: string;
  selo?: { texto: string; tom: "ok" | "atencao" };
  campos: ResumoCampo[];
};

export default function SelectionSummary({
  total,
  substantivo,
  destaque,
  itens,
  aviso,
}: {
  total: number;
  /** "docentes", "ofertas", "cursos"… já no plural. */
  substantivo: string;
  destaque?: { texto: string; tom: "ok" | "atencao" };
  itens: ResumoItem[];
  /** Alerta de premissa sem efeito para parte do conjunto. */
  aviso?: string;
}) {
  if (total < 2) return null;

  const visiveis = itens.slice(0, LIMITE_FAIXAS);
  const ocultas = itens.length - visiveis.length;

  return (
    <div className="entity-context is-summary" aria-live="polite">
      <div className="entity-context-head">
        <strong>
          {total} {substantivo} selecionados
        </strong>
        {destaque && (
          <span className={`pill-state ${destaque.tom === "ok" ? "is-allocated" : "is-open"}`}>
            {destaque.texto}
          </span>
        )}
      </div>

      {/* Rolagem própria: com dezenas de alvos a lista empurraria o botão de
          enviar para fora da tela, e a premissa ficaria fora de alcance. */}
      <ul className="selection-bands">
        {visiveis.map((item) => (
          <li key={item.chave} className="selection-band">
            <div className="selection-band-head">
              <strong>{item.titulo}</strong>
              {item.selo && (
                <span
                  className={`pill-state ${item.selo.tom === "ok" ? "is-allocated" : "is-open"}`}
                >
                  {item.selo.texto}
                </span>
              )}
            </div>
            <dl className="selection-band-fields">
              {item.campos.map((campo) => {
                const destino = String(campo.destino ?? "").trim();
                return (
                  <div key={campo.rotulo} className={campo.editando ? "is-editing" : undefined}>
                    <dt>{campo.rotulo}</dt>
                    <dd title={destino !== "" ? `${campo.valor} → ${destino}` : campo.valor}>
                      {campo.editando && destino !== "" ? (
                        <>
                          <s>{campo.valor}</s>
                          <span aria-hidden="true"> → </span>
                          <b>{destino}</b>
                          <span className="sr-only">
                            {` alterado de ${campo.valor} para ${destino}`}
                          </span>
                        </>
                      ) : (
                        campo.valor
                      )}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </li>
        ))}
        {ocultas > 0 && (
          <li className="selection-band is-rest">
            +{ocultas} {substantivo} não exibidos aqui — todos entram na premissa. Use os
            filtros acima para conferir os que faltam.
          </li>
        )}
      </ul>

      {aviso && (
        <p className="entity-context-aviso" role="status">
          {aviso}
        </p>
      )}
    </div>
  );
}
