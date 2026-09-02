import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  addScenarioChangesBatch,
  addScenarioPolicy,
  createScenario,
  deleteScenarioChange,
  deleteScenarioPolicy,
  getJob,
  getScenario,
  getScenarioCatalog,
  getScenarioComparison,
  getSummary,
  listJobs,
  listScenarios,
  promoteScenario,
  resetPrimaryJobs,
  resetSavedScenarios,
  runScenario,
} from "../api";
import LoadingState from "../components/LoadingState";
import BaselineGapGuide from "../components/BaselineGapGuide";
import ScenarioEntityContext, { mesmoValor, valorAtualDoCampo } from "../components/ScenarioEntityContext";
import ScenarioEntityPicker from "../components/ScenarioEntityPicker";
import SelectionSummary from "../components/SelectionSummary";
import StatusBadge, { humanizeStatus, statusTone } from "../components/StatusBadge";
import StudyPanel from "../components/StudyPanel";
import MultiSelect from "../components/MultiSelect";
import RoundPicker from "../components/RoundPicker";
import { count, percent, signedNatural } from "../numberFormat";
import type {
  BatchChangeResult,
  Job,
  Scenario,
  ScenarioCatalog,
  ScenarioComparison,
  Summary,
} from "../types";

const executiveMoves = [
  { key: "CAPACIDADE", icon: "CH", title: "Reforçar ou reduzir capacidade", decision: "Contratar, afastar, retornar ou alterar CH letiva.", fields: ["STATUS", "CH_LETIVA"], impact: "Cobertura, déficit de CH e custo de capacidade" },
  { key: "AGENDA", icon: "AG", title: "Reorganizar agenda", decision: "Mover ofertas entre dia, horário ou metade do módulo.", fields: ["DIA_AULA", "HORÁRIO", "ORDEM"], impact: "Choques, cobertura e concentração diária" },
  { key: "COMPATIBILIDADE", icon: "PF", title: "Ampliar compatibilidade", decision: "Adicionar perfil docente ou revisar o perfil exigido pela oferta.", fields: ["PERFIL_DISCIPLINA"], impact: "Candidatos elegíveis e risco de candidato único" },
  { key: "ALOCAR_CLUSTER", icon: "CL", title: "Alocar docentes do cluster", decision: "Buscar docentes com CH disponível no cluster para recuperar disciplinas sem alocação.", fields: ["CLUSTER", "CH DISPONÍVEL", "AGENDA"], impact: "Cobertura das lacunas com flexibilização controlada de perfil" },
  { key: "PRIORIDADE", icon: "PR", title: "Proteger prioridades acadêmicas", decision: "Definir cursos e disciplinas que não podem perder cobertura.", fields: ["CURSO", "OFERTA"], impact: "Cobertura das ofertas estratégicas" },
  { key: "FIXAR", icon: "BL", title: "Fixar decisões", decision: "Preservar alocações homologadas e recalcular o restante.", fields: ["OFERTA", "DOCENTE", "CHAPA"], impact: "Estabilidade, trocas e esforço de implantação" },
] as const;

type MoveKey = typeof executiveMoves[number]["key"];
type EntityType = "teacher" | "offer";

const dayOptions = ["SEGUNDA", "TERÇA", "QUARTA", "QUINTA", "SEXTA"];
const statusOptions = ["ATIVO", "DEMITIDO", "LICENÇA MATER.", "LICENÇA MATER. COMPL. 180 DIAS"];

function signed(value: number, suffix = "") {
  return signedNatural(value, suffix);
}

function deltaInterpretation(value: number, positiveIsGood: boolean) {
  if (value === 0) return { className: "delta-neutral", label: "Sem alteração" };
  const improves = positiveIsGood ? value > 0 : value < 0;
  return improves
    ? { className: "delta-improvement", label: "Melhora" }
    : { className: "delta-regression", label: "Piora" };
}

function ScenarioMetricCard({
  title,
  value,
  delta,
  positiveIsGood,
  detail,
  featured = false,
}: {
  title: string;
  value: string;
  delta: number;
  positiveIsGood: boolean;
  detail: string;
  featured?: boolean;
}) {
  const interpretation = deltaInterpretation(delta, positiveIsGood);
  return <article className={`kpi-card scenario-delta-card ${interpretation.className} ${featured ? "featured" : ""}`}><span>{title}</span><strong>{value}</strong><small><b>{interpretation.label}</b>{detail}</small></article>;
}

export default function ScenariosPage() {
  // Um cenario responde por um modulo; um estudo repete a mesma pergunta ao
  // longo do ano. Sao fluxos distintos, e o seletor mantem o modo de um
  // modulo como padrao para quem ja usa a tela.
  const [mode, setMode] = useState<"single" | "batch">("single");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [active, setActive] = useState<Scenario | null>(null);
  const [baseline, setBaseline] = useState("");
  const [baselineSummary, setBaselineSummary] = useState<Summary | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedMove, setSelectedMove] = useState<MoveKey>("CAPACIDADE");
  const [entityType, setEntityType] = useState<EntityType>("teacher");
  const [fieldName, setFieldName] = useState("STATUS");
  const [newValue, setNewValue] = useState("");
  // Seleção em lote: o modo individual continua sendo o padrão.
  const [selectedRows, setSelectedRows] = useState<number[]>([]);
  const [chLivre, setChLivre] = useState(false);
  const [chFonte, setChFonte] = useState<"letiva" | "contratada">("letiva");
  const [perfilLivre, setPerfilLivre] = useState(false);
  const [perfilBusca, setPerfilBusca] = useState("");
  const [chMode, setChMode] = useState<"set" | "adjust">("set");
  const [adjustment, setAdjustment] = useState("");
  const [batchFeedback, setBatchFeedback] = useState<BatchChangeResult | null>(null);
  const [configuratorOpen, setConfiguratorOpen] = useState(false);
  const [policyTargetType, setPolicyTargetType] = useState("COURSE");
  const [policyTargetValues, setPolicyTargetValues] = useState<string[]>([]);
  const [catalog, setCatalog] = useState<ScenarioCatalog | null>(null);
  const [comparison, setComparison] = useState<ScenarioComparison | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [resetTarget, setResetTarget] = useState<"baseline" | "scenario" | null>(null);
  const baselineRequest = useRef(0);
  const scenarioDetailRequest = useRef(0);
  const resetDialogRef = useRef<HTMLElement>(null);
  const resetCancelRef = useRef<HTMLButtonElement>(null);
  const busyRef = useRef(false);

  useEffect(() => { busyRef.current = busy; }, [busy]);

  useEffect(() => {
    if (!resetTarget) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    resetCancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        setResetTarget(null);
        return;
      }
      if (event.key !== "Tab" || !resetDialogRef.current) return;
      const focusable = Array.from(resetDialogRef.current.querySelectorAll<HTMLElement>("button:not(:disabled)"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [resetTarget]);

  const refreshScenarios = async (preferredId?: string) => {
    const items = await listScenarios();
    setScenarios(items);
    const selected = items.find((item) => item.id === (preferredId ?? active?.id));
    if (selected) setActive(selected);
  };

  useEffect(() => {
    let live = true;
    void Promise.all([listJobs(), listScenarios()]).then(([jobItems, scenarioItems]) => {
      if (!live) return;
      const complete = jobItems.filter((item) => item.status === "CONCLUIDA");
      setJobs(complete);
      setScenarios(scenarioItems);
      if (complete[0]) setBaseline(complete[0].id);
      // Restaurar o cenario sem abrir o configurador deixava a tela num estado
      // enganoso: o campo "Cenario salvo" ja mostrava o cenario, mas o
      // formulario de premissas nao existia na pagina, e nada dizia que ainda
      // faltava um clique em "Configurar cenario".
      if (scenarioItems[0]) {
        setActive(scenarioItems[0]);
        setConfiguratorOpen(true);
      }
    }).catch((requestError: Error) => { if (live) setError(requestError.message); })
      .finally(() => { if (live) setInitialLoading(false); });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    const baselineId = active?.baseline_job_id ?? baseline;
    if (!baselineId) {
      setBaselineSummary(null);
      return;
    }
    const requestId = ++baselineRequest.current;
    let live = true;
    setBaselineSummary(null);
    void getSummary(baselineId)
      .then((payload) => { if (live && requestId === baselineRequest.current) setBaselineSummary(payload); })
      .catch(() => { if (live && requestId === baselineRequest.current) setBaselineSummary(null); });
    return () => { live = false; };
  }, [baseline, active?.baseline_job_id]);

  useEffect(() => {
    if (!active) {
      setCatalog(null);
      setComparison(null);
      setCatalogLoading(false);
      setComparisonLoading(false);
      return;
    }
    const requestId = ++scenarioDetailRequest.current;
    let live = true;
    setError("");
    setCatalog(null);
    setCatalogLoading(true);
    setComparison(null);
    setComparisonLoading(active.latest_job?.status === "CONCLUIDA");
    void getScenarioCatalog(active.id)
      .then((payload) => { if (live && requestId === scenarioDetailRequest.current) setCatalog(payload); })
      .catch((requestError: Error) => { if (live && requestId === scenarioDetailRequest.current) setError(requestError.message); })
      .finally(() => { if (live && requestId === scenarioDetailRequest.current) setCatalogLoading(false); });
    if (active.latest_job?.status === "CONCLUIDA") {
      void getScenarioComparison(active.id)
        .then((payload) => { if (live && requestId === scenarioDetailRequest.current) setComparison(payload); })
        .catch((requestError: Error) => { if (live && requestId === scenarioDetailRequest.current) { setComparison(null); setError(`Não foi possível carregar a comparação: ${requestError.message}`); } })
        .finally(() => { if (live && requestId === scenarioDetailRequest.current) setComparisonLoading(false); });
    }
    return () => { live = false; };
  }, [active?.id, active?.latest_job?.status]);

  useEffect(() => {
    const latest = active?.latest_job;
    if (!latest || latest.terminal) return;
    const timer = window.setInterval(async () => {
      try {
        const current = await getJob(latest.id);
        setActive((previous) => previous ? { ...previous, latest_job: current, status: current.terminal ? previous.status : "EXECUTANDO" } : previous);
        if (current.terminal) {
          window.clearInterval(timer);
          const refreshed = await getScenario(active.id);
          setActive(refreshed);
          await refreshScenarios(refreshed.id);
        }
      } catch (requestError) {
        setError((requestError as Error).message);
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [active?.id, active?.latest_job?.id, active?.latest_job?.terminal]);

  const move = executiveMoves.find((item) => item.key === selectedMove) ?? executiveMoves[0];
  const advancedMove = ["ALOCAR_CLUSTER", "PRIORIDADE", "FIXAR"].includes(selectedMove);
  const fields = useMemo(() => {
    if (selectedMove === "CAPACIDADE") return ["STATUS", "CH_LETIVA"];
    if (selectedMove === "AGENDA") return ["DIA_AULA", "HORÁRIO", "ORDEM"];
    if (selectedMove === "COMPATIBILIDADE") return ["PERFIL_DISCIPLINA"];
    return [];
  }, [selectedMove]);
  const baselineCoverage = baselineSummary?.transmissions
    ? (100 * baselineSummary.allocated) / baselineSummary.transmissions
    : 0;
  const premiseCount = (active?.changes.length ?? 0) + (active?.policies.length ?? 0);
  const readOnly = Boolean(active && (active.status === "HOMOLOGADO" || active.official_job_id));
  const promotionBlockers = useMemo(() => {
    if (!comparison || comparison.guardrails.eligible_for_promotion) return [];
    const blockers: string[] = [];
    if (statusTone(comparison.guardrails.validation) !== "success") blockers.push(`Validação: ${humanizeStatus(comparison.guardrails.validation)}.`);
    if (statusTone(comparison.guardrails.solver) !== "success") blockers.push(`Solver: ${humanizeStatus(comparison.guardrails.solver)}.`);
    if (statusTone(comparison.guardrails.audit) !== "success") blockers.push(`Auditoria: ${humanizeStatus(comparison.guardrails.audit)}.`);
    if (!blockers.length) blockers.push("O cenário não atende a todos os critérios internos de homologação.");
    return blockers;
  }, [comparison]);

  const resetEditor = (moveKey: MoveKey) => {
    setSelectedMove(moveKey);
    const nextEntity: EntityType = moveKey === "AGENDA" ? "offer" : "teacher";
    setEntityType(nextEntity);
    setNewValue("");
    setChLivre(false);
    setPerfilLivre(false);
    setPerfilBusca("");
    setSelectedRows([]);
    setBatchFeedback(null);
    setChMode("set");
    setAdjustment("");
    setPolicyTargetType(moveKey === "ALOCAR_CLUSTER" ? "CLUSTER" : moveKey === "FIXAR" ? "OFFER" : "COURSE");
    setPolicyTargetValues([]);
    setFieldName(moveKey === "CAPACIDADE" ? "STATUS" : moveKey === "AGENDA" ? "DIA_AULA" : "PERFIL_DISCIPLINA");
  };

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!baseline || name.trim().length < 3) return;
    setBusy(true);
    setError("");
    try {
      const created = await createScenario(baseline, name, description);
      setActive(created);
      setName("");
      setDescription("");
      await refreshScenarios(created.id);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };


  const handleAddBatch = async (event: FormEvent) => {
    event.preventDefault();
    if (!active || readOnly || advancedMove || !selectedRows.length) return;
    const relativo = fieldName === "CH_LETIVA" && chMode === "adjust";
    if (relativo && (adjustment.trim() === "" || Number(adjustment) === 0)) return;
    if (!relativo && newValue === "") return;
    setBusy(true);
    setError("");
    setBatchFeedback(null);
    try {
      const result = await addScenarioChangesBatch(active.id, {
        change_type: selectedMove,
        entity_type: entityType,
        field_name: fieldName,
        row_numbers: selectedRows,
        ...(relativo
          ? { adjustment: Number(adjustment) }
          : { new_value: fieldName === "CH_LETIVA" ? Number(newValue) : newValue }),
      });
      setBatchFeedback(result);
      const refreshed = await getScenario(active.id);
      setActive(refreshed);
      await refreshScenarios(active.id);
      // Mantém a seleção quando nada entrou, para o operador corrigir o valor
      // sem refazer o filtro inteiro.
      if (result.applied_count > 0) setSelectedRows([]);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleAddPolicy = async (event: FormEvent) => {
    event.preventDefault();
    if (!active || readOnly || !advancedMove) return;
    if (!policyTargetValues.length) return;
    setBusy(true);
    setError("");
    // Uma politica por alvo: o modelo guarda um alvo por linha, entao a
    // selecao multipla vira varias criacoes em serie. Alvos ja cadastrados
    // sao ignorados em vez de abortar o lote inteiro.
    const jaCadastrados = new Set(
      (active.policies ?? [])
        .filter((item) => item.policy_type === selectedMove && item.target_type === policyTargetType)
        .map((item) => item.target_value),
    );
    const pendentes = policyTargetValues.filter((value) => !jaCadastrados.has(value));
    const falhas: string[] = [];
    try {
      for (const targetValue of pendentes) {
        const selectedOffer = catalog?.offers.find((item) => item.row_number === Number(targetValue));
        try {
          await addScenarioPolicy(active.id, {
            policy_type: selectedMove,
            target_type: policyTargetType,
            target_value: targetValue,
            configuration: selectedMove === "FIXAR" ? { teacher_badge: selectedOffer?.baseline_teacher_badge ?? "" } : {},
          });
        } catch (requestError) {
          falhas.push(`${targetValue}: ${(requestError as Error).message}`);
        }
      }
      const refreshed = await getScenario(active.id);
      setActive(refreshed);
      await refreshScenarios(active.id);
      setPolicyTargetValues([]);
      if (falhas.length) {
        setError(`${falhas.length} de ${pendentes.length} política(s) não foram criadas. ${falhas[0]}`);
      }
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteChange = async (changeId: string) => {
    if (!active || readOnly) return;
    setBusy(true);
    setError("");
    try {
      await deleteScenarioChange(active.id, changeId);
      const refreshed = await getScenario(active.id);
      setActive(refreshed);
      await refreshScenarios(active.id);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeletePolicy = async (policyId: string) => {
    if (!active || readOnly) return;
    setBusy(true);
    setError("");
    try {
      await deleteScenarioPolicy(active.id, policyId);
      const refreshed = await getScenario(active.id);
      setActive(refreshed);
      await refreshScenarios(active.id);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleRun = async () => {
    if (!active || readOnly) return;
    setBusy(true);
    setError("");
    setComparison(null);
    try {
      const job = await runScenario(active.id);
      setActive({ ...active, status: "EXECUTANDO", latest_job: job });
      await refreshScenarios(active.id);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handlePromote = async () => {
    if (!active || !comparison?.guardrails.eligible_for_promotion) return;
    if (!window.confirm("Homologar esta simulação como resultado final do módulo? O histórico anterior será preservado.")) return;
    setBusy(true);
    setError("");
    try {
      const promoted = await promoteScenario(active.id);
      setActive(promoted);
      await refreshScenarios(promoted.id);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async (scope: "latest" | "all") => {
    if (!resetTarget) return;
    setBusy(true);
    setError("");
    try {
      if (resetTarget === "baseline") await resetPrimaryJobs(scope);
      else await resetSavedScenarios(scope);
      const [jobItems, scenarioItems] = await Promise.all([listJobs(), listScenarios()]);
      const complete = jobItems.filter((item) => item.status === "CONCLUIDA");
      setJobs(complete);
      setScenarios(scenarioItems);
      setBaseline(complete[0]?.id ?? "");
      setActive(scenarioItems[0] ?? null);
      setConfiguratorOpen(Boolean(scenarioItems[0]));
      setCatalog(null);
      setComparison(null);
      setResetTarget(null);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // Dias e horarios efetivamente praticados na rodada-base, com a contagem de
  // ofertas em cada um. Sugerir um horario que a operacao nao usa nao ajuda a
  // decidir; mostrar quantas ofertas ja ocupam a faixa, sim.
  const agendaPraticada = useMemo(() => {
    const dias = new Map<string, number>();
    const horarios = new Map<string, number>();
    for (const oferta of catalog?.offers ?? []) {
      const dia = (oferta.day ?? "").trim().toUpperCase();
      const hora = (oferta.time ?? "").trim();
      if (dia) dias.set(dia, (dias.get(dia) ?? 0) + 1);
      if (hora) horarios.set(hora, (horarios.get(hora) ?? 0) + 1);
    }
    return {
      dias,
      horarios: [...horarios.entries()].sort((a, b) => a[0].localeCompare(b[0])),
    };
  }, [catalog]);

  // As cargas letivas que realmente existem na base. Digitar o numero a mao
  // obriga a lembrar quais faixas o contrato usa; a lista fechada mostra as
  // faixas e quantos docentes estao em cada uma, como ja acontece com dia,
  // horario e ordem.
  // Duas leituras da mesma base respondem a perguntas diferentes: a CH letiva
  // mostra as faixas que estao efetivamente em sala; a CH contratada mostra os
  // tipos de contrato disponiveis. A coluna contratada pode nao existir na
  // base, e nesse caso a fonte simplesmente nao e oferecida.
  // Perfis e status praticados na base, com quantos registros usam cada um.
  // O perfil vem da mesma coluna PERFIL_DISCIPLINA nos dois lados: no docente e
  // o que ele pode assumir, na oferta e o que ela exige.
  const perfisPraticados = useMemo(() => {
    const perfis = new Map<string, number>();
    const origem = entityType === "teacher" ? catalog?.teachers ?? [] : catalog?.offers ?? [];
    for (const item of origem) {
      const perfil = (item.profile ?? "").trim();
      if (perfil) perfis.set(perfil, (perfis.get(perfil) ?? 0) + 1);
    }
    return [...perfis.entries()].sort((a, b) => a[0].localeCompare(b[0], "pt-BR"));
  }, [catalog, entityType]);

  // A lista canonica de status garante que uma situacao ainda nao usada continue
  // disponivel; a base acrescenta o que existir alem dela.
  const statusPraticados = useMemo(() => {
    const contagem = new Map<string, number>();
    for (const docente of catalog?.teachers ?? []) {
      const status = (docente.status ?? "").trim().toUpperCase();
      if (status) contagem.set(status, (contagem.get(status) ?? 0) + 1);
    }
    const nomes = [...new Set([...statusOptions, ...contagem.keys()])];
    return nomes.map((nome) => [nome, contagem.get(nome) ?? 0] as [string, number]);
  }, [catalog]);

  const cargasPorFonte = useMemo(() => {
    const letiva = new Map<number, number>();
    const contratada = new Map<number, number>();
    for (const docente of catalog?.teachers ?? []) {
      const ch = Number(docente.teaching_capacity);
      if (Number.isFinite(ch)) letiva.set(ch, (letiva.get(ch) ?? 0) + 1);
      const contrato = docente.contracted_capacity;
      if (contrato !== null && contrato !== undefined && Number.isFinite(Number(contrato))) {
        const valor = Number(contrato);
        contratada.set(valor, (contratada.get(valor) ?? 0) + 1);
      }
    }
    const ordenar = (mapa: Map<number, number>) =>
      [...mapa.entries()].sort((a, b) => a[0] - b[0]);
    return { letiva: ordenar(letiva), contratada: ordenar(contratada) };
  }, [catalog]);

  const cargasPraticadas = chFonte === "contratada" ? cargasPorFonte.contratada : cargasPorFonte.letiva;

  // Uma premissa que repete o valor atual entra no conjunto, vai para o motor e
  // nao muda nada — polui o registro de decisoes do cenario sem produzir efeito.
  // Detectar aqui evita que ela chegue a ser criada.
  // So faz sentido com um alvo: com varios, o valor atual difere entre eles e
  // quem reporta o que ficou de fora e o retorno do lote.
  const entidadeSelecionada = useMemo(() => {
    if (selectedRows.length !== 1) return null;
    const linha = selectedRows[0];
    return entityType === "teacher"
      ? catalog?.teachers.find((item) => item.row_number === linha) ?? null
      : catalog?.offers.find((item) => item.row_number === linha) ?? null;
  }, [catalog, entityType, selectedRows]);

  const valorAtual = valorAtualDoCampo(entidadeSelecionada, fieldName);
  // Com um unico alvo da para avisar antes de enviar; com varios o servidor
  // ignora as linhas ja no valor e devolve o motivo em skipped.
  const alteracaoInocua = Boolean(entidadeSelecionada) && mesmoValor(valorAtual, newValue);

  // Resumo do conjunto quando ha mais de um alvo. O painel de contexto mostra o
  // registro inteiro de uma entidade; com varias, o que decide a premissa e a
  // distribuicao do campo em edicao e quantas ja estao no valor de destino.
  // Uma faixa por alvo, com os mesmos campos que o painel de um registro
  // mostra. O agregado que existia antes respondia "como e o grupo"; quem
  // confere uma premissa precisa reconhecer cada registro.
  const resumoSelecao = useMemo(() => {
    if (selectedRows.length < 2 || !catalog) return null;
    const linhasSelecionadas = new Set(selectedRows);
    const destinoDe = (campo: string, atual: string) => {
      if (fieldName !== campo) return undefined;
      if (fieldName === "CH_LETIVA" && chMode === "adjust") {
        const delta = Number(adjustment);
        if (adjustment.trim() === "" || Number.isNaN(delta) || delta === 0) return "";
        return `${Number(atual.replace(/[^\d.-]/g, "")) + delta} h`;
      }
      const texto = String(newValue ?? "").trim();
      if (texto === "") return "";
      return fieldName === "CH_LETIVA" ? `${texto} h` : texto;
    };

    if (entityType === "teacher") {
      const docentes = catalog.teachers.filter((item) => linhasSelecionadas.has(item.row_number));
      if (!docentes.length) return null;
      const ativos = docentes.filter(
        (item) => item.status.trim().toLocaleUpperCase("pt-BR") === "ATIVO",
      ).length;
      return {
        total: docentes.length,
        substantivo: "docentes",
        destaque: {
          texto: ativos === docentes.length
            ? `${ativos} ativo(s)`
            : `${ativos} ativo(s) · ${docentes.length - ativos} fora de atividade`,
          tom: ativos === docentes.length ? ("ok" as const) : ("atencao" as const),
        },
        itens: docentes.map((item) => ({
          chave: String(item.row_number),
          titulo: `${item.name} · ${item.badge}`,
          selo: {
            texto: item.status.trim() || "sem status",
            tom: item.status.trim().toLocaleUpperCase("pt-BR") === "ATIVO"
              ? ("ok" as const)
              : ("atencao" as const),
          },
          campos: [
            { rotulo: "Cargo", valor: item.job_function || "—" },
            {
              rotulo: "Status",
              valor: item.status || "—",
              editando: fieldName === "STATUS",
              destino: destinoDe("STATUS", item.status),
            },
            {
              rotulo: "CH letiva",
              valor: `${item.teaching_capacity} h${item.contracted_capacity !== null ? ` de ${item.contracted_capacity} h` : ""}`,
              editando: fieldName === "CH_LETIVA",
              destino: destinoDe("CH_LETIVA", String(item.teaching_capacity)),
            },
            { rotulo: "Gestor", valor: item.manager || "—" },
            {
              rotulo: "Perfil",
              valor: item.profile || "—",
              editando: fieldName === "PERFIL_DISCIPLINA",
              destino: destinoDe("PERFIL_DISCIPLINA", item.profile),
            },
          ],
        })),
        entidades: docentes,
      };
    }

    const ofertas = catalog.offers.filter((item) => linhasSelecionadas.has(item.row_number));
    if (!ofertas.length) return null;
    const alocadas = ofertas.filter((item) => item.baseline_status === "ALOCADA").length;
    return {
      total: ofertas.length,
      substantivo: "ofertas",
      destaque: {
        texto: alocadas === ofertas.length
          ? `${alocadas} alocada(s) na base`
          : `${alocadas} alocada(s) · ${ofertas.length - alocadas} sem docente`,
        tom: alocadas === ofertas.length ? ("ok" as const) : ("atencao" as const),
      },
      itens: ofertas.map((item) => ({
        chave: String(item.row_number),
        titulo: item.discipline_name || item.discipline_code,
        selo: {
          texto: item.baseline_status === "ALOCADA"
            ? item.baseline_teacher_name || "alocada"
            : "sem docente",
          tom: item.baseline_status === "ALOCADA" ? ("ok" as const) : ("atencao" as const),
        },
        campos: [
          { rotulo: "Curso", valor: item.course_name || item.course || "—" },
          {
            rotulo: "Dia",
            valor: item.day || "—",
            editando: fieldName === "DIA_AULA",
            destino: destinoDe("DIA_AULA", item.day),
          },
          {
            rotulo: "Horário",
            valor: item.time || "—",
            editando: fieldName === "HORÁRIO",
            destino: destinoDe("HORÁRIO", item.time),
          },
          {
            rotulo: "Ordem",
            valor: item.order || "—",
            editando: fieldName === "ORDEM",
            destino: destinoDe("ORDEM", item.order),
          },
          { rotulo: "Cluster", valor: item.cluster || "—" },
          {
            rotulo: "Perfil",
            valor: item.profile || "—",
            editando: fieldName === "PERFIL_DISCIPLINA",
            destino: destinoDe("PERFIL_DISCIPLINA", item.profile),
          },
        ],
      })),
      entidades: ofertas,
    };
  }, [catalog, entityType, fieldName, selectedRows, newValue, chMode, adjustment]);

  // Quantas linhas do conjunto o motor vai ignorar por ja estarem no valor
  // pedido. O ajuste relativo de CH nao tem valor de destino unico, entao a
  // conta nao se aplica.
  const jaNoValor = useMemo(() => {
    if (!resumoSelecao) return 0;
    if (fieldName === "CH_LETIVA" && chMode === "adjust") return 0;
    if (String(newValue).trim() === "") return 0;
    return resumoSelecao.entidades.filter((item) =>
      mesmoValor(valorAtualDoCampo(item as never, fieldName), newValue),
    ).length;
  }, [resumoSelecao, fieldName, newValue, chMode]);

  const conjuntoInocuo = Boolean(resumoSelecao) && jaNoValor === resumoSelecao!.total;

  const nomeDaLinha = (tipo: string, linha: number) => {
    if (tipo === "teacher") {
      const docente = catalog?.teachers.find((item) => item.row_number === linha);
      return docente ? `${docente.name} · ${docente.badge}` : `Docente · linha ${linha}`;
    }
    const oferta = catalog?.offers.find((item) => item.row_number === linha);
    return oferta ? `${oferta.discipline_name} · ${oferta.course}` : `Oferta · linha ${linha}`;
  };

  const renderValueControl = () => {
    if (fieldName === "STATUS") return <select disabled={readOnly} value={newValue} onChange={(event) => setNewValue(event.target.value)}><option value="">Selecione</option>{statusPraticados.map(([item, total]) => <option key={item} value={item}>{item}{total ? ` · ${total} docente(s) na base` : " · nao usado na base"}</option>)}</select>;
    if (fieldName === "DIA_AULA") return <select disabled={readOnly} value={newValue} onChange={(event) => setNewValue(event.target.value)}><option value="">Selecione</option>{dayOptions.map((item) => <option key={item} value={item}>{item}{agendaPraticada.dias.get(item) ? ` · ${agendaPraticada.dias.get(item)} oferta(s) hoje` : " · sem ofertas hoje"}</option>)}</select>;
    if (fieldName === "ORDEM") return <select disabled={readOnly} value={newValue} onChange={(event) => setNewValue(event.target.value)}><option value="">Selecione</option>{["1ª", "2ª", "ESTENDIDA"].map((item) => <option key={item}>{item}</option>)}</select>;
    if (fieldName === "HORÁRIO") {
      // Lista fechada: inventar um horario nao praticado nao tem significado
      // operacional, e o campo livre so revelava o erro no envio.
      return agendaPraticada.horarios.length
        ? <select disabled={readOnly} value={newValue} onChange={(event) => setNewValue(event.target.value)}><option value="">Selecione</option>{agendaPraticada.horarios.map(([hora, total]) => <option key={hora} value={hora}>{hora} · {total} oferta(s) hoje</option>)}</select>
        : <input disabled={readOnly} type="text" placeholder="19:00" value={newValue} onChange={(event) => setNewValue(event.target.value)} />;
    }
    if (fieldName === "CH_LETIVA" && cargasPraticadas.length && !chLivre) {
      const trocarFonte = (fonte: "letiva" | "contratada") => {
        setChFonte(fonte);
        // Mantem o valor se ele tambem existir na outra fonte; caso contrario
        // limpa, para o campo nunca ficar exibindo uma opcao que sumiu.
        const destino = fonte === "contratada" ? cargasPorFonte.contratada : cargasPorFonte.letiva;
        if (!destino.some(([ch]) => String(ch) === newValue)) setNewValue("");
      };
      return <span className="scenario-ch-origem">
        {cargasPorFonte.contratada.length > 0 && (
          <span className="scenario-ch-fonte" role="group" aria-label="Origem das faixas de carga">
            <button
              type="button"
              className={chFonte === "letiva" ? "active" : ""}
              aria-pressed={chFonte === "letiva"}
              disabled={readOnly}
              onClick={() => trocarFonte("letiva")}
            >
              Faixas de CH letiva
            </button>
            <button
              type="button"
              className={chFonte === "contratada" ? "active" : ""}
              aria-pressed={chFonte === "contratada"}
              disabled={readOnly}
              onClick={() => trocarFonte("contratada")}
            >
              Faixas de CH contratada
            </button>
          </span>
        )}
        <select
          disabled={readOnly}
          value={newValue}
          onChange={(event) => {
            if (event.target.value === "__outro__") { setChLivre(true); setNewValue(""); return; }
            setNewValue(event.target.value);
          }}
        >
          <option value="">Selecione</option>
          {cargasPraticadas.map(([ch, total]) => <option key={ch} value={ch}>{ch}h · {total} docente(s) na base</option>)}
          <option value="__outro__">Outro valor…</option>
        </select>
        <small className="field-hint">
          {chFonte === "contratada"
            ? "Tipos de contrato existentes na base. O valor entra como nova CH letiva."
            : "Faixas de CH letiva efetivamente praticadas na base."}
        </small>
      </span>;
    }
    if (fieldName === "CH_LETIVA") {
      return <span className="scenario-ch-livre">
        <input disabled={readOnly} type="number" min={0} placeholder="Horas" value={newValue} onChange={(event) => setNewValue(event.target.value)} />
        {cargasPraticadas.length > 0 && <button type="button" className="text-action" disabled={readOnly} onClick={() => { setChLivre(false); setNewValue(""); }}>Voltar às cargas da base</button>}
      </span>;
    }
    if (fieldName === "PERFIL_DISCIPLINA" && perfisPraticados.length && !perfilLivre) {
      // Sao centenas de perfis, muitos com mais de cem caracteres: sem busca o
      // select corta justamente a parte que distingue um do outro.
      const termo = perfilBusca
        .normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("pt-BR").trim();
      const visiveis = termo
        ? perfisPraticados.filter(([perfil]) =>
            perfil.normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("pt-BR").includes(termo))
        : perfisPraticados;
      return <span className="scenario-ch-origem">
        <input
          className="scenario-entity-search"
          type="search"
          disabled={readOnly}
          value={perfilBusca}
          onChange={(event) => setPerfilBusca(event.target.value)}
          placeholder="Buscar perfil por area, curso ou termo"
          aria-label="Buscar perfil"
        />
        <select
          disabled={readOnly}
          value={newValue}
          onChange={(event) => {
            if (event.target.value === "__outro__") { setPerfilLivre(true); setNewValue(""); return; }
            setNewValue(event.target.value);
          }}
        >
          <option value="">{termo ? `${visiveis.length} de ${perfisPraticados.length} perfis` : `Selecione entre ${perfisPraticados.length} perfis`}</option>
          {visiveis.map(([perfil, total]) => <option key={perfil} value={perfil}>{perfil} · {total} {entityType === "teacher" ? "docente(s)" : "oferta(s)"} na base</option>)}
          <option value="__outro__">Outro perfil…</option>
        </select>
        <small className="field-hint">
          {entityType === "teacher"
            ? "Perfis que os docentes ja assumem na base."
            : "Perfis exigidos pelas ofertas na base."}
        </small>
      </span>;
    }
    if (fieldName === "PERFIL_DISCIPLINA") {
      return <span className="scenario-ch-livre">
        <input disabled={readOnly} type="text" placeholder="Novo perfil" value={newValue} onChange={(event) => setNewValue(event.target.value)} />
        {perfisPraticados.length > 0 && <button type="button" className="text-action" disabled={readOnly} onClick={() => { setPerfilLivre(false); setNewValue(""); }}>Voltar aos perfis da base</button>}
      </span>;
    }
    return <input disabled={readOnly} type="text" placeholder="Novo valor" value={newValue} onChange={(event) => setNewValue(event.target.value)} />;
  };

  return <div className="page-container">
    <div className="page-heading"><div><h1>Cenários de reajuste</h1><p>Simule o futuro em um motor secundário, compare com a alocação oficial e homologue somente o resultado escolhido.</p></div><span className="phase-badge">Motor secundário isolado</span></div>
    <section className="scenario-mode" role="group" aria-label="Modo de simulação">
      <button type="button" className={mode === "single" ? "active" : ""} aria-pressed={mode === "single"} onClick={() => setMode("single")}>
        <strong>Cenário de um módulo</strong><small>Uma rodada-base, uma pergunta.</small>
      </button>
      <button type="button" className={mode === "batch" ? "active" : ""} aria-pressed={mode === "batch"} onClick={() => setMode("batch")}>
        <strong>Estudo em lote</strong><small>A mesma pergunta ao longo dos módulos do ano.</small>
      </button>
    </section>

    {mode === "batch" && <StudyPanel />}

    {mode === "single" && <>
    {error && <div className="alert error" role="alert">{error}</div>}
    {initialLoading && <LoadingState title="Carregando o ambiente de cenários" description="Rodadas-base, cenários salvos e estados de auditoria estão sendo recuperados." />}

    {/* Sem rodada concluida nao ha baseline para comparar, e todo o
        configurador abaixo ficaria oferecendo controles que nao levam a
        simulacao nenhuma. O estudo em lote ja se comportava assim. */}
    {!initialLoading && !jobs.length && <section className="empty-state panel">
      <span aria-hidden="true">◈</span>
      <h2>Execute uma alocação para liberar os cenários</h2>
      <p>O cenário de um módulo simula alterações sobre uma rodada oficial concluída e compara os dois resultados. É preciso ter ao menos uma rodada concluída.</p>
      <a className="button primary" href="#/processamento">Ir para Processamento</a>
    </section>}

    {!initialLoading && jobs.length > 0 && <section className="panel scenario-intro">
      <div><h2>Escolha a rodada oficial de comparação</h2><p>Cada cenário terá sua própria fonte, solução, auditoria e diferenças em relação a esta rodada.</p></div>
      <div className="scenario-intro-controls">
        <div className="scenario-select-action"><RoundPicker label="Rodada-base" jobs={jobs} value={active?.baseline_job_id ?? baseline} onChange={setBaseline} disabled={Boolean(active)} emptyLabel="Execute uma rodada primeiro" /><button type="button" className="scenario-reset-trigger" disabled={!jobs.length || busy} onClick={() => setResetTarget("baseline")}>Zerar rodadas-base</button></div>
        <div className="scenario-select-action"><label className="field"><span>Cenário salvo</span><select value={active?.id ?? ""} onChange={(event) => { const selected = scenarios.find((item) => item.id === event.target.value) ?? null; setActive(selected); setConfiguratorOpen(Boolean(selected)); }}><option value="">Novo cenário</option>{scenarios.map((item) => <option value={item.id} key={item.id}>{item.name} · Módulo {item.module} · {humanizeStatus(item.status)}</option>)}</select></label><button type="button" className="scenario-reset-trigger" disabled={!scenarios.length || busy} onClick={() => setResetTarget("scenario")}>Zerar cenários salvos</button></div>
      </div>
    </section>}

    {resetTarget && <section ref={resetDialogRef} className="scenario-reset-confirmation" role="dialog" aria-modal="true" aria-labelledby="reset-title" aria-describedby="reset-description"><div><span className="step-kicker">CONFIRMAÇÃO</span><h2 id="reset-title">{resetTarget === "baseline" ? "Zerar rodadas-base" : "Zerar cenários salvos"}</h2><p id="reset-description">{resetTarget === "baseline" ? "Ao remover uma rodada-base, seus cenários vinculados também serão excluídos." : "As rodadas-base serão preservadas; somente os cenários e suas simulações serão excluídos."} Esta ação não pode ser desfeita.</p></div><div className="scenario-reset-actions"><button ref={resetCancelRef} type="button" className="button secondary" disabled={busy} onClick={() => setResetTarget(null)}>Cancelar</button><button type="button" className="button secondary danger" disabled={busy} onClick={() => void handleReset("latest")}>Somente o último</button><button type="button" className="button primary danger" disabled={busy} onClick={() => void handleReset("all")}>Zerar todos</button></div></section>}

    {jobs.length > 0 && <section className="scenario-workflow" aria-label="Fluxo de cenários"><div className="active"><span>01</span><strong>Escolher movimento</strong></div><div className={configuratorOpen ? "active" : ""}><span>02</span><strong>Editar premissas</strong></div><div className={active?.latest_job ? "active" : ""}><span>03</span><strong>Reprocessar e auditar</strong></div><div className={comparison ? "active" : ""}><span>04</span><strong>Comparar e decidir</strong></div></section>}

    {jobs.length > 0 && <div className="executive-moves">{executiveMoves.map((item) => <button type="button" className={selectedMove === item.key ? "active" : ""} aria-pressed={selectedMove === item.key} onClick={() => resetEditor(item.key)} key={item.title}><span>{item.icon}</span><div><strong>{item.title}</strong><small>{item.decision}</small></div></button>)}</div>}

    {jobs.length > 0 && <section className="panel scenario-builder-preview"><div><h2>{move.title}</h2><p>{move.decision}</p><div className="field-chips">{move.fields.map((field) => <span key={field}>{field}</span>)}</div></div><div className="impact-preview"><span>Impacto esperado</span><strong>{move.impact}</strong><small>A simulação nunca substituirá automaticamente a rodada oficial.</small></div><button className="button primary" disabled={(!baseline && !active) || readOnly} onClick={() => setConfiguratorOpen(true)}>{readOnly ? "Cenário somente leitura" : "Configurar cenário"}</button></section>}

    {configuratorOpen && !active && <form className="panel scenario-create" onSubmit={handleCreate}>
      <div className="section-title"><div><h2>Defina a pergunta da simulação</h2></div></div>
      <div className="scenario-create-grid">
        <label className="field"><span>Nome do cenário</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex.: Retorno de docentes licenciados" /></label>
        <label className="field scenario-description"><span>Objetivo e justificativa</span><input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Qual hipótese ou decisão será testada?" /></label>
        <button className="button primary" disabled={!baseline || name.trim().length < 3 || busy}>Criar e configurar</button>
      </div>
    </form>}

    {active && <>
      <section className="scenario-baseline-strip" aria-label="Resumo da baseline">
        <div><span>Baseline</span><strong>{active.baseline_round}</strong><small>Módulo {active.module}</small></div>
        <div><span>Cobertura original</span><strong>{baselineSummary ? percent(baselineCoverage) : "—"}</strong><small>{baselineSummary ? `${count(baselineSummary.allocated)}/${count(baselineSummary.transmissions)} ofertas` : "Carregando baseline"}</small></div>
        <div><span>Pendências</span><strong>{baselineSummary?.unassigned ?? "—"}</strong><small>antes da simulação</small></div>
        <div><span>Premissas</span><strong>{premiseCount}</strong><small>alterações e políticas</small></div>
        <div><span>Status</span><StatusBadge value={active.status} /><small>{active.official_job_id ? "resultado oficial" : "ambiente isolado"}</small></div>
      </section>

      <BaselineGapGuide summary={baselineSummary} />

      {readOnly && <section className="scenario-readonly-notice" role="status"><div><span className="step-kicker">CENÁRIO HOMOLOGADO</span><strong>Este cenário está em modo somente leitura</strong><p>Premissas, políticas e o resultado oficial permanecem preservados. Crie um novo cenário para testar outra hipótese.</p></div><button type="button" className="button secondary" onClick={() => { setBaseline(active.baseline_job_id); setActive(null); setConfiguratorOpen(true); setName(`${active.name} · nova hipótese`); setDescription(active.description); }}>Criar novo cenário</button></section>}

      {configuratorOpen && <section className="panel scenario-builder-live">
        <div className="section-title"><div><h2>{move.title}</h2><p>{move.decision}</p></div><span className="scenario-capability ready">Funcional no motor secundário</span></div>
        {catalogLoading && <div className="inline-loading" role="status"><span className="mini-spinner" aria-hidden="true" />Carregando catálogo da rodada-base…</div>}
        {!catalogLoading && (advancedMove
          ? <ScenarioPolicyEditor move={selectedMove} catalog={catalog} targetType={policyTargetType} targetValues={policyTargetValues} busy={busy} readOnly={readOnly} onTargetType={(value) => { setPolicyTargetType(value); setPolicyTargetValues([]); }} onTargetValues={setPolicyTargetValues} onSubmit={handleAddPolicy} />
          : <form className="scenario-change-form scenario-batch-form" onSubmit={handleAddBatch}>
          {selectedMove === "COMPATIBILIDADE" && <label className="field"><span>Aplicar em</span><select disabled={readOnly} value={entityType} onChange={(event) => { setEntityType(event.target.value as EntityType); setSelectedRows([]); setNewValue(""); setPerfilLivre(false); setPerfilBusca(""); setBatchFeedback(null); }}><option value="teacher">Docente</option><option value="offer">Oferta</option></select></label>}
          <ScenarioEntityPicker
            entityType={entityType}
            teachers={catalog?.teachers ?? []}
            offers={catalog?.offers ?? []}
            selected={selectedRows}
            onSelectedChange={(rows) => { setSelectedRows(rows); setBatchFeedback(null); }}
            disabled={readOnly || busy}
          />
          {/* Com um alvo, o registro inteiro da baseline; com varios, o
              resumo do conjunto. Antes o segundo clique apagava o painel e
              devolvia o operador a tela cega do estado anterior. */}
          {entidadeSelecionada && <ScenarioEntityContext
            offer={entityType === "offer" ? entidadeSelecionada as never : null}
            teacher={entityType === "teacher" ? entidadeSelecionada as never : null}
            fieldName={fieldName}
            newValue={newValue}
          />}
          {resumoSelecao && <SelectionSummary
            total={resumoSelecao.total}
            substantivo={resumoSelecao.substantivo}
            destaque={resumoSelecao.destaque}
            itens={resumoSelecao.itens}
            aviso={jaNoValor
              ? `${jaNoValor} de ${resumoSelecao.total} já usam ${newValue} em ${fieldName} e serão ignorados: o motor só registra as linhas que mudam.`
              : undefined}
          />}
          <label className="field"><span>Campo</span><select disabled={readOnly} value={fieldName} onChange={(event) => { setFieldName(event.target.value); setNewValue(""); setChLivre(false); setPerfilLivre(false); setPerfilBusca(""); setBatchFeedback(null); }}>{fields.map((field) => <option key={field}>{field}</option>)}</select></label>
          {fieldName === "CH_LETIVA" && <fieldset className="scenario-ch-mode"><legend>Como aplicar a CH letiva</legend>
            <label><input type="radio" name="ch-mode" checked={chMode === "set"} disabled={readOnly} onChange={() => setChMode("set")} /> Definir o mesmo valor {selectedRows.length > 1 ? "para todos" : ""}</label>
            <label><input type="radio" name="ch-mode" checked={chMode === "adjust"} disabled={readOnly} onChange={() => setChMode("adjust")} /> Ajustar em horas, preservando as diferenças</label>
          </fieldset>}
          {fieldName === "CH_LETIVA" && chMode === "adjust"
            ? <label className="field"><span>Ajuste em horas</span><input type="number" step={1} disabled={readOnly} value={adjustment} onChange={(event) => setAdjustment(event.target.value)} placeholder="+2 ou -2" /><small className="field-hint">Cada docente sobe ou desce a partir da própria carga. Quem passar da CH contratada fica de fora, com o motivo registrado.</small></label>
            : <label className="field"><span>Novo valor</span>{renderValueControl()}</label>}
          {alteracaoInocua && <p className="inert-change" role="status">Este registro já usa <b>{valorAtual}</b> em {fieldName}. Escolha outro valor: uma premissa que repete o valor atual não muda o resultado da simulação.</p>}
          <button className="button primary" disabled={readOnly || busy || !selectedRows.length || alteracaoInocua || conjuntoInocuo || (fieldName === "CH_LETIVA" && chMode === "adjust" ? adjustment.trim() === "" || Number(adjustment) === 0 : newValue === "")}>
            {!selectedRows.length
              ? "Selecione ao menos um registro"
              : conjuntoInocuo
                ? "Nenhum registro mudaria com este valor"
                : selectedRows.length === 1 ? "Adicionar alteração" : `Aplicar a ${selectedRows.length} registros`}
          </button>
          {batchFeedback && <div className={`batch-feedback${batchFeedback.skipped.length ? " with-skips" : ""}`} role="status">
            <strong>{batchFeedback.applied_count} premissa(s) registrada(s){batchFeedback.skipped_count ? `, ${batchFeedback.skipped_count} ignorada(s)` : ""}.</strong>
            {batchFeedback.skipped.length > 0 && <ul>{batchFeedback.skipped.map((item) => <li key={item.row_number}>{nomeDaLinha(entityType, item.row_number)} — {item.reason}</li>)}</ul>}
          </div>}
        </form>)}
      </section>}

      <section className="panel scenario-change-set">
        <div className="section-title"><div><h2>Premissas antes da simulação</h2><p>Alterações de dados e políticas do solver são registradas separadamente e aplicadas apenas ao cenário.</p></div><button className="button primary" disabled={readOnly || !premiseCount || busy || Boolean(active.latest_job && !active.latest_job.terminal)} onClick={() => void handleRun()}>{active.latest_job && !active.latest_job.terminal ? "Simulando…" : "Executar simulação"}</button></div>
        {premiseCount ? <div className="table-wrap"><table><thead><tr><th>Movimento</th><th>Alvo</th><th>Regra</th><th>Configuração</th><th /></tr></thead><tbody>
          {active.changes.map((change) => <tr key={change.id}><td>{change.change_type}</td><td>{nomeDaLinha(change.entity_type, change.row_number)}<small>linha {change.row_number}</small></td><td><strong>{change.field_name}</strong></td><td>{String(change.old_value ?? "Vazio")} → <strong>{String(change.new_value)}</strong></td><td><button className="text-action danger" disabled={busy || readOnly} onClick={() => void handleDeleteChange(change.id)}>Remover</button></td></tr>)}
          {active.policies.map((policy) => <tr key={policy.id}><td>{policy.policy_type}</td><td>{policy.target_type} · {policy.target_value}</td><td><strong>Política do motor secundário</strong></td><td>{policy.policy_type === "FIXAR" ? `Chapa ${String(policy.configuration.teacher_badge)}` : "Restrição ativa"}</td><td><button className="text-action danger" disabled={busy || readOnly} onClick={() => void handleDeletePolicy(policy.id)}>Remover</button></td></tr>)}
        </tbody></table></div> : <div className="chart-empty">Configure um dos seis movimentos para liberar a simulação.</div>}
        {active.latest_job && <div className="scenario-run-state"><span className={active.latest_job.terminal ? `status-${statusTone(active.latest_job.status)}` : "pulse"} /><div><StatusBadge value={active.latest_job.status} /><small>{active.latest_job.message}</small></div></div>}
      </section>

      {comparisonLoading && <LoadingState title="Comparando baseline e cenário" description="Deltas, trocas de docente e guardrails estão sendo consolidados." />}
      {comparison && <section className="scenario-comparison-section">
        <div className="section-title"><div><h2>Impacto da simulação</h2><p>Os deltas abaixo foram recalculados sobre a solução auditada do motor secundário.</p></div></div>
        <div className="kpi-grid scenario-kpis">
          <ScenarioMetricCard featured title="Cobertura simulada" value={percent(comparison.kpis.scenario_coverage_pct)} delta={comparison.kpis.coverage_delta_pp} positiveIsGood detail={`${signed(comparison.kpis.coverage_delta_pp, " pp")} vs. baseline`} />
          <ScenarioMetricCard title="Ofertas alocadas" value={signed(comparison.kpis.allocated_delta)} delta={comparison.kpis.allocated_delta} positiveIsGood detail={`${comparison.differences.recovered.length} recuperadas · ${comparison.differences.lost.length} perdidas`} />
          <ScenarioMetricCard title="Demanda pendente" value={signed(comparison.kpis.unassigned_hours_delta, "h")} delta={comparison.kpis.unassigned_hours_delta} positiveIsGood={false} detail="delta de horas não cobertas" />
          <article className="kpi-card"><span>Estabilidade</span><strong>{percent(comparison.kpis.assignment_stability_pct)}</strong><small>{comparison.differences.reassigned.length} trocas de docente</small></article>
          <ScenarioMetricCard title="1ª etapa" value={signed(comparison.kpis.first_stage_hours_delta, "h")} delta={comparison.kpis.first_stage_hours_delta} positiveIsGood detail="delta de horas alocadas" />
          <ScenarioMetricCard title="2ª etapa" value={signed(comparison.kpis.second_stage_hours_delta, "h")} delta={comparison.kpis.second_stage_hours_delta} positiveIsGood detail="delta de horas alocadas" />
          <ScenarioMetricCard title="Horas internas" value={signed(comparison.kpis.internal_allocated_hours_delta, "h")} delta={comparison.kpis.internal_allocated_hours_delta} positiveIsGood detail="delta de alocações em contratos CLT" />
          <ScenarioMetricCard title="Exposição externa" value={signed(comparison.kpis.external_allocated_hours_delta, "h")} delta={comparison.kpis.external_allocated_hours_delta} positiveIsGood={false} detail="delta de horas fora do quadro interno" />
        </div>
        <div className="scenario-guardrail-results" aria-label="Guardrails para homologação"><span>Validação <StatusBadge value={comparison.guardrails.validation} /></span><span>Solver <StatusBadge value={comparison.guardrails.solver} /></span><span>Auditoria <StatusBadge value={comparison.guardrails.audit} /></span></div>
        <div className="scenario-difference-grid">
          <DifferenceList title="Ofertas recuperadas" items={comparison.differences.recovered} empty="Nenhuma oferta recuperada." />
          <DifferenceList title="Ofertas perdidas" items={comparison.differences.lost} empty="Nenhuma oferta perdeu cobertura." />
          <DifferenceList title="Docentes alterados" items={comparison.differences.reassigned} empty="Nenhuma troca de docente." />
        </div>
        <div className="scenario-promotion"><div><h2>Aplicar como resultado final</h2><p>A baseline e o resultado oficial anterior permanecerão arquivados e reversíveis.</p>{promotionBlockers.length > 0 && <div className="promotion-blockers" role="alert"><strong>Homologação bloqueada</strong><ul>{promotionBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></div>}</div><button className="button primary" disabled={!comparison.guardrails.eligible_for_promotion || busy || readOnly} onClick={() => void handlePromote()}>{readOnly ? "Cenário homologado" : "Homologar e aplicar"}</button></div>
      </section>}
    </>}
    </>}
  </div>;
}

function ScenarioPolicyEditor({
  move, catalog, targetType, targetValues, busy, readOnly, onTargetType, onTargetValues, onSubmit,
}: {
  move: MoveKey;
  catalog: ScenarioCatalog | null;
  targetType: string;
  targetValues: string[];
  busy: boolean;
  readOnly: boolean;
  onTargetType: (value: string) => void;
  onTargetValues: (values: string[]) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  // A busca do proprio MultiSelect cobre o que o campo separado fazia aqui.
  const fixedOffers = catalog?.offers.filter(
    (item) => item.baseline_status === "ALOCADA" && item.baseline_teacher_badge,
  ) ?? [];
  return <form className="scenario-policy-form" onSubmit={onSubmit}>
    {move === "ALOCAR_CLUSTER" && <><div className="scenario-policy-explanation"><strong>Flexibilização de perfil dentro do cluster</strong><p>O docente é considerado do cluster quando algum perfil dele aparece nas ofertas desse cluster. O motor pode então recuperar lacunas sem exigir o perfil exato, preservando CH por etapa, agenda, status e limite Stricto.</p></div><div className="field scenario-entity-field"><MultiSelect disabled={readOnly} label="Clusters com lacunas" values={targetValues} onChange={onTargetValues} emptyLabel="Selecione" emptyHint="Nenhum" clearLabel="Limpar seleção" options={(catalog?.clusters ?? []).map((item) => ({ value: item.name, label: `${item.name} · ${item.unassigned_offers} oferta(s) sem alocação` }))} /></div></>}
    {move === "PRIORIDADE" && <>
      <label className="field"><span>Proteger</span><select disabled={readOnly} value={targetType} onChange={(event) => onTargetType(event.target.value)}><option value="COURSE">Curso completo</option><option value="OFFER">Oferta específica</option></select></label>
      <div className="field scenario-entity-field"><MultiSelect disabled={readOnly} label={targetType === "COURSE" ? "Cursos estratégicos" : "Ofertas estratégicas"} values={targetValues} onChange={onTargetValues} emptyLabel="Selecione" emptyHint="Nenhum" clearLabel="Limpar seleção" options={targetType === "COURSE"
        ? (catalog?.courses ?? []).map((item) => ({ value: item.code, label: `${item.name} · ${item.code}` }))
        : (catalog?.offers ?? []).map((item) => ({ value: String(item.row_number), label: `${item.discipline_name} · ${item.course} · ${item.order} · ${item.day} ${item.time} · ${item.baseline_status === "ALOCADA" ? item.baseline_teacher_name : "sem docente"}` }))} /></div>
      {targetType === "OFFER" && targetValues.length === 1 && <ScenarioEntityContext offer={catalog?.offers.find((item) => String(item.row_number) === targetValues[0])} />}
    </>}
    {move === "FIXAR" && <div className="field scenario-entity-field"><MultiSelect disabled={readOnly} label="Alocações da baseline a preservar" values={targetValues} onChange={onTargetValues} emptyLabel="Selecione" emptyHint="Nenhuma" clearLabel="Limpar seleção" options={fixedOffers.map((item) => ({ value: String(item.row_number), label: `${item.discipline_name} · ${item.course} · ${item.day} ${item.time} · ${item.baseline_teacher_name} (${item.baseline_teacher_badge})` }))} /></div>}
    {move === "FIXAR" && targetValues.length === 1 && <ScenarioEntityContext offer={catalog?.offers.find((item) => String(item.row_number) === targetValues[0])} />}
    <button className="button primary" disabled={readOnly || busy || !targetValues.length}>
      {targetValues.length > 1 ? `Adicionar ${targetValues.length} políticas` : "Adicionar política"}
    </button>
  </form>;
}

function DifferenceList({ title, items, empty }: { title: string; items: ScenarioComparison["differences"]["recovered"]; empty: string }) {
  return <article className="panel scenario-difference-card"><h3>{title}<span>{items.length}</span></h3>{items.length ? <ul tabIndex={0} aria-label={`${title}: ${items.length} registros`}>{items.map((item) => <li key={item.source_row}><strong>{item.discipline_name}</strong><span>{item.discipline_code} · linha {item.source_row}</span>{(item.before_teacher || item.after_teacher) && <small>{item.before_teacher || "Sem docente"} → {item.after_teacher || "Sem docente"}</small>}</li>)}</ul> : <p>{empty}</p>}</article>;
}
