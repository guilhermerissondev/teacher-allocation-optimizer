import { Component, ErrorInfo, ReactNode } from "react";

type Props = { children: ReactNode; area: string };
type State = { error: Error | null };

/**
 * Contém uma falha de render à área onde ela aconteceu.
 *
 * Sem isso, qualquer exceção durante o render desmonta a aplicação inteira e o
 * operador fica olhando para uma tela vazia, sem nada que explique o que houve
 * nem como sair — foi exatamente o que um campo ausente na resposta da API
 * provocou na tela de lote. Aqui a falha vira uma mensagem no lugar do painel,
 * o resto da página continua utilizável, e o detalhe técnico fica disponível
 * para o relato.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // O console é a única trilha que sobra para diagnosticar em produção local.
    console.error(`Falha ao desenhar ${this.props.area}:`, error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <section className="panel error-boundary" role="alert">
        <div className="section-title">
          <div>
            <span className="step-kicker">FALHA NA INTERFACE</span>
            <h2>Não foi possível desenhar {this.props.area}</h2>
          </div>
        </div>
        <p>
          O restante da página continua funcionando. Recarregue para tentar de novo; se
          persistir, o detalhe abaixo identifica o ponto da falha.
        </p>
        <pre>{this.state.error.message}</pre>
        <div className="validation-actions">
          <button
            type="button"
            className="button secondary"
            onClick={() => this.setState({ error: null })}
          >
            Tentar desenhar novamente
          </button>
          <button
            type="button"
            className="button primary"
            onClick={() => window.location.reload()}
          >
            Recarregar a página
          </button>
        </div>
      </section>
    );
  }
}
