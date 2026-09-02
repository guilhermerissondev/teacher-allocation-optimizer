import { useEffect, useMemo, useRef, useState } from "react";
import { getInsights, listAnalysisJobs } from "../api";
import LoadingState from "../components/LoadingState";
import ResetPrimaryRounds from "../components/ResetPrimaryRounds";
import RoundPicker from "../components/RoundPicker";
import { jobContextLabel } from "../jobPresentation";
import { count, hours, percent } from "../numberFormat";
import { toneByCoverage } from "../coverageTone";
import type { InsightsData, Job } from "../types";

/**
 * Tom do cartao a partir do valor, nao do assunto.
 *
 * Um indicador zerado e uma boa noticia e precisa parecer uma: pintar
 * "Disciplinas sem cobertura: 0" de vermelho treina o operador a ignorar a cor.
 */
function toneByCount(value: number, nonZeroTone: "critical" | "warning" = "warning") {
  return value > 0 ? `tone-${nonZeroTone}` : "tone-success";
}



export default function InsightsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState("");
  const [insights, setInsights] = useState<InsightsData | null>(null);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const insightRequest = useRef(0);

  useEffect(() => {
    let active = true;
    void listAnalysisJobs().then((items) => {
      if (!active) return;
      const complete = items.filter((item) => item.status === "CONCLUIDA");
      setJobs(complete);
      if (complete[0]) setSelected(complete[0].id);
    }).catch((requestError: Error) => { if (active) setError(requestError.message); })
      .finally(() => { if (active) setJobsLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selected) {
      setInsights(null);
      setLoading(false);
      return;
    }
    const requestId = ++insightRequest.current;
    let active = true;
    setInsights(null);
    setLoading(true);
    setError("");
    void getInsights(selected)
      .then((payload) => { if (active && requestId === insightRequest.current) setInsights(payload); })
      .catch((requestError: Error) => { if (active && requestId === insightRequest.current) setError(requestError.message); })
      .finally(() => { if (active && requestId === insightRequest.current) setLoading(false); });
    return () => { active = false; };
  }, [selected]);

  const congestedSlotMaximum = useMemo(
    () => Math.max(1, ...(insights?.diagnostics.most_congested_unassigned_slots.map((item) => item.count) ?? [1])),
    [insights],
  );
  const disciplineGaps = insights?.coverage.discipline_gaps.filter((item) => item.unassigned > 0) ?? [];
  const selectedJob = jobs.find((item) => item.id === selected) ?? null;

  const pendingOpportunities = insights?.opportunities.filter((item) => item.severity !== "resolvido") ?? [];
  const resolvedOpportunities = insights?.opportunities.filter((item) => item.severity === "resolvido") ?? [];

  return (
    <div className="page-container">
      <div className="page-heading">
        <div><h1>Insights da alocação</h1><p>Priorize lacunas de curso e disciplina, proteja a cobertura e encontre oportunidades de eficiência operacional.</p></div>
        <div className="page-heading-actions"><RoundPicker label="Rodada analisada" jobs={jobs} value={selected} onChange={setSelected} /><ResetPrimaryRounds disabled={!jobs.some((job) => job.kind === "PRIMARY")} /></div>
      </div>
      {error && <div className="alert error" role="alert">{error}</div>}
      {(jobsLoading || loading) && !insights && !error && <LoadingState title={jobsLoading ? "Localizando rodadas auditadas" : "Gerando diagnósticos da rodada"} description={jobsLoading ? "Aguarde enquanto o histórico disponível é carregado." : "Cobertura, lacunas e oportunidades estão sendo consolidadas."} />}
      {!jobsLoading && !loading && !insights && !error && <section className="empty-state panel"><span>✦</span><h2>Execute uma rodada para gerar os insights</h2><p>A análise usa somente o resultado auditado.</p><a className="button primary" href="#/processamento">Ir para Processamento</a></section>}

      {insights && <>
        <section className="kpi-grid insight-kpis">
          <article className={`kpi-card featured ${toneByCoverage(insights.kpis.coverage_pct)}`}><span>Cobertura geral</span><strong>{percent(insights.kpis.coverage_pct)}</strong><small>ofertas com docente definido</small></article>
          <article className={`kpi-card ${toneByCount(insights.kpis.courses_below_90_pct)}`}><span>Cursos abaixo de 90%</span><strong>{count(insights.kpis.courses_below_90_pct)}</strong><small>{insights.kpis.courses_below_90_pct ? "prioridade para diretoria acadêmica" : "todos os cursos em 90% ou mais"}</small></article>
          <article className={`kpi-card ${toneByCount(insights.kpis.disciplines_uncovered, "critical")}`}><span>Disciplinas sem cobertura</span><strong>{count(insights.kpis.disciplines_uncovered)}</strong><small>{insights.kpis.disciplines_uncovered ? "cobertura igual a zero" : "nenhuma disciplina zerada"}</small></article>
          <article className={`kpi-card ${toneByCount(insights.kpis.unassigned_demand_hours, "critical")}`}><span>Demanda não coberta</span><strong>{hours(insights.kpis.unassigned_demand_hours)}</strong><small>{insights.kpis.unassigned_demand_hours ? `${hours(insights.kpis.hours_per_transmission)} por oferta não alocada` : "toda a demanda foi atendida"}</small></article>
          <article className={`kpi-card ${toneByCount(insights.kpis.single_candidate_allocations)}`}><span>Alocações com candidato único</span><strong>{count(insights.kpis.single_candidate_allocations)}</strong><small>{insights.kpis.single_candidate_allocations ? "ofertas alocadas sem alternativa docente" : "toda alocação tem alternativa"}</small></article>
          <article className={`kpi-card ${toneByCount(insights.kpis.rpa_allocated_hours)}`}><span>Exposição RPA/NF</span><strong>{hours(insights.kpis.rpa_allocated_hours)}</strong><small>{insights.kpis.rpa_allocated_hours ? "proxy operacional de custo" : "nenhuma hora em contrato externo"}</small></article>
        </section>

        {/* O que exige ação fica em cartão; o que já está resolvido vira uma
            linha. Dar a mesma área e a mesma saturação aos dois puxava o olho
            para o "nada a fazer" — a frente crítica ficava em minoria visual. */}
        {pendingOpportunities.length > 0 && (
          <section className="opportunity-grid">
            {pendingOpportunities.map((item) => <article className={`opportunity-card sev-${item.severity}`} key={item.title}><div><span className="priority">Prioridade {item.priority}</span><strong>{item.title}</strong></div><b>{item.metric}</b><p>{item.impact}</p><footer>{item.action}</footer></article>)}
          </section>
        )}
        {resolvedOpportunities.length > 0 && (
          <section className="resolved-strip" aria-label="Frentes sem ação pendente">
            <h2>Sem ação pendente</h2>
            <ul>
              {resolvedOpportunities.map((item) => (
                <li key={item.title}>
                  <strong>{item.title}</strong>
                  <span>{item.metric}</span>
                  <p>{item.impact}</p>
                </li>
              ))}
            </ul>
          </section>
        )}

        <div className="insight-grid coverage-grid">
          <section className="panel chart-panel">
            <div className="section-title"><div><h2>Cobertura de todos os cursos</h2><p>Todos os {insights.coverage.courses.length} cursos, ordenados pela quantidade de lacunas. Os dias indicam onde ocorreram as ofertas não alocadas.</p></div></div>
            <div className="coverage-legend" aria-label="Legenda do gráfico"><span><i className="allocated" />Alocadas</span><span><i className="unassigned" />Não alocadas</span></div>
            <div className="coverage-bars all-courses">{insights.coverage.courses.map((item) => (
              <div className="coverage-row" key={`${item.curso}|${item.nome_curso}`}>
                <div>
                  <strong title={item.nome_curso}>{item.nome_curso}</strong>
                  <span>{item.allocated} alocadas de {item.total} ofertas · {item.unassigned} {item.unassigned === 1 ? "lacuna" : "lacunas"}</span>
                  <div className="course-gap-days" aria-label={`Dias com lacunas em ${item.nome_curso}`}>
                    <small>Dias:</small>
                    {item.gap_days.length > 0
                      ? item.gap_days.map((gap) => <em key={gap.day}>{gap.day} <b>{gap.count}</b></em>)
                      : <em className="no-gap">sem lacunas</em>}
                  </div>
                </div>
                <div className="coverage-track" role="img" aria-label={`${item.nome_curso}: ${percent(item.coverage_pct)} de cobertura, ${item.unassigned} ofertas não alocadas`}>
                  <span className="coverage-allocated" style={{ width: `${item.coverage_pct}%` }} />
                  <span className="coverage-unassigned" style={{ width: `${100 - item.coverage_pct}%` }} />
                </div>
                <b>{percent(item.coverage_pct)}</b>
              </div>
            ))}</div>
          </section>
          <section className="panel chart-panel">
            <div className="section-title"><div><h2>Horários com mais lacunas</h2><p>Todas as combinações de dia e horário, ordenadas pela quantidade de ofertas não alocadas.</p></div></div>
            <div className="diagnostic-profile"><span>Perfil mais recorrente nas lacunas</span><strong>{insights.diagnostics.top_gap_profile ?? "Sem lacunas"}</strong></div>
            {insights.diagnostics.most_congested_unassigned_slots.length > 0 ? (
              <div className="diagnostic-bars">{insights.diagnostics.most_congested_unassigned_slots.map((item, index) => (
                <div className="diagnostic-row" key={item.slot}>
                  <div><span>{index + 1}</span><strong>{item.slot}</strong><b>{item.count}</b></div>
                  <div className="diagnostic-track" role="img" aria-label={`${item.slot}: ${item.count} ofertas não alocadas`}><span style={{ width: `${(100 * item.count) / congestedSlotMaximum}%` }} /></div>
                  <p>{item.affected_courses} {item.affected_courses === 1 ? "curso afetado" : "cursos afetados"} · Mais recorrente: <strong>{item.top_course}</strong> ({item.top_course_count})</p>
                  <small>Perfil predominante: {item.top_profile}</small>
                </div>
              ))}</div>
            ) : <div className="chart-empty state-success">Nenhuma oferta não alocada nesta rodada.</div>}
          </section>
        </div>

        <section className="panel chart-panel">
          <div className="section-title"><div><h2>Cobertura de todos os clusters</h2><p>Todos os {insights.coverage.clusters.length} clusters, ordenados pela quantidade de lacunas. Os dias indicam onde ocorreram as ofertas não alocadas.</p></div></div>
          <div className="coverage-legend" aria-label="Legenda do gráfico"><span><i className="allocated" />Alocadas</span><span><i className="unassigned" />Não alocadas</span></div>
          <div className="coverage-bars all-clusters">{insights.coverage.clusters.map((item) => (
            <div className="coverage-row" key={item.cluster}>
              <div>
                <strong title={item.cluster}>{item.cluster}</strong>
                <span>{item.allocated} alocadas de {item.total} ofertas · {item.unassigned} {item.unassigned === 1 ? "lacuna" : "lacunas"}</span>
                <div className="course-gap-days" aria-label={`Dias com lacunas em ${item.cluster}`}>
                  <small>Dias:</small>
                  {item.gap_days.length > 0
                    ? item.gap_days.map((gap) => <em key={gap.day}>{gap.day} <b>{gap.count}</b></em>)
                    : <em className="no-gap">sem lacunas</em>}
                </div>
              </div>
              <div className="coverage-track" role="img" aria-label={`${item.cluster}: ${percent(item.coverage_pct)} de cobertura, ${item.unassigned} ofertas não alocadas`}>
                <span className="coverage-allocated" style={{ width: `${item.coverage_pct}%` }} />
                <span className="coverage-unassigned" style={{ width: `${100 - item.coverage_pct}%` }} />
              </div>
              <b>{percent(item.coverage_pct)}</b>
            </div>
          ))}</div>
        </section>

        <section className="panel">
          <div className="section-title"><div><h2>Fila de recuperação de cobertura</h2><p>Todas as {disciplineGaps.length} disciplinas que não estão 100% cobertas, ordenadas por prioridade de alocação.</p></div></div>
          <div className="table-wrap discipline-gaps-table"><table><caption className="sr-only">Disciplinas prioritárias para recuperação de cobertura</caption><thead><tr><th scope="col">Curso</th><th scope="col">Disciplina</th><th scope="col">Cobertura</th><th scope="col">Não alocadas</th><th scope="col">Demanda</th><th scope="col">Candidato único</th></tr></thead><tbody>{disciplineGaps.map((item) => <tr key={`${item.curso}|${item.nome_curso}|${item.cod_disciplina}|${item.nome_disciplina}`}><td><strong>{item.nome_curso}</strong><small>{item.curso}</small></td><td><strong>{item.nome_disciplina}</strong><small>{item.cod_disciplina}</small></td><td><span className={`coverage-pill ${item.coverage_pct === 0 ? "critical" : "attention"}`}>{percent(item.coverage_pct)}</span></td><td>{item.unassigned}</td><td>{item.demand_hours}h</td><td>{item.single_candidate}</td></tr>)}</tbody></table></div>
        </section>

        <section className="panel methodology-panel"><div><h2>Como interpretar</h2></div><div className="methodology-columns"><div><strong>Regras aplicadas</strong><ul>{insights.methodology.map((item) => <li key={item}>{item}</li>)}</ul></div><div><strong>Limites atuais</strong><ul>{insights.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div></div></section>
        <footer className="source-note"><span>Fonte</span>{insights.source_note}{selectedJob && <> Contexto selecionado: {jobContextLabel(selectedJob)}.</>}</footer>
      </>}
    </div>
  );
}
