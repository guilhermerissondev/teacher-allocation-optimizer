# Qualidade e homologação

## Objetivo

Uma release só está pronta quando código, regra de negócio, experiência visual, dados de demonstração e pacote Windows foram verificados como conjunto.

## Inventário automatizado

O código revisado possui:

| Camada | Testes definidos |
|---|---:|
| Motor principal | 109 |
| Motor de cenários | 116 |
| Backend | 61 |
| Release, backup e restauração | 42 |
| Frontend | nenhum teste automatizado dedicado; `tsc --noEmit` cobre os tipos |

São **328 testes Python** no total. A contagem não substitui o recibo de
execução: cada release precisa registrar data, ambiente, comando, quantidade
aprovada e falhas.

O recibo técnico mais recente está em [evidências de QA](evidencias/README.md).

## Comandos

Execução consolidada recomendada:

    .\scripts\testar.ps1

O script executa backend, motor principal, motor de cenários, release/backup/restauração, verificação estrutural e, quando presente, MANIFESTO_RELEASE.json.

### Verificação opcional da interface

`testar.ps1` cobre tudo que é Python. O que ele não cobre é se a tela
**desenha**: uma resposta da API sem um campo que o tipo prometia derruba a
página inteira e passa por toda a suíte sem um arranhão — foi o que aconteceu
uma vez no fluxo de lote.

    node .\scriptserificar_interface.js --url http://127.0.0.1:8000

Percorre as cinco abas e o fluxo de lote nos dois temas, reprovando em qualquer
exceção de render. Fica **fora** do portão canônico de propósito: exige Node.js,
o Chrome instalado e a aplicação em execução, e o release não deve depender
disso. Rode-o antes de publicar uma mudança de interface.

Motor principal:

    python -m unittest discover -s engines\primary\tests -p "test_*.py" -v

Motor de cenários:

    python -m unittest discover -s engines\scenarios\tests -p "test_*.py" -v

Backend:

    Set-Location backend
    python -m unittest discover -s tests -p "test_*.py" -v

Release, backup e restauração:

    python -m unittest discover -s scripts\tests -p "test_*.py" -v

Frontend:

    Set-Location frontend
    npm ci
    npm run build

## Cobertura esperada dos motores

- contrato e fórmulas proibidas;
- seleção de entrada;
- carga por etapas;
- elegibilidade;
- limite Stricto;
- colisão de agenda;
- objetivos lexicográficos;
- canonicalização;
- GRASP;
- auditoria;
- reporting;
- integridade do manifesto;
- execução por caminho independente do diretório atual;
- políticas exclusivas de cenário.

## Homologação integrada

O teste E2E mínimo deve executar:

1. iniciar a aplicação com diretório de dados vazio;
2. selecionar módulo;
3. enviar base anonimizada;
4. baixar pendências XLSX;
5. confirmar ressalvas, se houver;
6. executar motor principal;
7. esperar conclusão;
8. validar resumo e artefatos;
9. aplicar filtros do Dashboard;
10. verificar todos os cursos e horários em Insights;
11. criar cenário;
12. configurar alteração de docente ou oferta;
13. executar cenário;
14. comparar;
15. homologar cenário elegível;
16. confirmar que ele aparece como oficial nas análises;
17. testar reset do último cenário;
18. testar reset da última rodada em ambiente descartável.

## Evidência de referência

A base de demonstração oficial desta versão é:

    exemplos\BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx

O conjunto agregado de homologação associado apresentou:

| Métrica | Resultado |
|---|---:|
| Ofertas | 402 |
| Alocadas | 377 |
| Não alocadas | 25 |
| Docentes utilizados | 222 |
| Solver | OPTIMAL |
| Auditoria | APROVADO |
| Estado final | CONCLUIDA |

A validação teve ressalvas de qualidade da entrada. O resultado de alocação foi PARCIAL, mas matematicamente OPTIMAL.

Esses números servem somente como referência daquele conjunto. Não são meta fixa para outro módulo.

## Verificação de artefatos

Para cada item estável do manifesto:

1. resolver o caminho relativo dentro da rodada;
2. confirmar existência;
3. comparar tamanho;
4. recalcular SHA-256;
5. registrar resultado.

O manifesto também deve ter fonte, versões, configuração, fases e outcome coerentes.

## Integridade do pacote

O manifesto de release não é o mesmo manifesto de uma rodada. Para gerar:

    python scripts\integridade_release.py --gerar

Para verificar:

    python scripts\integridade_release.py --verificar

MANIFESTO_RELEASE.json deve declarar a versão 2.0.0 e validar tamanho e SHA-256 de todos os arquivos distribuíveis. Dados reais ficam na pasta data da instalação (ou em LocalAppData, quando ela é somente leitura) e não integram o manifesto.

## Qualidade de dados

Antes de aprovar a rodada:

- cabeçalhos completos e sem duplicação;
- módulo coerente;
- CHAPA única;
- cargas inteiras não negativas;
- ORDEM suportada;
- agenda válida nas ofertas;
- nenhuma fórmula em campos de dados;
- bloqueios iguais a zero;
- ressalvas compreendidas pelo responsável.

## Matriz visual

Validar pelo menos:

| Cenário | Verificação |
|---|---|
| Desktop 1920×1080 | Leitura para apresentação |
| Notebook 1366×768 | Sem corte de controles |
| Largura 760 px | Reorganização responsiva |
| Largura 320–375 px | Sem overflow destrutivo |
| Zoom 200% | Conteúdo e ações acessíveis |
| Teclado | Ordem de foco e operação completa |
| Movimento reduzido | Transições desativadas |
| Edge e Chrome | Layout e downloads |

Gráficos precisam de texto ou aria-label equivalente. Cores não podem ser a única forma de distinguir estado.

## Custo computacional por critério

Os métodos por cluster ampliam o conjunto de candidatos e, com ele, o modelo
entregue ao CP-SAT. Na base de demonstração de 402 ofertas e 233 docentes:

| Critério | Variáveis de atribuição | Candidatos por oferta | Ofertas sem candidato |
|---|---:|---:|---:|
| PERFIL_EXATO | 2.582 | 6,4 em média | 11 |
| CLUSTER_PURO | 28.155 | 70,0 em média | 0 |

O crescimento de aproximadamente 11 vezes torna a prova de otimalidade
substancialmente mais cara. A homologação deve medir o tempo de parede dos
métodos por cluster na base real antes de liberá-los para uso em apresentação, e
decidir se um limite de tempo será configurado.

Atenção: com limite de tempo e sem a opção de permitir não ótimo, uma fase que
não conclui a prova impede a publicação da rodada.

## Casos de falha

- extensão inválida;
- XLSX acima de 50 MB;
- arquivo corrompido;
- planilha ou coluna ausente;
- módulo divergente;
- validação reprovada;
- ressalva sem confirmação;
- porta 8000 ocupada;
- diretório de dados sem permissão;
- reinício no meio da execução;
- ótimo não comprovado;
- auditoria reprovada;
- baseline excluída;
- cenário sem política válida;
- reset durante job;
- caminho com espaço e acento;
- artefato ausente ou hash divergente;
- critério de elegibilidade inválido;
- política ALOCAR_CLUSTER sobre baseline já em cluster;
- promoção de cenário com critério diferente da baseline.

## Homologação Windows

O candidato deve ser testado em máquina limpa, sem depender do repositório original, Node global ou pacotes Python globais.

Validar:

- primeira inicialização;
- diretório de dados;
- launcher e encerramento;
- firewall sem exposição externa;
- abertura do navegador;
- execução dos dois motores;
- downloads;
- backup e restauração;
- desinstalação sem excluir dados sem confirmação.

## Gate para diretoria

- [ ] Regras validadas pelo responsável acadêmico.
- [ ] Critério de elegibilidade padrão confirmado pelo responsável acadêmico.
- [x] Solver principal não alterado por políticas de cenário.
- [x] Todos os testes Python aprovados (224/224 em 24/08/2026).
- [x] Modo PERFIL_EXATO comprovado equivalente à versão 1.0 na base de
      demonstração: 402 ofertas, zero decisões divergentes.
- [x] Build frontend regerado com Node.js 26.5.0 e Vite 7.3.6, sem erro de tipo.
- [ ] E2E local dos três critérios aprovado.
- [ ] Tempo de execução dos métodos por cluster medido e aceito na base real.
- [x] Base de demonstração anonimizada.
- [x] Nome da base confirmado como BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx.
- [x] MANIFESTO_RELEASE.json aprovado por integridade_release.py.
- [x] Manifesto e hashes válidos.
- [ ] Interface revisada em resolução de apresentação.
- [x] Limitações conhecidas explicadas.
- [x] Backup e restauração da homologação comprovados.
- [x] Licenças e avisos presentes.
- [x] Versão 2.0.0 e checksum SHA-256 do pacote registrados em `release/`.
