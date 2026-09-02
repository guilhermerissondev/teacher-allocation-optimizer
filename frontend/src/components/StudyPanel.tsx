import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  addStudyPremise,
  createStudy,
  deleteStudy,
  deleteStudyPremise,
  getStudy,
  getStudyCatalog,
  getStudyComparison,
  getStudyProjection,
  listStudies,
  listStudyBaselines,
  promoteScenario,
  runStudy,
} from "../api";
import LoadingState from "./LoadingState";
import StatusBadge, { humanizeStatus, statusTone } from "./StatusBadge";
import SelectionSummary from "./SelectionSummary";
import StudyEntityContext from "./StudyEntityContext";
import StudyEntityPicker, { StudyFacetDef, StudyTarget } from "./StudyEntityPicker";
import { percent, signedNatural } from "../numberFormat";
import type {
  Study,
  StudyBaseline,
  StudyCatalog,
  StudyComparison,
  StudyModuleProjection,
  StudyOfferTarget,
} from "../types";

/**
 * Estudo em lote: a mesma premissa aplicada a vários módulos do ano letivo.
 *
 * O alvo aqui é a chapa do docente, e não a linha da planilha. Ao fatiar a
 * base anual por módulo, a linha de uma oferta muda de lugar, e amarrar a
 * premissa ao número da linha faria a mesma pergunta significar coisas
 * diferentes em cada recorte.
 */

const studyMoves = [
  {
    key: "CAPACIDADE" as const,
    icon: "CH",
    entity: "teacher" as const,
    title: "Reforçar ou reduzir capacidade",
    decision: "Demitir, afastar, retornar ou alterar a CH letiva de um docente em vários módulos.",
    fields: ["STATUS", "CH_LETIVA"],
  },
  {
    key: "AGENDA" as const,
    icon: "AG",
    entity: "offer" as const,
    title: "Reorganizar agenda",
    decision: "Mover um curso ou uma disciplina de dia, horário ou metade do módulo ao longo do ano.",
    fields: ["DIA_AULA", "HORÁRIO", "ORDEM"],
  },
  {
    key: "COMPATIBILIDADE" as const,
    icon: "PF",
    entity: "teacher" as const,
    title: "Ampliar compatibilidade",
    decision: "Alterar o perfil que o docente pode assumir ao longo do ano.",
    fields: ["PERFIL_DISCIPLINA"],
  },
];

type MoveKey = typeof studyMoves[number]["key"];

const moveFields: Record<MoveKey, string[]> = {
  CAPACIDADE: ["STATUS", "CH_LETIVA"],
  AGENDA: ["DIA_AULA", "HORÁRIO", "ORDEM"],
  COMPATIBILIDADE: ["PERFIL_DISCIPLINA"],
};

const fieldLabels: Record<string, string> = {
  STATUS: "Status",
  CH_LETIVA: "CH letiva",
  PERFIL_DISCIPLINA: "Perfil",
  DIA_AULA: "Dia da aula",
  "HORÁRIO": "Horário",
  ORDEM: "Ordem (metade do módulo)",
};

const statusOptions = [
  "ATIVO",
  "DEMITIDO",
  "LICENÇA MATER.",
  "LICENÇA MATER. COMPL. 180 DIAS",
];

function signed(value: number, suffix = "") {
  return signedNatural(value, suffix);
}

function deltaClass(value: number, positiveIsGood: boolean) {
  if (value === 0) return "delta-neutral";
  return (positiveIsGood ? value > 0 : value < 0)
    ? "delta-improvement"
    : "delta-regression";
}

/** Rótulo legível de uma premissa, do jeito que o operador a formulou. */
function premiseLabel(premise: Study["premises"][number]) {
  const alvo = premise.target_label || premise.target_value;
  if (premise.operation === "ADJUST") {
    return `${alvo} · ${premise.field_name} ${signed(Number(premise.value))}h`;
  }
  return `${alvo} · ${premise.field_name} → ${premise.value}`;
}

export default function StudyPanel() {
  const [baselines, setBaselines] = useState<StudyBaseline[]>([]);
  const [studies, setStudies] = useState<Study[]>([]);
  const [active, setActive] = useState<Study | null>(null);
  const [catalog, setCatalog] = useState<StudyCatalog | null>(null);
  const [projection, setProjection] = useState<StudyModuleProjection[]>([]);
  const [comparison, setComparison] = useState<StudyComparison | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const [batchId, setBatchId] = useState("");
  const [modules, setModules] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const [selectedMove, setSelectedMove] = useState<MoveKey>("CAPACIDADE");
  const [fieldName, setFieldName] = useState("STATUS");
  const [targetType, setTargetType] = useState<"TEACHER_BADGE" | "COURSE" | "DISCIPLINE">("TEACHER_BADGE");
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [newValue, setNewValue] = useState("");
  const [chMode, setChMode] = useState<"set" | "adjust">("set");
  const [adjustment, setAdjustment] = useState("");

  // O catálogo lê a rodada-base de cada módulo, então demora o suficiente para
  // merecer estado próprio: sem ele o seletor apareceria vazio e pareceria uma
  // base sem docentes.
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const detailRequest = useRef(0);

  useEffect(() => {
    let live = true;
    void Promise.all([listStudyBaselines(), listStudies()])
      .then(([baselineItems, studyItems]) => {
        if (!live) return;
        setBaselines(baselineItems);
        setStudies(studyItems);
        if (baselineItems[0]) {
          setBatchId(baselineItems[0].id);
          setModules(baselineItems[0].modules.map((item) => item.module));
        }
        if (studyItems[0]) setActive(studyItems[0]);
      })
      .catch((requestError: Error) => { if (live) setError(requestError.message); })
      .finally(() => { if (live) setInitialLoading(false); });
    return () => { live = false; };
  }, []);

  // Catálogo e projeção acompanham o estudo aberto. A projeção é o que diz, por
  // módulo, o que cada premissa produziu — é ela que revela um módulo onde a
  // premissa não teve efeito antes de gastar quatro simulações para descobrir.
  useEffect(() => {
    if (!active) {
      setCatalog(null);
      setProjection([]);
      setComparison(null);
      setCatalogLoading(false);
      return;
    }
    const requestId = ++detailRequest.current;
    let live = true;
    const current = requestId === detailRequest.current;
    setCatalogLoading(true);
    void getStudyCatalog(active.id)
      .then((payload) => { if (live && current) setCatalog(payload); })
      .catch((requestError: Error) => { if (live && current) { setCatalog(null); setError(requestError.message); } })
      .finally(() => { if (live && current) setCatalogLoading(false); });
    void getStudyProjection(active.id)
      .then((payload) => { if (live && current) setProjection(payload.modules); })
      .catch(() => { if (live && current) setProjection([]); });
    return () => { live = false; };
  }, [active?.id, active?.premises.length]);

  useEffect(() => {
    if (!active || active.status !== "CONCLUIDO") {
      if (active?.status !== "CONCLUIDO") setComparison(null);
      return;
    }
    let live = true;
    void getStudyComparison(active.id)
      .then((payload) => { if (live) setComparison(payload); })
      .catch((requestError: Error) => { if (live) setError(requestError.message); });
    return () => { live = false; };
  }, [active?.id, active?.status]);

  // Enquanto houver módulo na fila, o estudo é reconsultado inteiro: o que
  // interessa é o avanço do conjunto, e não o de uma simulação isolada.
  useEffect(() => {
    if (!active || active.status !== "EXECUTANDO") return;
    const timer = window.setInterval(async () => {
      try {
        const refreshed = await getStudy(active.id);
        setActive(refreshed);
        if (refreshed.status !== "EXECUTANDO") {
          window.clearInterval(timer);
          setStudies(await listStudies());
        }
      } catch (requestError) {
        setError((requestError as Error).message);
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active?.id, active?.status]);

  const selectedBaseline = baselines.find((item) => item.id === batchId) ?? null;
  const availableModules = selectedBaseline?.modules.map((item) => item.module) ?? [];
  const readOnly = Boolean(active && active.status === "EXECUTANDO");

  const move = studyMoves.find((item) => item.key === selectedMove) ?? studyMoves[0];
  const fields = moveFields[selectedMove];

  // Alvos e facetas do seletor. As facetas de docente repetem as do cenário
  // avulso; as de oferta trocam a linha da planilha pelo que só o lote sabe:
  // em que módulos o alvo existe e quantas lacunas ele deixou em cada um.
  const offerTargets = (list: StudyOfferTarget[]): StudyTarget[] => list.map((item) => ({
    key: item.code,
    label: `${item.name} (${item.code})`,
    detail: [
      `${item.total_offers} oferta(s)`,
      item.total_unassigned ? `${item.total_unassigned} sem alocação` : "tudo alocado",
      item.days.join("/") || "sem dia",
      item.modules.map((row) => `M${row.module}`).join(" "),
    ].join(" · "),
    facets: {
      module: item.modules.map((row) => `M${row.module}`),
      day: item.days.length ? item.days : ["sem dia"],
      gap: [item.total_unassigned ? "Com lacuna na base" : "Totalmente alocado"],
      ...(item.course_name ? { course: [item.course_name] } : {}),
    },
  }));

  const { targets, facetDefs, pickerLabel } = useMemo(() => {
    if (move.entity === "teacher") {
      return {
        pickerLabel: "Docentes",
        facetDefs: [
          { key: "capacity", label: "CH letiva", numeric: true },
          { key: "job_function", label: "Cargo" },
          { key: "status", label: "Status" },
          { key: "manager", label: "Gestor" },
        ] as StudyFacetDef[],
        targets: (catalog?.teachers ?? []).map((item) => ({
          key: item.badge,
          label: `${item.name} · ${item.badge}`,
          detail: `${item.job_function} · CH ${item.teaching_capacity}h${item.contracted_capacity ? ` de ${item.contracted_capacity}h` : ""} · ${item.status}`,
          facets: {
            capacity: [String(item.teaching_capacity ?? "")],
            job_function: [item.job_function],
            status: [item.status],
            manager: [item.manager],
          },
        })) as StudyTarget[],
      };
    }
    const isCourse = targetType === "COURSE";
    return {
      pickerLabel: isCourse ? "Cursos" : "Disciplinas",
      facetDefs: [
        { key: "module", label: "Existe no módulo" },
        { key: "gap", label: "Situação na base" },
        { key: "day", label: "Dia praticado" },
        ...(isCourse ? [] : [{ key: "course", label: "Curso" }]),
      ] as StudyFacetDef[],
      targets: offerTargets(
        (isCourse ? catalog?.courses : catalog?.disciplines) ?? [],
      ),
    };
  }, [catalog, move.entity, targetType]);

  const selectedTeacher = move.entity === "teacher" && selectedTargets.length === 1
    ? catalog?.teachers.find((item) => item.badge === selectedTargets[0]) ?? null
    : null;

  // Com um alvo só, o painel de contexto mostra o registro inteiro — a mesma
  // vantagem que o cenário de um módulo já tinha. Com vários, o registro de um
  // deles enganaria mais do que ajuda, então fica o resumo do próprio seletor.
  const selectedOfferTarget = move.entity === "offer" && selectedTargets.length === 1
    ? ((targetType === "COURSE" ? catalog?.courses : catalog?.disciplines) ?? [])
        .find((item) => item.code === selectedTargets[0]) ?? null
    : null;

  // Resumo do conjunto quando ha mais de um alvo. Vale o mesmo motivo da aba de
  // modulo unico: o segundo clique nao pode apagar a informacao da tela. O que
  // muda e o eixo — aqui o conjunto tambem se distribui pelos modulos do ano.
  const resumoSelecao = useMemo(() => {
    if (selectedTargets.length < 2 || !catalog) return null;
    const chaves = new Set(selectedTargets);
    // O destino fica por alvo: no ajuste relativo de CH cada docente parte de
    // uma carga diferente e chega a um numero diferente.
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

    if (move.entity === "teacher") {
      const docentes = catalog.teachers.filter((item) => chaves.has(item.badge));
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
          chave: item.badge,
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
      };
    }

    const lista = (targetType === "COURSE" ? catalog.courses : catalog.disciplines) ?? [];
    const alvos = lista.filter((item) => chaves.has(item.code));
    if (!alvos.length) return null;
    const totalOfertas = alvos.reduce((total, item) => total + item.total_offers, 0);
    const totalLacunas = alvos.reduce((total, item) => total + item.total_unassigned, 0);
    const juntar = (valores: string[]) => {
      const limpos = valores.map((valor) => valor.trim()).filter(Boolean);
      return limpos.length ? limpos.join(" / ") : "—";
    };

    return {
      total: alvos.length,
      substantivo: targetType === "COURSE" ? "cursos" : "disciplinas",
      destaque: {
        texto: totalLacunas === 0
          ? `${totalOfertas} oferta(s) · tudo alocado`
          : `${totalLacunas} de ${totalOfertas} oferta(s) sem docente`,
        tom: totalLacunas === 0 ? ("ok" as const) : ("atencao" as const),
      },
      itens: alvos.map((item) => ({
        chave: item.code,
        titulo: `${item.name} (${item.code})`,
        selo: {
          texto: item.total_unassigned === 0
            ? `${item.total_offers} oferta(s) · tudo alocado`
            : `${item.total_unassigned} de ${item.total_offers} sem docente`,
          tom: item.total_unassigned === 0 ? ("ok" as const) : ("atencao" as const),
        },
        campos: [
          // Em que modulos o alvo existe: e o que antecipa a premissa que vai
          // sair "sem efeito" nos recortes onde ele nao aparece.
          {
            rotulo: "Módulos",
            valor: juntar(item.modules.map((row) => `M${row.module}`)),
          },
          ...(targetType === "DISCIPLINE"
            ? [{ rotulo: "Curso", valor: item.course_name || item.course_code || "—" }]
            : []),
          {
            rotulo: "Dias praticados",
            valor: juntar(item.days),
            editando: fieldName === "DIA_AULA",
            destino: destinoDe("DIA_AULA", ""),
          },
          {
            rotulo: "Horários praticados",
            valor: juntar(item.times),
            editando: fieldName === "HORÁRIO",
            destino: destinoDe("HORÁRIO", ""),
          },
          {
            rotulo: "Ordens praticadas",
            valor: juntar(item.orders),
            editando: fieldName === "ORDEM",
            destino: destinoDe("ORDEM", ""),
          },
        ],
      })),
    };
  }, [catalog, move.entity, targetType, selectedTargets, fieldName, newValue, chMode, adjustment]);

  const projectionByModule = useMemo(
    () => new Map(projection.map((item) => [item.module, item])),
    [projection],
  );

  /** Quantos módulos aquela premissa alcançou, para a coluna de efeito. */
  const premiseReach = (premiseId: string) =>
    projection.map((item) => ({
      module: item.module,
      applied: item.results.find((row) => row.premise_id === premiseId)?.applied ?? 0,
      reason: item.results.find((row) => row.premise_id === premiseId)?.reason ?? "",
    }));

  const refresh = async (studyId: string) => {
    const [refreshed, list] = await Promise.all([getStudy(studyId), listStudies()]);
    setActive(refreshed);
    setStudies(list);
  };

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!batchId || !modules.length || name.trim().length < 3) return;
    setBusy(true);
    setError("");
    try {
      const created = await createStudy(batchId, [...modules].sort((a, b) => a - b), name, description);
      setActive(created);
      setStudies(await listStudies());
      setName("");
      setDescription("");
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ajusteRelativo = fieldName === "CH_LETIVA" && chMode === "adjust";
  const faltaParaPremissa = !selectedTargets.length
    ? "Selecione ao menos um alvo"
    : ajusteRelativo && (adjustment.trim() === "" || Number(adjustment) === 0)
      ? "Informe o ajuste em horas"
      : !ajusteRelativo && newValue === ""
        ? "Escolha o novo valor"
        : null;

  const handleAddPremise = async (event: FormEvent) => {
    event.preventDefault();
    if (!active || readOnly || !selectedTargets.length) return;
    const relativo = fieldName === "CH_LETIVA" && chMode === "adjust";
    if (relativo && (adjustment.trim() === "" || Number(adjustment) === 0)) return;
    if (!relativo && newValue === "") return;
    setBusy(true);
    setError("");
    try {
      const result = await addStudyPremise(active.id, {
        premise_type: selectedMove,
        target_type: targetType,
        target_values: selectedTargets,
        field_name: fieldName,
        ...(relativo
          ? { adjustment: Number(adjustment) }
          : { new_value: fieldName === "CH_LETIVA" ? Number(newValue) : newValue }),
      });
      setActive(result.study);
      setProjection(result.projection);
      setStudies(await listStudies());
      setNewValue("");
      setAdjustment("");
      setSelectedTargets([]);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeletePremise = async (premiseId: string) => {
    if (!active || readOnly) return;
    setBusy(true);
    setError("");
    try {
      await deleteStudyPremise(active.id, premiseId);
      await refresh(active.id);
      setProjection((await getStudyProjection(active.id)).modules);
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
      setActive(await runStudy(active.id));
      setStudies(await listStudies());
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handlePromote = async (scenarioId: string, module: number) => {
    if (!active) return;
    if (!window.confirm(`Homologar a simulação do módulo ${module} como resultado final? O histórico anterior será preservado.`)) return;
    setBusy(true);
    setError("");
    try {
      await promoteScenario(scenarioId);
      await refresh(active.id);
      setComparison(await getStudyComparison(active.id));
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteStudy = async () => {
    if (!active) return;
    setBusy(true);
    setError("");
    try {
      await deleteStudy(active.id);
      const list = await listStudies();
      setStudies(list);
      setActive(list[0] ?? null);
      setConfirmDelete(false);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const valueEditor = () => {
    if (fieldName === "STATUS") {
      return <label className="field"><span>Novo status</span>
        <select disabled={readOnly} value={newValue} onChange={(event) => setNewValue(event.target.value)}>
          <option value="">Selecione</option>
          {statusOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>;
    }
    if (fieldName === "CH_LETIVA") {
      return <div className="study-ch-editor">
        <div className="study-ch-mode" role="group" aria-label="Forma do ajuste de CH">
          <button type="button" className={chMode === "set" ? "active" : ""} aria-pressed={chMode === "set"} disabled={readOnly} onClick={() => setChMode("set")}>Definir valor</button>
          <button type="button" className={chMode === "adjust" ? "active" : ""} aria-pressed={chMode === "adjust"} disabled={readOnly} onClick={() => setChMode("adjust")}>Somar ou subtrair</button>
        </div>
        {chMode === "set"
          ? <label className="field"><span>Nova CH letiva (h)</span><input disabled={readOnly} type="number" min={0} value={newValue} onChange={(event) => setNewValue(event.target.value)} /></label>
          : <label className="field"><span>Ajuste (h)</span><input disabled={readOnly} type="number" placeholder="Ex.: -4" value={adjustment} onChange={(event) => setAdjustment(event.target.value)} /></label>}
        {selectedTeacher && <small className="study-hint">Hoje: {selectedTeacher.teaching_capacity}h letivas{selectedTeacher.contracted_capacity !== null ? ` · teto contratado ${selectedTeacher.contracted_capacity}h` : ""}</small>}
      </div>;
    }
    if (fieldName === "DIA_AULA" || fieldName === "HORÁRIO" || fieldName === "ORDEM") {
      // Só o que a operação realmente pratica no ano. Oferecer um horário que
      // não existe na base produziria uma simulação que não responde a nada.
      const praticado = fieldName === "DIA_AULA"
        ? catalog?.practiced.days ?? []
        : fieldName === "HORÁRIO"
          ? catalog?.practiced.times ?? []
          : catalog?.practiced.orders ?? [];
      return <label className="field"><span>Novo {fieldLabels[fieldName].toLocaleLowerCase("pt-BR")}</span>
        <select disabled={readOnly} value={newValue} onChange={(event) => setNewValue(event.target.value)}>
          <option value="">Selecione</option>
          {praticado.map((item) => <option key={item.value} value={item.value}>{item.value} · {item.offers} oferta(s) hoje</option>)}
        </select>
      </label>;
    }
    return <label className="field"><span>Novo perfil</span><input disabled={readOnly} type="text" placeholder="Ex.: GESTÃO" value={newValue} onChange={(event) => setNewValue(event.target.value)} /></label>;
  };

  if (initialLoading) {
    return <LoadingState title="Carregando os estudos em lote" description="Lotes com rodada concluída e estudos salvos estão sendo recuperados." />;
  }

  return <>
    {error && <div className="alert error" role="alert">{error}</div>}

    {!baselines.length && <section className="empty-state panel">
      <span aria-hidden="true">▦</span>
      <h2>Processe um lote para liberar o estudo</h2>
      <p>O estudo em lote compara cada módulo do ano com a sua própria rodada oficial. É preciso ter um lote com ao menos um módulo concluído.</p>
      <a className="button primary" href="#/processamento">Ir para Processamento</a>
    </section>}

    {baselines.length > 0 && <section className="panel study-scope">
      <div className="section-title">
        <div><span className="step-kicker">01 · ESCOPO DO ESTUDO</span><h2>Escolha o lote-base e os módulos</h2><p>Cada módulo é resolvido separadamente e comparado com a sua própria rodada oficial.</p></div>
        <label className="field"><span>Estudo salvo</span>
          <select value={active?.id ?? ""} onChange={(event) => setActive(studies.find((item) => item.id === event.target.value) ?? null)}>
            <option value="">Novo estudo</option>
            {studies.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.modules.length} módulo(s) · {humanizeStatus(item.status)}</option>)}
          </select>
        </label>
      </div>

      {!active && <form className="study-scope-form" onSubmit={handleCreate}>
        <label className="field"><span>Lote-base</span>
          <select value={batchId} onChange={(event) => {
            setBatchId(event.target.value);
            const option = baselines.find((item) => item.id === event.target.value);
            setModules(option?.modules.map((item) => item.module) ?? []);
          }}>
            {baselines.map((item) => <option key={item.id} value={item.id}>{item.name} · módulos {item.modules.map((row) => row.module).join(", ")}</option>)}
          </select>
        </label>

        <fieldset className="study-modules">
          <legend>Módulos do estudo</legend>
          <div className="study-module-presets">
            {availableModules.map((item) => (
              <button type="button" key={`from-${item}`} className="text-action" onClick={() => setModules(availableModules.filter((value) => value >= item))}>A partir do {item}</button>
            ))}
            <button type="button" className="text-action" onClick={() => setModules(availableModules)}>Ano inteiro</button>
          </div>
          <div className="study-module-checks">
            {availableModules.map((item) => (
              <label key={item} className={modules.includes(item) ? "active" : ""}>
                <input
                  type="checkbox"
                  checked={modules.includes(item)}
                  onChange={(event) => setModules((previous) => event.target.checked
                    ? [...previous, item]
                    : previous.filter((value) => value !== item))}
                />
                <span>Módulo {item}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="field"><span>Nome do estudo</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex.: Demitir chapa 12345 a partir do módulo 51" /></label>
        <label className="field"><span>Pergunta que o estudo responde</span><input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="O que você quer descobrir com esta simulação?" /></label>
        <button className="button primary" disabled={!batchId || !modules.length || name.trim().length < 3 || busy}>Criar estudo</button>
      </form>}

      {active && <div className="study-active-header">
        <div>
          <strong>{active.name}</strong>
          <small>{active.description || "Sem descrição"}</small>
          <div className="study-module-chips">{active.modules.map((item) => <span key={item.module}>Módulo {item.module}</span>)}</div>
        </div>
        <div className="study-active-actions">
          <StatusBadge value={active.status} />
          <button type="button" className="scenario-reset-trigger" disabled={busy || readOnly} onClick={() => setConfirmDelete(true)}>Excluir estudo</button>
        </div>
      </div>}
    </section>}

    {confirmDelete && active && <section className="scenario-reset-confirmation" role="dialog" aria-modal="true" aria-labelledby="study-delete-title">
      <div><span className="step-kicker">CONFIRMAÇÃO</span><h2 id="study-delete-title">Excluir o estudo</h2><p>As simulações de todos os módulos deste estudo serão removidas. As rodadas-base do lote permanecem intactas. Esta ação não pode ser desfeita.</p></div>
      <div className="scenario-reset-actions">
        <button type="button" className="button secondary" disabled={busy} onClick={() => setConfirmDelete(false)}>Cancelar</button>
        <button type="button" className="button primary danger" disabled={busy} onClick={() => void handleDeleteStudy()}>Excluir estudo</button>
      </div>
    </section>}

    {active && <section className="panel study-premises">
      <div className="section-title"><div><span className="step-kicker">02 · PREMISSAS</span><h2>O que muda em todos os módulos escolhidos</h2><p>O alvo é o docente, o curso ou a disciplina — nunca a linha da planilha. É o que faz a mesma pergunta valer em cada módulo do estudo.</p></div></div>

      <div className="executive-moves">{studyMoves.map((item) => (
        <button type="button" key={item.key} className={selectedMove === item.key ? "active" : ""} aria-pressed={selectedMove === item.key} disabled={readOnly} onClick={() => {
          setSelectedMove(item.key);
          setFieldName(moveFields[item.key][0]);
          setTargetType(item.entity === "teacher" ? "TEACHER_BADGE" : "COURSE");
          setSelectedTargets([]);
          setNewValue("");
          setAdjustment("");
          setChMode("set");
        }}>
          <span>{item.icon}</span><div><strong>{item.title}</strong><small>{item.decision}</small></div>
        </button>
      ))}</div>

      {move.entity === "offer" && <div className="study-target-mode" role="group" aria-label="Tipo de alvo">
        <button type="button" className={targetType === "COURSE" ? "active" : ""} aria-pressed={targetType === "COURSE"} disabled={readOnly} onClick={() => { setTargetType("COURSE"); setSelectedTargets([]); }}>Curso inteiro</button>
        <button type="button" className={targetType === "DISCIPLINE" ? "active" : ""} aria-pressed={targetType === "DISCIPLINE"} disabled={readOnly} onClick={() => { setTargetType("DISCIPLINE"); setSelectedTargets([]); }}>Disciplina específica</button>
      </div>}

      <StudyEntityPicker
        label={pickerLabel}
        targets={targets}
        facetDefs={facetDefs}
        selected={selectedTargets}
        onSelectedChange={setSelectedTargets}
        disabled={readOnly || catalogLoading}
      />

      {(selectedTeacher || selectedOfferTarget) && <StudyEntityContext
        teacher={selectedTeacher}
        target={selectedOfferTarget}
        targetKind={targetType === "DISCIPLINE" ? "DISCIPLINE" : "COURSE"}
        studyModules={active.modules.map((item) => item.module)}
        fieldName={fieldName}
        newValue={newValue}
        chMode={chMode}
        adjustment={adjustment}
      />}

      {resumoSelecao && <SelectionSummary
        total={resumoSelecao.total}
        substantivo={resumoSelecao.substantivo}
        destaque={resumoSelecao.destaque}
        itens={resumoSelecao.itens}
      />}

      <form className="study-premise-form" onSubmit={handleAddPremise}>
        <label className="field"><span>Campo</span>
          <select disabled={readOnly} value={fieldName} onChange={(event) => { setFieldName(event.target.value); setNewValue(""); setAdjustment(""); }}>
            {fields.map((item) => <option key={item} value={item}>{fieldLabels[item] ?? item}</option>)}
          </select>
        </label>
        {valueEditor()}
        <button className="button primary" disabled={readOnly || busy || Boolean(faltaParaPremissa)}>
          {faltaParaPremissa
            ?? (selectedTargets.length > 1
              ? `Adicionar ${selectedTargets.length} premissas`
              : "Adicionar premissa")}
        </button>
      </form>

      {active.premises.length === 0
        ? <p className="study-hint">Nenhuma premissa ainda. O estudo só pode ser simulado depois que algo mudar.</p>
        : <table className="study-premise-table">
          <caption className="sr-only">Premissas do estudo e o efeito de cada uma por módulo</caption>
          <thead><tr><th scope="col">Premissa</th>{active.modules.map((item) => <th scope="col" key={item.module}>M{item.module}</th>)}<th scope="col"><span className="sr-only">Ações</span></th></tr></thead>
          <tbody>
            {active.premises.map((premise) => {
              const reach = premiseReach(premise.id);
              return <tr key={premise.id}>
                <th scope="row">{premiseLabel(premise)}</th>
                {active.modules.map((item) => {
                  const cell = reach.find((row) => row.module === item.module);
                  const applied = cell?.applied ?? 0;
                  return <td key={item.module} className={applied ? "study-cell-applied" : "study-cell-empty"} title={cell?.reason || undefined}>
                    {applied ? `${applied} linha${applied > 1 ? "s" : ""}` : "sem efeito"}
                  </td>;
                })}
                <td><button type="button" className="text-action danger" disabled={readOnly || busy} onClick={() => void handleDeletePremise(premise.id)}>Remover</button></td>
              </tr>;
            })}
          </tbody>
        </table>}

      {/* Um módulo em que nada foi aplicado não vai para a fila. Dizer isso aqui
          evita que o operador leia o resultado como "o corte não teve efeito". */}
      {projection.some((item) => !item.applied_count) && active.premises.length > 0 && <div className="alert warning" role="status">
        <strong>Módulos sem alteração projetada: {projection.filter((item) => !item.applied_count).map((item) => `M${item.module}`).join(", ")}.</strong>
        <span> Eles não serão simulados. Passe o cursor sobre a célula "sem efeito" para ver o motivo.</span>
      </div>}
    </section>}

    {active && <section className="panel study-run">
      <div className="section-title">
        <div><span className="step-kicker">03 · SIMULAR</span><h2>Reprocessar cada módulo</h2><p>As simulações rodam em série no motor secundário: um estudo de quatro módulos leva cerca de quatro vezes o tempo de um cenário único.</p></div>
        <button className="button primary" disabled={busy || readOnly || !active.totals.runnable} onClick={() => void handleRun()}>
          {active.status === "EXECUTANDO" ? "Simulando…" : `Simular ${active.totals.runnable} módulo(s)`}
        </button>
      </div>
      <table className="study-module-table">
        <caption className="sr-only">Estado da simulação de cada módulo</caption>
        <thead><tr><th scope="col">Módulo</th><th scope="col">Premissas</th><th scope="col">Estado</th><th scope="col">Cobertura base</th><th scope="col">Cobertura simulada</th><th scope="col">Δ</th></tr></thead>
        <tbody>
          {active.modules.map((item) => {
            const delta = item.kpis && item.baseline_kpis
              ? Number((item.kpis.coverage_pct - item.baseline_kpis.coverage_pct).toFixed(2))
              : null;
            const locked = projectionByModule.get(item.module)?.locked;
            return <tr key={item.module}>
              <th scope="row">Módulo {item.module}{item.promoted && <span className="study-flag">homologado</span>}</th>
              <td>{item.change_count || (locked ? "—" : "nenhuma")}</td>
              <td>{item.stale
                ? <span className="study-stale">premissas mudaram · resultado desatualizado</span>
                : item.job
                  ? <StatusBadge value={item.job.status} />
                  : <span className="study-hint">não simulado</span>}</td>
              <td>{item.baseline_kpis ? percent(item.baseline_kpis.coverage_pct) : "—"}</td>
              <td>{item.kpis ? percent(item.kpis.coverage_pct) : "—"}</td>
              <td className={delta === null ? "" : deltaClass(delta, true)}>{delta === null ? "—" : `${signed(delta)} p.p.`}</td>
            </tr>;
          })}
        </tbody>
      </table>
    </section>}

    {active && active.totals.compared > 0 && <section className="panel study-results">
      <div className="section-title"><div><span className="step-kicker">04 · COMPARAR E DECIDIR</span><h2>Impacto consolidado do ano</h2><p>Somatório dos módulos já comparados. Cada módulo é homologado separadamente.</p></div></div>

      <div className="kpi-grid study-totals">
        <article className={`kpi-card scenario-delta-card ${deltaClass(active.totals.coverage_delta_pp, true)}`}><span>Cobertura do ano</span><strong>{signed(active.totals.coverage_delta_pp)} p.p.</strong><small>{active.totals.baseline_coverage_pct}% → {active.totals.coverage_pct}%</small></article>
        <article className={`kpi-card scenario-delta-card ${deltaClass(active.totals.allocated_delta, true)}`}><span>Ofertas alocadas</span><strong>{signed(active.totals.allocated_delta)}</strong><small>de {active.totals.baseline_offers} ofertas nos módulos comparados</small></article>
        <article className={`kpi-card scenario-delta-card ${deltaClass(active.totals.unassigned_delta, false)}`}><span>Ofertas sem alocação</span><strong>{signed(active.totals.unassigned_delta)}</strong><small>Quanto menor, melhor</small></article>
        <article className={`kpi-card scenario-delta-card ${deltaClass(active.totals.used_teachers_delta, false)}`}><span>Docentes utilizados</span><strong>{signed(active.totals.used_teachers_delta)}</strong><small>{active.totals.compared} de {active.totals.modules} módulos comparados</small></article>
      </div>

      {comparison?.modules.map((row) => {
        const detail = row.comparison;
        const moduleRow = active.modules.find((item) => item.module === row.module);
        return <article className="study-module-result" key={row.module}>
          <header>
            <div>
              <strong>Módulo {row.module}</strong>
              {detail
                ? <small>{detail.kpis.baseline_coverage_pct}% → {detail.kpis.scenario_coverage_pct}% · {signed(detail.kpis.coverage_delta_pp)} p.p. · estabilidade {detail.kpis.assignment_stability_pct}%</small>
                : <small>{row.reason || "Sem simulação concluída."}</small>}
            </div>
            <div className="study-module-result-actions">
              {detail && <button type="button" className="text-action" aria-expanded={expanded === row.module} onClick={() => setExpanded(expanded === row.module ? null : row.module)}>{expanded === row.module ? "Ocultar detalhes" : "Ver detalhes"}</button>}
              {detail && row.scenario_id && <button
                type="button"
                className="button primary"
                disabled={busy || !detail.guardrails.eligible_for_promotion || moduleRow?.promoted}
                onClick={() => void handlePromote(String(row.scenario_id), row.module)}
              >{moduleRow?.promoted ? "Homologado" : "Homologar módulo"}</button>}
            </div>
          </header>

          {detail && !detail.guardrails.eligible_for_promotion && !moduleRow?.promoted && <div className="promotion-blockers" role="status">
            <strong>Homologação bloqueada neste módulo</strong>
            <ul>
              {statusTone(detail.guardrails.validation) !== "success" && <li>Validação: {humanizeStatus(detail.guardrails.validation)}.</li>}
              {statusTone(detail.guardrails.solver) !== "success" && <li>Solver: {humanizeStatus(detail.guardrails.solver)}.</li>}
              {statusTone(detail.guardrails.audit) !== "success" && <li>Auditoria: {humanizeStatus(detail.guardrails.audit)}.</li>}
            </ul>
          </div>}

          {detail && expanded === row.module && <div className="study-module-detail">
            <div className="study-difference-grid">
              <div><span>Recuperadas</span><strong>{detail.differences.recovered.length}</strong><ul>{detail.differences.recovered.slice(0, 8).map((item) => <li key={item.source_row}>{item.discipline_name} → {item.after_teacher || "sem docente"}</li>)}</ul></div>
              <div><span>Perdidas</span><strong>{detail.differences.lost.length}</strong><ul>{detail.differences.lost.slice(0, 8).map((item) => <li key={item.source_row}>{item.discipline_name} ← {item.before_teacher || "sem docente"}</li>)}</ul></div>
              <div><span>Remanejadas</span><strong>{detail.differences.reassigned.length}</strong><ul>{detail.differences.reassigned.slice(0, 8).map((item) => <li key={item.source_row}>{item.discipline_name}: {item.before_teacher} → {item.after_teacher}</li>)}</ul></div>
            </div>
          </div>}
        </article>;
      })}
    </section>}
  </>;
}
