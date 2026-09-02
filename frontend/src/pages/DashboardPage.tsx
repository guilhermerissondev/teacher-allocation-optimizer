import { useEffect, useMemo, useRef, useState } from "react";
import { getDashboard, listAnalysisJobs } from "../api";
import LoadingState from "../components/LoadingState";
import ResetPrimaryRounds from "../components/ResetPrimaryRounds";
import StatusBadge from "../components/StatusBadge";
import MultiSelect, { type MultiSelectOption } from "../components/MultiSelect";
import RoundPicker from "../components/RoundPicker";
import { criterionLabel, jobContextLabel, profileLabel } from "../jobPresentation";
import { count, hours, percent, signedHours } from "../numberFormat";
import { toneByCoverage } from "../coverageTone";
import type { DashboardData, DashboardFilters, Job } from "../types";

const dashboardFilterOrder: Array<keyof DashboardFilters> = ["order", "day", "time", "cluster", "course"];
const emptyFilters = (): DashboardFilters => ({ order: [], day: [], time: [], cluster: [], course: [] });
function labelReason(reason: string) {
  const businessLabels: Record<string, string> = {
    SEM_CANDIDATO: "Sem docente elegível",
    SEM_DOCENTE_COM_PERFIL_E_CARGA: "Sem docente com perfil e carga disponível",
    CHOQUE_DE_HORARIO: "Conflito de agenda",
    CAPACIDADE_LETIVA_ESGOTADA: "Capacidade letiva esgotada",
    CAPACIDADE_E_HORARIO_COMBINADOS: "Capacidade e agenda indisponíveis",
    NAO_INFORMADO: "Motivo não informado",
    "NÃO INFORMADO": "Motivo não informado",
  };
  const known = businessLabels[reason.toLocaleUpperCase("pt-BR")];
  if (known) return known;
  // Um motivo novo do motor chega em CAIXA_ALTA_COM_UNDERSCORE. Só a primeira
  // letra sobe: capitalizar palavra a palavra deixaria "Sem Docente Com Perfil".
  const readable = reason.replaceAll("_", " ").toLocaleLowerCase("pt-BR");
  return readable.charAt(0).toLocaleUpperCase("pt-BR") + readable.slice(1);
}

function DeltaValue({ value }: { value: number }) {
  const state = value > 0 ? "deficit" : "surplus";
  return <strong className={state}>{signedHours(value)}</strong>;
}

export default function DashboardPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState("");
  const [filters, setFilters] = useState<DashboardFilters>(emptyFilters);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const dashboardRequest = useRef(0);
  const loadedRound = useRef("");

  useEffect(() => {
    let active = true;
    void listAnalysisJobs()
      .then((items) => {
        if (!active) return;
        const complete = items.filter((item) => item.status === "CONCLUIDA");
        setJobs(complete);
        if (complete[0]) setSelected(complete[0].id);
      })
      .catch((requestError: Error) => { if (active) setError(requestError.message); })
      .finally(() => { if (active) setJobsLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selected) {
      setDashboard(null);
      setLoading(false);
      return;
    }
    const requestId = ++dashboardRequest.current;
    let active = true;
    setLoading(true);
    // Mudar de filtro mantém o quadro anterior na tela enquanto o novo recorte
    // carrega. Zerá-lo desmontava a barra de filtros a cada clique: o
    // MultiSelect guarda o <details> aberto e o texto buscado em estado local,
    // então marcar um curso fechava a lista e apagava a busca. É também o que
    // torna .is-refreshing e o mini-spinner alcançáveis.
    //
    // Trocar de rodada é outro caso: os números velhos sob o rótulo da rodada
    // nova enganariam, então aí o quadro sai.
    if (loadedRound.current !== selected) setDashboard(null);
    loadedRound.current = selected;
    setError("");
    const timer = window.setTimeout(() => {
      void getDashboard(selected, filters)
        .then((payload) => { if (active && requestId === dashboardRequest.current) setDashboard(payload); })
        .catch((requestError: Error) => { if (active && requestId === dashboardRequest.current) setError(requestError.message); })
        .finally(() => { if (active && requestId === dashboardRequest.current) setLoading(false); });
    }, 100);
    return () => { active = false; window.clearTimeout(timer); };
  }, [selected, filters]);

  const maxReason = useMemo(
    () => Math.max(1, ...(dashboard?.unassigned_reasons.map((item) => item.count) ?? [1])),
    [dashboard],
  );
  const maxDay = useMemo(
    () => Math.max(1, ...(dashboard?.charts.by_day.flatMap((item) => [item.disciplines, item.teachers]) ?? [1])),
    [dashboard],
  );
  const options = dashboard?.filters.options;
  const clusterTotal = useMemo(
    () => dashboard?.charts.demand_hours_by_cluster.reduce((total, item) => total + item.hours, 0) ?? 0,
    [dashboard],
  );
  const clusterBars = useMemo(() => {
    return [...(dashboard?.charts.demand_hours_by_cluster ?? [])].sort((a, b) => b.hours - a.hours || a.cluster.localeCompare(b.cluster, "pt-BR"));
  }, [dashboard]);
  const maxClusterHours = Math.max(1, ...clusterBars.map((item) => item.hours));
  const selectedJob = jobs.find((item) => item.id === selected) ?? null;
  // Uma linha por etapa com os dois confrontos que interessam: a demanda
  // contra a capacidade contratada (delta) e contra o que a rodada entregou
  // (saldo). Em cartões separados os operandos ficavam longe um do outro.
  const stages = dashboard ? [
    {
      label: "Primeiras 5 semanas",
      orders: "1ª + estendida",
      demand: dashboard.kpis.first_stage_demand_hours,
      covered: dashboard.stage_hours.first_stage ?? 0,
      delta: dashboard.kpis.first_stage_capacity_delta_hours,
    },
    {
      label: "Últimas 5 semanas",
      orders: "2ª + estendida",
      demand: dashboard.kpis.second_stage_demand_hours,
      covered: dashboard.stage_hours.second_stage ?? 0,
      delta: dashboard.kpis.second_stage_capacity_delta_hours,
    },
  ] : [];
  // A CH letiva é um teto semanal, então vale igual para as duas metades.
  const activeCapacity = dashboard?.kpis.active_teaching_capacity_hours ?? 0;

  const updateFilter = (key: keyof DashboardFilters, values: string[]) => {
    setFilters((current) => ({ ...current, [key]: values }));
  };
  const hasFilters = Object.values(filters).some((values) => values.length > 0);
  const filterLabels: Record<keyof DashboardFilters, string> = { order: "Ordem", course: "Curso", cluster: "Cluster", day: "Dia", time: "Horário" };
  const optionMaps: Record<keyof DashboardFilters, MultiSelectOption[]> = {
    order: options?.orders.map((value) => ({ value, label: value })) ?? [],
    course: options?.courses ?? [],
    cluster: options?.clusters.map((value) => ({ value, label: value })) ?? [],
    day: options?.days.map((value) => ({ value, label: value })) ?? [],
    time: options?.times.map((value) => ({ value, label: value })) ?? [],
  };
  const activeChips = dashboardFilterOrder.flatMap((key) =>
    filters[key].map((value) => ({ key, value, label: optionMaps[key].find((item) => item.value === value)?.label ?? value })),
  );

  return (
    <div className="page-container dashboard-page">
      <div className="page-heading">
        <div>
          <h1>Dashboard da alocação</h1>
          <p>Monitore cobertura, demanda, capacidade docente e os principais direcionadores da rodada.</p>
        </div>
        <div className="page-heading-actions">
          <RoundPicker
            label="Rodada analisada"
            jobs={jobs}
            value={selected}
            onChange={(id) => { setSelected(id); setFilters(emptyFilters()); }}
          />
          <ResetPrimaryRounds disabled={!jobs.some((job) => job.kind === "PRIMARY")} />
        </div>
      </div>

      {error && <div className="alert error" role="alert">{error}</div>}
      {(jobsLoading || loading) && !dashboard && !error && (
        <LoadingState
          title={jobsLoading ? "Localizando rodadas auditadas" : "Atualizando a visão gerencial"}
          description={jobsLoading ? "Aguarde enquanto o histórico disponível é carregado." : "Indicadores e gráficos estão sendo recalculados para o recorte selecionado."}
        />
      )}
      {!jobsLoading && !loading && !dashboard && !error && (
        <section className="empty-state panel">
          <span aria-hidden="true">▥</span><h2>Execute uma rodada para liberar o dashboard</h2>
          <p>Os gráficos usam somente artefatos publicados e auditados pela aplicação.</p>
          <a className="button primary" href="#/processamento">Ir para Processamento</a>
        </section>
      )}

      {dashboard && (
        <div className={`dashboard-workspace ${loading ? "is-refreshing" : ""}`} aria-busy={loading}>
          <aside className="filter-sidebar panel" aria-label="Filtros globais do dashboard">
            <div className="filter-heading"><div><h2>Recorte da análise</h2></div>{loading && <><span className="mini-spinner" aria-hidden="true" /><span className="sr-only" role="status">Atualizando indicadores</span></>}</div>
            <p>Combine várias opções. Dentro de cada filtro vale “OU”; entre filtros vale “E”.</p>
            {dashboardFilterOrder.map((key) => <MultiSelect key={key} label={filterLabels[key]} values={filters[key]} options={optionMaps[key]} onChange={(values) => updateFilter(key, values)} />)}
            <button className="button secondary" disabled={!hasFilters} onClick={() => setFilters(emptyFilters())}>Limpar filtros</button>
            <div className="filter-footnote"><strong>{count(dashboard.kpis.transmissions)}</strong><span>ofertas no recorte atual</span></div>
          </aside>

          <div className="dashboard-content">
            <section className="confidence-strip" aria-label="Indicadores de confiança">
              <span>Validação <StatusBadge value={dashboard.guardrails.validation} /></span>
              <span>Solver <StatusBadge value={dashboard.guardrails.solver} /></span>
              <span>Auditoria <StatusBadge value={dashboard.guardrails.audit} /></span>
              <span>Rodada <strong>{dashboard.job.round}</strong></span>
              <span>Contexto <StatusBadge value={dashboard.job.is_official ? "APROVADO" : "EXECUTANDO"} label={jobContextLabel(dashboard.job)} /></span>
              <span>Critério <span className="criterion-badge">{criterionLabel(dashboard.job)}</span></span>
              <span>Perfil <span className="criterion-badge">{profileLabel(dashboard.job)}</span></span>
            </section>

            {hasFilters && <section className="active-filter-strip" aria-label="Filtros ativos" aria-live="polite"><strong>Recorte ativo</strong><div>{activeChips.map((chip) => <button type="button" key={`${chip.key}-${chip.value}`} onClick={() => updateFilter(chip.key, filters[chip.key].filter((value) => value !== chip.value))} title={`Remover ${filterLabels[chip.key]}: ${chip.label}`}><span>{filterLabels[chip.key]}</span>{chip.label}<b aria-hidden="true">×</b></button>)}</div><button type="button" className="clear-all" onClick={() => setFilters(emptyFilters())}>Limpar tudo</button></section>}

            <section className="round-result panel" aria-label="Resultado da rodada">
              <div className={`headline-metric ${toneByCoverage(dashboard.kpis.coverage_pct)}`}>
                <span>Cobertura do recorte</span>
                <strong>{percent(dashboard.kpis.coverage_pct)}</strong>
                <div className="headline-track" aria-hidden="true"><span style={{ width: `${Math.min(100, dashboard.kpis.coverage_pct)}%` }} /></div>
                <small>{count(dashboard.kpis.allocated)} de {count(dashboard.kpis.transmissions)} ofertas com docente definido</small>
              </div>
              <div className="result-support">
                <dl className="support-metrics">
                  <div className={dashboard.kpis.unassigned ? "is-attention" : ""}>
                    <dt>Ofertas sem docente</dt>
                    <dd>{count(dashboard.kpis.unassigned)}</dd>
                    <p>{percent(dashboard.kpis.transmissions ? 100 - dashboard.kpis.coverage_pct : 0)} do recorte</p>
                  </div>
                  <div>
                    <dt>Docentes com alocação</dt>
                    <dd>{percent(dashboard.kpis.teacher_use_pct)}</dd>
                    <p>{count(dashboard.kpis.used_teachers)} de {count(dashboard.kpis.active_teachers)} ativos</p>
                  </div>
                  <div>
                    <dt>Ativos sem alocação</dt>
                    <dd>{count(dashboard.kpis.zero_active_teachers)}</dd>
                    <p>nenhuma oferta no recorte</p>
                  </div>
                </dl>
                {/* Composição da oferta é de outra natureza: não é um placar da
                    rodada, é o que entrou no mapa. Fica numa faixa própria. */}
                <div className="order-strip">
                  <span>Ofertas por ordem</span>
                  <b>1ª <em>{count(dashboard.kpis.disciplines_by_order.first)}</em></b>
                  <b>2ª <em>{count(dashboard.kpis.disciplines_by_order.second)}</em></b>
                  <b>Estendida <em>{count(dashboard.kpis.disciplines_by_order.extended)}</em></b>
                  <small>linhas do mapa pedagógico</small>
                </div>
              </div>
            </section>

            <section className="panel stage-panel" aria-labelledby="titulo-etapas">
              <div className="section-title"><div><h2 id="titulo-etapas">Demanda e capacidade por etapa</h2><p>A CH letiva é um teto semanal, então vale igual nas duas metades do módulo. {dashboard.metric_notes.demand}</p></div></div>
              <div className="table-wrap">
                <table className="data-table stage-table">
                  <thead>
                    <tr>
                      <th scope="col">Etapa</th>
                      <th scope="col">Demanda</th>
                      <th scope="col">CH letiva ativa</th>
                      <th scope="col">Delta<small>demanda − CH letiva</small></th>
                      <th scope="col">Horas cobertas<small>ofertas com docente</small></th>
                      <th scope="col">Saldo<small>horas cobertas − demanda</small></th>
                    </tr>
                  </thead>
                  <tbody>
                    {stages.map((stage) => {
                      const balance = stage.covered - stage.demand;
                      const coveredPct = stage.demand ? Math.min(100, (100 * stage.covered) / stage.demand) : 0;
                      // Delta positivo é déficit de capacidade; saldo negativo é
                      // demanda que a rodada não cobriu. Sinais opostos, então
                      // cada um recebe o seu próprio teste.
                      return (
                        <tr key={stage.label}>
                          <th scope="row">{stage.label}<small>{stage.orders}</small></th>
                          <td>{hours(stage.demand)}</td>
                          <td>{hours(activeCapacity)}</td>
                          <td className={stage.delta > 0 ? "is-deficit" : "is-surplus"}>
                            <DeltaValue value={stage.delta} />
                            <small>{stage.delta > 0 ? "déficit" : "folga"}</small>
                          </td>
                          <td>
                            {hours(stage.covered)}
                            <div className="stage-track" role="img" aria-label={`${hours(stage.covered)} de ${hours(stage.demand)} cobertas`}><span style={{ width: `${coveredPct}%` }} /></div>
                          </td>
                          <td className={balance >= 0 ? "is-surplus" : "is-deficit"}>{signedHours(balance)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="chart-note">{dashboard.metric_notes.capacity_delta}</p>
            </section>

            <div className="dashboard-charts">
              <section className="panel chart-panel day-panel">
                <div className="section-title"><div><h2>Disciplinas e professores por dia</h2><p>Ofertas demandadas e docentes únicos efetivamente alocados.</p></div></div>
                <div className="chart-legend"><span><i className="disciplines" />Disciplinas</span><span><i className="teachers" />Professores</span></div>
                <div className="day-chart" role="img" aria-label={`Disciplinas e professores por dia: ${dashboard.charts.by_day.map((item) => `${item.day}, ${item.disciplines} disciplinas e ${item.teachers} professores`).join("; ")}`}>
                  {dashboard.charts.by_day.map((item) => (
                    <div className="day-group" key={item.day}>
                      <div className="day-bars"><span className="disciplines" style={{ height: `${(100 * item.disciplines) / maxDay}%` }} data-value={item.disciplines} /><span className="teachers" style={{ height: `${(100 * item.teachers) / maxDay}%` }} data-value={item.teachers} /></div>
                      <strong>{item.day.slice(0, 3)}</strong>
                    </div>
                  ))}
                </div>
              </section>

              <section className="panel chart-panel cluster-panel">
                <div className="section-title"><div><h2>Horas demandadas por cluster</h2><p>Todos os clusters, ordenados por demanda. Total do recorte: {hours(clusterTotal)}.</p></div></div>
                <div className="cluster-ranked-bars" role="list" aria-label={`Demanda de ${clusterBars.length} clusters, total ${hours(clusterTotal)}`}>
                  {clusterBars.length ? clusterBars.map((item) => {
                    const share = clusterTotal ? (100 * item.hours) / clusterTotal : 0;
                    return <div className="cluster-bar-row" role="listitem" aria-label={`${item.cluster}: ${hours(item.hours)}, ${percent(share)} da demanda`} key={item.cluster}><div><strong title={item.cluster}>{item.cluster}</strong><span>{hours(item.hours)} · {percent(share)}</span></div><div className="cluster-bar-track" aria-hidden="true"><span style={{ width: `${(100 * item.hours) / maxClusterHours}%` }} /></div></div>;
                  }) : <div className="chart-empty" role="listitem">Nenhum cluster no recorte atual.</div>}
                </div>
              </section>

              <section className="panel chart-panel">
                <div className="section-title"><div><h2>Motivos das não alocadas</h2><p>Restrições que impedem a cobertura no recorte.</p></div></div>
                {dashboard.unassigned_reasons.length ? <div className="bar-chart constraint-bars">{dashboard.unassigned_reasons.map((item) => <div className="bar-row" key={item.reason}><div><span>{labelReason(item.reason)}</span><strong>{count(item.count)}</strong></div><div className="bar-track"><span style={{ width: `${(100 * item.count) / maxReason}%` }} /></div></div>)}</div> : <div className="chart-empty state-success">Nenhuma oferta sem alocação neste recorte.</div>}
              </section>

              <section className="panel chart-panel cargo-panel" aria-labelledby="titulo-cargos">
                <div className="section-title"><div><h2 id="titulo-cargos">Docentes por cargo</h2><p>Como o corpo docente absorveu a rodada, aberto por cargo e regime de contratação. Cobre a rodada inteira — este quadro não acompanha o recorte dos filtros.</p></div></div>
                <div className="table-wrap">
                  <table className="data-table cargo-table">
                    <thead>
                      <tr>
                        <th scope="col">Cargo e regime</th>
                        <th scope="col">Docentes</th>
                        <th scope="col">Utilização<small>média das duas etapas</small></th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.teachers_by_job_function.map((row) => (
                        <tr key={`${row.job_function}-${row.regime}`} className={`is-${row.level}`}>
                          <th scope="row">{row.level === "regime" ? row.regime : row.job_function}</th>
                          <td>{count(row.headcount)}</td>
                          <td aria-label={row.utilization_pct === null ? "Não se aplica" : `${percent(row.utilization_pct)}, média de ${hours(row.allocated_hours)} sobre ${hours(row.allocatable_hours)} alocáveis; 1ª etapa ${hours(row.first_stage_hours)}, 2ª etapa ${hours(row.second_stage_hours)}`}>
                            {row.utilization_pct === null ? (
                              // Stricto usa limite de disciplinas, não teto de horas.
                              <span className="not-applicable" title="Sem CH letiva alocável: o contrato usa um limite próprio de disciplinas">NSA</span>
                            ) : (
                              // As duas etapas ficam no título: a média sozinha
                              // esconderia uma metade cheia ao lado de uma vazia.
                              <div className="cargo-usage" title={`1ª etapa ${hours(row.first_stage_hours)} · 2ª etapa ${hours(row.second_stage_hours)} · média ${hours(row.allocated_hours)} de ${hours(row.allocatable_hours)} alocáveis`}>
                                <div className="cargo-usage-track" aria-hidden="true"><span style={{ width: `${Math.min(100, row.utilization_pct)}%` }} /></div>
                                <b>{percent(row.utilization_pct)}</b>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

            </div>

            <footer className="source-note"><span>Fonte</span>{dashboard.source_note}{selectedJob && <> Contexto selecionado: {jobContextLabel(selectedJob)}.</>}<a className="inline-link" href="#/insights">Explorar oportunidades</a></footer>
          </div>
        </div>
      )}
    </div>
  );
}
