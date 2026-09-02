import { ChangeEvent, DragEvent, Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  artifactUrl,
  createModuleBatch,
  getModuleBatch,
  inspectBatchFiles,
  listModuleBatches,
  runModuleBatch,
  deleteModuleBatch,} from "../api";
import RunOptions from "./RunOptions";
import StatusBadge, { humanizeStatus } from "./StatusBadge";
import { formatJobDate } from "../jobPresentation";
import { jobFailed, stepIndex, steps } from "../jobStages";
import { count, percent } from "../numberFormat";
import type {
  BatchModule,
  BatchInspection,
  EligibilityCriterion,
  ExecutionProfile,
  ModuleBatch,
} from "../types";

/** Linha de um módulo no acompanhamento: etapas, mensagem e artefatos. */
function ModuleProgress({ item }: { item: BatchModule }) {
  const job = item.job;
  // Sem rodada ainda, o cartão mostra a situação real do módulo — a fila ou o
  // resultado da validação — em vez de inventar um estado de motor.
  const status = job?.status ?? (item.runnable ? "QUEUED" : item.validation_status);
  const current = stepIndex(status);
  const isFailure = jobFailed(status, Boolean(job?.terminal));
  return (
    <article className="batch-module-card">
      <header>
        <div>
          <span className="batch-module-number">Módulo {item.module}</span>
          <strong>{item.filename}</strong>
          {job && <small>{job.round ?? "Aguardando rodada"} · início {formatJobDate(job.created_at)}</small>}
        </div>
        <StatusBadge value={status} />
      </header>

      {job ? (
        <>
          <ol className="stepper">
            {steps.map((step, index) => (
              <li
                key={step}
                className={
                  isFailure && index === current
                    ? "failed"
                    : index < current
                      ? "done"
                      : index === current
                        ? "current"
                        : ""
                }
              >
                <span>{isFailure && index === current ? "!" : index < current ? "✓" : index + 1}</span>
                <strong>{step}</strong>
              </li>
            ))}
          </ol>
          <div className={`process-message ${isFailure ? "is-failure" : ""}`} role="status">
            <span className={!job.terminal ? "pulse" : ""} aria-hidden="true" />
            <div><strong>{job.message}</strong></div>
            {!job.terminal && <div className="stage-spinner" aria-hidden="true" />}
          </div>
        </>
      ) : (
        <p className="batch-module-waiting">{item.reason || "Pronto para executar."}</p>
      )}

      {item.kpis && job && (
        <>
          <div className="kpi-grid">
            <article className="kpi-card featured">
              <span>Cobertura</span>
              <strong>{percent(item.kpis.coverage_pct)}</strong>
              <small>{count(item.kpis.allocated)} de {count(item.kpis.transmissions)} ofertas</small>
            </article>
            <article className="kpi-card">
              <span>Não alocadas</span>
              <strong>{count(item.kpis.unassigned)}</strong>
              <small>Exigem análise dos motivos</small>
            </article>
            <article className="kpi-card">
              <span>Docentes utilizados</span>
              <strong>{count(item.kpis.used_teachers)}</strong>
              <small>no módulo {item.module}</small>
            </article>
            <article className="kpi-card">
              <span>Solver</span>
              <strong>{humanizeStatus(item.kpis.solver_status ?? "—")}</strong>
              <small>garantia entregue pela rodada</small>
            </article>
          </div>
          <div className="downloads">
            <strong>Artefatos do módulo {item.module}</strong>
            <a href={artifactUrl(job.id, "allocation_workbook")}>Resultado Excel</a>
            <a href={artifactUrl(job.id, "allocation_summary")}>Resumo JSON</a>
            <a href={artifactUrl(job.id, "audit_report")}>Auditoria</a>
            <a href={artifactUrl(job.id, "validation_issues")}>Inconsistências</a>
            <a href={artifactUrl(job.id, "manifest")}>Manifesto</a>
            <a className="analysis-link" href="#/dashboard">Abrir no Dashboard →</a>
          </div>
        </>
      )}
    </article>
  );
}

/**
 * Processamento de vários módulos em uma operação.
 *
 * Segue os mesmos passos da rodada única — arquivo, validação, acompanhamento
 * e resultado — porque é o mesmo pipeline repetido por módulo. O que muda é
 * que cada passo mostra N linhas em vez de uma.
 */
export default function BatchPanel() {
  const [files, setFiles] = useState<File[]>([]);
  const [inspection, setInspection] = useState<BatchInspection | null>(null);
  const [chosenModules, setChosenModules] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [criterion, setCriterion] = useState<EligibilityCriterion>("PERFIL_EXATO");
  const [profile, setProfile] = useState<ExecutionProfile>("PROVA_COMPLETA");
  const [marginOffers, setMarginOffers] = useState(2);
  const [confirmWarnings, setConfirmWarnings] = useState(false);
  const [batch, setBatch] = useState<ModuleBatch | null>(null);
  const [history, setHistory] = useState<ModuleBatch[]>([]);
  const [inspecting, setInspecting] = useState(false);
  const [validating, setValidating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [confirmRemoval, setConfirmRemoval] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    void listModuleBatches().then(setHistory).catch(() => undefined);
  }, []);

  // Enquanto houver módulo na fila, o painel se atualiza sozinho. O histórico
  // acompanha o mesmo ciclo: sem isso a linha do lote em execução continuava
  // exibindo AGUARDANDO até a próxima montagem da tela.
  const historyRunning = history.some(
    (item) => item.status === "EXECUTANDO" || item.status === "AGUARDANDO",
  );
  const shouldPoll = batch?.status === "EXECUTANDO" || historyRunning;

  useEffect(() => {
    if (!shouldPoll) return;
    pollRef.current = window.setInterval(async () => {
      try {
        const [fresh, batches] = await Promise.all([
          batch ? getModuleBatch(batch.id) : Promise.resolve(null),
          listModuleBatches(),
        ]);
        if (fresh) setBatch(fresh);
        setHistory(batches);
      } catch {
        // Falha momentânea de rede não derruba o painel.
      }
    }, 1200);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [batch?.id, shouldPoll]);

  const handleDeleteBatch = async (batchId: string) => {
    setRemoving(batchId);
    setError("");
    try {
      await deleteModuleBatch(batchId);
      // O lote aberto pode ser justamente o excluido: o painel volta ao inicio
      // para nao ficar exibindo uma execucao que nao existe mais.
      if (batch?.id === batchId) resetDownstream();
      setHistory(await listModuleBatches());
      setConfirmRemoval(null);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setRemoving(null);
    }
  };

  const resetDownstream = () => {
    setBatch(null);
    setExpanded(null);
  };

  const acceptFiles = async (incoming: File[]) => {
    const xlsx = incoming.filter((item) => item.name.toLowerCase().endsWith(".xlsx"));
    if (!xlsx.length) {
      setError("Envie planilhas .xlsx.");
      return;
    }
    setInspecting(true);
    setError("");
    resetDownstream();
    setFiles(xlsx);
    try {
      const found = await inspectBatchFiles(xlsx);
      setInspection(found);
      setChosenModules(found.available_modules);
      const broken = found.files.filter((item) => item.error);
      if (broken.length) {
        setError(broken.map((item) => `${item.filename}: ${item.error}`).join(" · "));
      }
    } catch (requestError) {
      setInspection(null);
      setChosenModules([]);
      setError((requestError as Error).message);
    } finally {
      setInspecting(false);
    }
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    void acceptFiles([...(event.target.files ?? [])]);
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    void acceptFiles([...event.dataTransfer.files]);
  };

  const toggleModule = (module: number) => {
    resetDownstream();
    setChosenModules((previous) =>
      previous.includes(module)
        ? previous.filter((item) => item !== module)
        : [...previous, module].sort((a, b) => a - b),
    );
  };

  const handleValidate = async () => {
    if (!files.length || !chosenModules.length) return;
    setValidating(true);
    setError("");
    try {
      const created = await createModuleBatch(files, chosenModules, {
        name,
        criterion,
        profile,
        marginOffers,
      });
      setBatch(created);
      setHistory(await listModuleBatches());
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setValidating(false);
    }
  };

  const handleRun = async () => {
    if (!batch) return;
    setBusy(true);
    setError("");
    try {
      setBatch(await runModuleBatch(batch.id, confirmWarnings));
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const totalRows = useMemo(
    () =>
      (inspection?.files ?? []).reduce(
        (total, item) =>
          total +
          (item.modules ?? [])
            .filter((entry) => chosenModules.includes(entry.module))
            .reduce((sum, entry) => sum + entry.rows, 0),
        0,
      ),
    [inspection, chosenModules],
  );

  const started = Boolean(batch?.modules.some((item) => item.job));
  const heldByWarnings = (batch?.modules ?? []).filter(
    (item) => item.validation_status === "APROVADO_COM_RESSALVAS",
  );
  // O servidor reavalia a confirmação na execução; aqui só antecipamos a
  // contagem para o botão dizer a verdade antes do clique.
  const liberados = (batch?.modules ?? []).filter(
    (item) =>
      item.upload_id &&
      item.validation_status !== "REPROVADO" &&
      (item.validation_status !== "APROVADO_COM_RESSALVAS" || item.runnable || confirmWarnings),
  ).length;

  return (
    <>
      {error && <div className="alert error" role="alert">{error}</div>}

      <section className="panel upload-panel">
        <div className="section-title">
          <div><span className="step-kicker">PASSO 1</span><h2>Arquivos de entrada</h2></div>
          <span className="muted">Somente .xlsx · até 50 MB por arquivo</span>
        </div>
        <div className="upload-grid">
          <label
            className={`dropzone ${files.length ? "has-file" : ""}`}
            onDragOver={(event) => event.preventDefault()}
            onDrop={onDrop}
          >
            <input type="file" accept=".xlsx" multiple onChange={onFileChange} />
            <span className="upload-icon" aria-hidden="true">↑</span>
            <strong>
              {files.length
                ? `${files.length} planilha(s) selecionada(s)`
                : "Arraste as planilhas ou clique para selecionar"}
            </strong>
            <span>
              {files.length
                ? files.map((item) => item.name).join(" · ")
                : "Uma planilha por módulo, ou uma planilha com o ano inteiro"}
            </span>
          </label>

          <div className="upload-actions">
            <label className="field">
              <span>Nome do lote</span>
              <input
                type="text"
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Ano letivo 2026"
              />
            </label>

            <RunOptions
              scope="lote"
              criterion={criterion}
              profile={profile}
              marginOffers={marginOffers}
              onCriterion={(value) => { setCriterion(value); resetDownstream(); }}
              onProfile={(value) => { setProfile(value); resetDownstream(); }}
              onMarginOffers={(value) => { setMarginOffers(value); resetDownstream(); }}
            />

            <button
              className="button primary"
              disabled={!files.length || !chosenModules.length || validating || inspecting}
              onClick={() => void handleValidate()}
            >
              {validating
                ? "Validando…"
                : chosenModules.length
                  ? `Validar ${chosenModules.length} módulo(s)`
                  : "Selecione os módulos"}
            </button>
            <p>A otimização só será liberada após a validação de cada módulo.</p>
          </div>
        </div>

        {inspecting && (
          <div className="inline-loading" role="status">
            <span className="mini-spinner" aria-hidden="true" />
            Lendo a coluna MÓD de cada planilha…
          </div>
        )}

        {inspection && !inspecting && (
          <div className="batch-inspection">
            <h3>Módulos encontrados nas planilhas</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Planilha</th><th>Módulos</th><th className="numeric">Linhas sem módulo</th></tr>
                </thead>
                <tbody>
                  {inspection.files.map((item) => (
                    <tr key={item.filename}>
                      <td>{item.filename}</td>
                      <td>
                        {item.error
                          ? <span className="batch-file-error">{item.error}</span>
                          : (item.modules ?? []).map((entry) => (
                              <span
                                key={entry.module}
                                className={`batch-module-tag${entry.supported ? "" : " unsupported"}`}
                              >
                                {entry.module} · {entry.rows} linha(s)
                                {entry.supported ? "" : " · fora de 51–54"}
                              </span>
                            ))}
                      </td>
                      <td className="numeric">{item.rows_without_module ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {inspection.available_modules.length > 0 && (
              <fieldset className="batch-module-choice">
                <legend>Módulos a processar</legend>
                <div className="batch-module-options">
                  {inspection.available_modules.map((module) => (
                    <label key={module} className={chosenModules.includes(module) ? "selected" : undefined}>
                      <input
                        type="checkbox"
                        checked={chosenModules.includes(module)}
                        onChange={() => toggleModule(module)}
                      />
                      Módulo {module}
                    </label>
                  ))}
                </div>
                <p className="muted">
                  {chosenModules.length} módulo(s) selecionado(s) · {totalRows} linha(s) do mapa
                  pedagógico entram no lote.
                </p>
              </fieldset>
            )}
          </div>
        )}
      </section>

      {validating && (
        <section className="panel loading-stage-panel" aria-live="polite">
          <div className="loading-orbit" aria-hidden="true"><span /><span /><span /></div>
          <div>
            <span className="step-kicker">VALIDAÇÃO EM CURSO</span>
            <h2>Conferindo estrutura e regras de cada módulo</h2>
            <p>Cada módulo é separado, preservado e validado antes de liberar a otimização.</p>
          </div>
          <div className="loading-lines" aria-hidden="true"><span /><span /><span /></div>
        </section>
      )}

      {batch && !validating && (
        <section className="panel">
          <div className="section-title">
            <div><span className="step-kicker">PASSO 2</span><h2>Resultado da validação</h2></div>
            <StatusBadge value={liberados === batch.totals.modules ? "APROVADO" : "PARCIAL"} />
          </div>
          <div className="validation-summary">
            <div><strong>{batch.totals.modules}</strong><span>módulos no lote</span></div>
            <div><strong>{liberados}</strong><span>liberados para executar</span></div>
            <div>
              <strong>{batch.modules.reduce((sum, item) => sum + (item.validation?.blocking_issue_groups ?? 0), 0)}</strong>
              <span>grupos bloqueantes</span>
            </div>
          </div>

          <div className="table-wrap">
            <table className="batch-table">
              <thead>
                <tr>
                  <th>Módulo</th><th>Base</th><th>Validação</th>
                  <th className="numeric">Ofertas alocáveis</th>
                  <th className="numeric">Ocorrências</th>
                  <th>Situação</th><th />
                </tr>
              </thead>
              <tbody>
                {batch.modules.map((item) => (
                  <Fragment key={item.module}>
                    <tr>
                      <td><strong>{item.module}</strong></td>
                      <td className="batch-file">{item.filename}</td>
                      <td><StatusBadge value={item.validation_status} /></td>
                      <td className="numeric">{item.validation?.allocating_rows ?? "—"}</td>
                      <td className="numeric">{item.validation?.issue_groups ?? "—"}</td>
                      <td>
                        {item.runnable
                          ? <span className="batch-ready">Pronto</span>
                          : <span className="batch-blocked">{item.reason}</span>}
                      </td>
                      <td className="batch-row-action">
                        {item.validation?.issues.length ? (
                          <button
                            type="button"
                            className="text-action"
                            aria-expanded={expanded === item.module}
                            onClick={() => setExpanded(expanded === item.module ? null : item.module)}
                          >
                            {expanded === item.module ? "Ocultar" : "Ver ocorrências"}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                    {expanded === item.module && item.validation && (
                      <tr className="batch-issue-row">
                        <td colSpan={7}>
                          <table className="batch-issue-table">
                            <thead>
                              <tr><th>Severidade</th><th>Local</th><th>Ocorrência</th><th>Linhas</th></tr>
                            </thead>
                            <tbody>
                              {item.validation.issues.map((issue) => (
                                <tr key={`${issue.code}-${issue.sheet}-${issue.column}`}>
                                  <td><span className={`severity ${issue.severity.toLowerCase()}`}>{issue.severity}</span></td>
                                  <td>{issue.sheet}<small>{issue.column}</small></td>
                                  <td>{issue.message}</td>
                                  <td>{issue.rows.join(", ")}{issue.count > issue.rows.length ? "…" : ""}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {item.upload_id && (
                            <a className="button secondary" href={`/api/uploads/${item.upload_id}/validation.xlsx`}>
                              Baixar pendências do módulo {item.module}
                            </a>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {heldByWarnings.length > 0 && (
            <div className="alert warning" role="status">
              {heldByWarnings.length} módulo(s) foram aprovados com ressalvas. Leia as
              ocorrências acima e confirme abaixo para liberá-los.
            </div>
          )}

          <div className="validation-actions">
            {heldByWarnings.length > 0 && (
              <label className="confirmation">
                <input
                  type="checkbox"
                  checked={confirmWarnings}
                  onChange={(event) => setConfirmWarnings(event.target.checked)}
                />
                Li as ressalvas e desejo executar a alocação.
              </label>
            )}
            <button
              className="button primary"
              disabled={busy || started || !liberados}
              onClick={() => void handleRun()}
            >
              {started
                ? "Alocação iniciada"
                : liberados
                  ? `Executar alocação de ${liberados} módulo(s)`
                  : heldByWarnings.length
                    ? `Confirme as ressalvas para liberar ${heldByWarnings.length} módulo(s)`
                    : "Nenhum módulo liberável"}
            </button>
          </div>
        </section>
      )}

      {batch && started && (
        <section className="panel" aria-busy={batch.status === "EXECUTANDO"}>
          <div className="section-title">
            <div><span className="step-kicker">PASSO 3</span><h2>Acompanhamento por módulo</h2></div>
            <StatusBadge value={batch.status} />
          </div>
          <p className="muted batch-serial-note">
            As rodadas correm em série, uma por vez. Cada módulo publica o seu próprio resultado
            oficial — o lote não cria um resultado combinado.
          </p>
          <div className="batch-module-list">
            {batch.modules.map((item) => <ModuleProgress item={item} key={item.module} />)}
          </div>
        </section>
      )}

      {batch && batch.totals.offers > 0 && (
        <section className="panel result-section">
          <div className="section-title">
            <div><h2>Consolidado do lote</h2></div>
            <StatusBadge value={batch.status} />
          </div>
          <div className="kpi-grid">
            <article className="kpi-card featured">
              <span>Cobertura do lote</span>
              <strong>{percent(batch.totals.coverage_pct)}</strong>
              <small>{count(batch.totals.allocated)} de {count(batch.totals.offers)} ofertas</small>
            </article>
            <article className="kpi-card">
              <span>Não alocadas</span>
              <strong>{count(batch.totals.offers - batch.totals.allocated)}</strong>
              <small>somadas em todos os módulos</small>
            </article>
            <article className="kpi-card">
              <span>Módulos concluídos</span>
              <strong>{batch.totals.concluded} de {batch.totals.modules}</strong>
              <small>{batch.totals.queued_or_running} ainda na fila</small>
            </article>
            <article className="kpi-card">
              <span>Regra do lote</span>
              <strong>{batch.modules.length ? `M${batch.modules.map((i) => i.module).join(", M")}` : "—"}</strong>
              <small>mesmo critério e perfil em todos</small>
            </article>
          </div>
          <p className="muted">
            O consolidado soma módulos independentes; ele não é um resultado oficial por si.
            A referência oficial continua sendo a rodada de cada módulo.
          </p>
        </section>
      )}

      {history.length > 0 && (
        <section className="panel">
          <div className="section-title">
            <div><h2>Lotes anteriores</h2></div>
          </div>
          <div className="table-wrap">
            <table className="batch-table">
              <thead>
                <tr>
                  <th>Lote</th><th>Módulos</th><th>Situação</th>
                  <th className="numeric">Cobertura</th><th />
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}<small>{formatJobDate(item.created_at)}</small></td>
                    <td>{item.modules.map((entry) => entry.module).join(", ")}</td>
                    <td><StatusBadge value={item.status} /></td>
                    <td className="numeric">
                      {item.totals.offers ? percent(item.totals.coverage_pct) : "—"}
                    </td>
                    <td className="batch-row-action">
                      {confirmRemoval === item.id ? (
                        <span className="batch-remove-confirm">
                          <span>Excluir o lote e as rodadas dele?</span>
                          <button
                            type="button"
                            className="text-action danger"
                            disabled={removing === item.id}
                            onClick={() => void handleDeleteBatch(item.id)}
                          >
                            {removing === item.id ? "Excluindo…" : "Confirmar"}
                          </button>
                          <button type="button" className="text-action" onClick={() => setConfirmRemoval(null)}>
                            Cancelar
                          </button>
                        </span>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="text-action"
                            onClick={() => void getModuleBatch(item.id).then((fresh) => { setBatch(fresh); setExpanded(null); })}
                          >
                            Abrir
                          </button>
                          <button
                            type="button"
                            className="text-action danger"
                            disabled={item.status === "EXECUTANDO"}
                            title={item.status === "EXECUTANDO"
                              ? "Aguarde a fila terminar para excluir o lote."
                              : "Excluir o lote do histórico"}
                            onClick={() => setConfirmRemoval(item.id)}
                          >
                            Excluir
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
