declare const __BUILD_STAMP__: string;
export const BUILD_STAMP = __BUILD_STAMP__;

export type ValidationIssue = {
  severity: string;
  code: string;
  sheet: string;
  column: string;
  message: string;
  blocking: boolean;
  count: number;
  rows: number[];
};

export type ValidationReport = {
  source: string;
  status: "APROVADO" | "APROVADO_COM_RESSALVAS" | "REPROVADO";
  summary: {
    issue_groups: number;
    blocking_issue_groups: number;
    by_severity: Record<string, number>;
  };
  metadata: { allocating_rows: number; expected_module: number };
  issues: ValidationIssue[];
};

export type EligibilityCriterion =
  | "PERFIL_EXATO"
  | "CLUSTER_PREFERENCIAL"
  | "CLUSTER_PURO";

export const CRITERION_LABELS: Record<EligibilityCriterion, string> = {
  PERFIL_EXATO: "Perfil da disciplina",
  CLUSTER_PREFERENCIAL: "Cluster com perfil preferencial",
  CLUSTER_PURO: "Cluster puro",
};

export type ExecutionProfile =
  | "PROVA_COMPLETA"
  | "COBERTURA_PROVADA"
  | "MARGEM_ACEITA"
  | "EXPLORACAO_RAPIDA";

export const PROFILE_LABELS: Record<ExecutionProfile, string> = {
  PROVA_COMPLETA: "Prova completa",
  COBERTURA_PROVADA: "Cobertura provada",
  MARGEM_ACEITA: "Margem aceita",
  EXPLORACAO_RAPIDA: "Exploração rápida",
};

export type UploadResult = {
  id: string;
  filename: string;
  size_bytes: number;
  module: number;
  criterion: EligibilityCriterion;
  profile: ExecutionProfile;
  margin_offers: number | null;
  created_at: string;
  validation: ValidationReport;
};

export type Job = {
  id: string;
  upload_id: string;
  filename: string;
  module: number;
  status: string;
  message: string;
  validation_status: string;
  require_optimal: boolean;
  time_limit_seconds: number | null;
  kind: "PRIMARY" | "SCENARIO";
  /** Lote a que a rodada pertence; nulo em execuções avulsas. */
  batch_id: string | null;
  criterion: EligibilityCriterion;
  profile: ExecutionProfile;
  margin_offers: number | null;
  scenario_id: string | null;
  is_official: boolean;
  round: string | null;
  exit_code: number | null;
  created_at: string;
  updated_at: string;
  history: Array<{ state: string; message: string; at_utc: string }>;
  terminal: boolean;
};

export type ScenarioChange = {
  id: string;
  change_type: "CAPACIDADE" | "AGENDA" | "COMPATIBILIDADE";
  entity_type: "teacher" | "offer";
  row_number: number;
  field_name: string;
  old_value: string | number | null;
  new_value: string | number;
  created_at: string;
};

export type ScenarioPolicy = {
  id: string;
  policy_type: "ALOCAR_CLUSTER" | "INTERNALIZACAO" | "PRIORIDADE" | "FIXAR";
  target_type: "GLOBAL" | "CLUSTER" | "COURSE" | "OFFER";
  target_value: string;
  configuration: Record<string, string | number | boolean>;
  created_at: string;
};

export type Scenario = {
  id: string;
  baseline_job_id: string;
  baseline_round: string | null;
  baseline_filename: string;
  module: number;
  criterion: EligibilityCriterion;
  profile: ExecutionProfile;
  name: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
  promoted_at: string | null;
  official_job_id: string | null;
  changes: ScenarioChange[];
  policies: ScenarioPolicy[];
  latest_job: Job | null;
};

export type ScenarioCatalog = {
  teachers: Array<{
    row_number: number;
    badge: string;
    name: string;
    status: string;
    job_function: string;
    teaching_capacity: number;
    /** Teto que a validação cobra. Nulo quando a coluna não existe na base. */
    contracted_capacity: number | null;
    manager: string;
    profile: string;
  }>;
  offers: Array<{
    row_number: number;
    course: string;
    course_code: string;
    course_name: string;
    discipline_code: string;
    discipline_name: string;
    day: string;
    time: string;
    order: string;
    cluster: string;
    profile: string;
    baseline_status: string;
    baseline_teacher_badge: string;
    baseline_teacher_name: string;
  }>;
  courses: Array<{ code: string; name: string }>;
  clusters: Array<{ name: string; total_offers: number; unassigned_offers: number }>;
};

export type ScenarioDifference = {
  source_row: number;
  discipline_code: string;
  discipline_name: string;
  before_teacher: string | null;
  after_teacher: string | null;
};

export type ScenarioComparison = {
  scenario: Scenario;
  baseline_job: Job;
  scenario_job: Job;
  kpis: {
    baseline_coverage_pct: number;
    scenario_coverage_pct: number;
    coverage_delta_pp: number;
    allocated_delta: number;
    unassigned_hours_delta: number;
    used_teachers_delta: number;
    internal_allocated_hours_delta: number;
    external_allocated_hours_delta: number;
    assignment_stability_pct: number;
    first_stage_hours_delta: number;
    second_stage_hours_delta: number;
  };
  differences: {
    recovered: ScenarioDifference[];
    lost: ScenarioDifference[];
    reassigned: ScenarioDifference[];
  };
  guardrails: {
    validation: string;
    solver: string;
    audit: string;
    baseline_criterion: EligibilityCriterion;
    scenario_criterion: EligibilityCriterion;
    same_criterion: boolean;
    baseline_profile: ExecutionProfile;
    scenario_profile: ExecutionProfile;
    promotable_profile: boolean;
    eligible_for_promotion: boolean;
  };
};

export type Summary = {
  status: string;
  solver_status: string;
  transmissions: number;
  allocated: number;
  unassigned: number;
  active_teachers: number;
  used_teachers: number;
  zero_active_teachers: number;
  wall_time_seconds: number;
  unassigned_reasons: Record<string, number>;
};

export type Allocation = {
  transmission_id: number;
  source_row: number;
  curriculum: string;
  discipline_code: string;
  discipline_name: string;
  status: string;
  unassigned_reason: string;
  allocation_reason: string;
  eligible_teacher_count: number;
  contract_model: string;
  teacher_badge: string | null;
  teacher_name: string | null;
};

export type AllocationPage = {
  items: Allocation[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
};

export type DashboardData = {
  job: Job;
  kpis: {
    coverage_pct: number;
    allocated: number;
    transmissions: number;
    unassigned: number;
    teacher_use_pct: number;
    active_teachers: number;
    used_teachers: number;
    zero_active_teachers: number;
    disciplines_by_order: { first: number; second: number; extended: number };
    first_stage_demand_hours: number;
    second_stage_demand_hours: number;
    first_stage_capacity_delta_hours: number;
    second_stage_capacity_delta_hours: number;
    active_teaching_capacity_hours: number;
  };
  unassigned_reasons: Array<{ reason: string; count: number }>;
  stage_hours: { first_stage?: number; second_stage?: number };
  charts: {
    by_day: Array<{ day: string; disciplines: number; teachers: number }>;
    demand_hours_by_cluster: Array<{ cluster: string; hours: number }>;
  };
  filters: {
    selected: Record<string, string[]>;
    options: {
      orders: string[];
      courses: Array<{ value: string; label: string }>;
      clusters: string[];
      days: string[];
      times: string[];
    };
  };
  teachers_by_job_function: Array<{
    job_function: string;
    regime: string;
    /** "cargo" agrupa, "regime" detalha, "total" fecha a tabela. */
    level: "cargo" | "regime" | "total";
    headcount: number;
    contracted_hours: number;
    allocatable_hours: number;
    /** Média das duas etapas, que é a base do percentual. */
    allocated_hours: number;
    first_stage_hours: number;
    second_stage_hours: number;
    /** Média das etapas. Nulo sem CH letiva alocável: o contrato Stricto. */
    utilization_pct: number | null;
  }>;
  guardrails: { validation: string; solver: string; audit: string };
  wall_time_seconds: number;
  metric_notes: { demand: string; capacity_delta: string };
  source_note: string;
};

export type DashboardFilters = {
  order: string[];
  course: string[];
  cluster: string[];
  day: string[];
  time: string[];
};

export type InsightBreakdown = {
  label: string;
  count: number;
  share_pct: number;
};

export type InsightsData = {
  job: Job;
  kpis: {
    coverage_pct: number;
    courses_below_90_pct: number;
    disciplines_uncovered: number;
    unassigned_demand_hours: number;
    rpa_allocated_hours: number;
    internal_idle_hours: number;
    top_20_teacher_share_pct: number;
    median_peak_utilization_pct: number;
    high_or_critical_risk_teachers: number;
    load_outliers: number;
    single_candidate_allocations: number;
    pareto_teacher_count_80: number;
    hours_per_transmission: number;
  };
  stage_load: {
    first_stage_allocations: number;
    second_stage_allocations: number;
    difference: number;
  };
  teacher_stats: {
    used_teachers: number;
    mean_allocations: number;
    median_allocations: number;
    pareto_count_80: number;
    top_20_count: number;
    top_20_share_pct: number;
  };
  teacher_distribution: Array<{
    teacher: string;
    role: string;
    allocations: number;
    share_pct: number;
    cumulative_pct: number;
    stage_1_utilization_pct: number;
    stage_2_utilization_pct: number;
  }>;
  risk_teachers: Array<{
    teacher: string;
    role: string;
    allocations: number;
    stage_1_utilization_pct: number;
    stage_2_utilization_pct: number;
    peak_utilization_pct: number;
    day_concentration_pct: number;
    score: number;
    risk_class: string;
    load_outlier: boolean;
  }>;
  breakdowns: {
    clusters: InsightBreakdown[];
    days: InsightBreakdown[];
    coordinators: InsightBreakdown[];
    contracts: InsightBreakdown[];
    unassigned_reasons: InsightBreakdown[];
  };
  automatic_insights: Array<{
    tone: "neutral" | "attention" | "critical" | "positive";
    title: string;
    text: string;
  }>;
  coverage: {
    courses: Array<{
      curso: string;
      nome_curso: string;
      total: number;
      allocated: number;
      unassigned: number;
      coverage_pct: number;
      demand_hours: number;
      single_candidate: number;
      gap_days: Array<{ day: string; count: number }>;
    }>;
    clusters: Array<{
      cluster: string;
      total: number;
      allocated: number;
      unassigned: number;
      coverage_pct: number;
      demand_hours: number;
      single_candidate: number;
      gap_days: Array<{ day: string; count: number }>;
    }>;
    discipline_gaps: Array<{
      curso: string;
      nome_curso: string;
      cod_disciplina: string;
      nome_disciplina: string;
      total: number;
      allocated: number;
      unassigned: number;
      coverage_pct: number;
      demand_hours: number;
      single_candidate: number;
    }>;
    gap_reasons: InsightBreakdown[];
  };
  opportunities: Array<{
    priority: string;
    /** Urgencia derivada dos numeros da rodada; define a cor do cartao. */
    severity: "critica" | "alta" | "media" | "monitorar" | "resolvido";
    kind: string;
    title: string;
    metric: string;
    impact: string;
    action: string;
  }>;
  diagnostics: {
    most_congested_unassigned_slots: Array<{
      slot: string;
      count: number;
      affected_courses: number;
      top_course: string;
      top_course_count: number;
      top_profile: string;
    }>;
    top_gap_profile: string | null;
  };
  methodology: string[];
  limitations: string[];
  source_note: string;
};

/** Resultado da inspeção prévia: o que cada planilha enviada contém. */
export type BatchInspection = {
  files: Array<{
    filename: string;
    error?: string;
    modules?: Array<{ module: number; rows: number; supported: boolean }>;
    rows_without_module?: number;
  }>;
  available_modules: number[];
};

export type BatchModule = {
  module: number;
  upload_id: string | null;
  filename: string;
  validation_status: string;
  runnable: boolean;
  reason: string;
  /** Os mesmos números do passo de validação da rodada única. */
  validation: {
    allocating_rows: number;
    issue_groups: number;
    blocking_issue_groups: number;
    by_severity: Record<string, number>;
    issues: Array<{
      severity: string;
      code: string;
      sheet: string;
      column: string;
      message: string;
      rows: number[];
      count: number;
    }>;
  } | null;
  job: Job | null;
  kpis: {
    transmissions: number;
    allocated: number;
    unassigned: number;
    used_teachers: number;
    solver_status: string | null;
    coverage_pct: number;
  } | null;
};

export type ModuleBatch = {
  id: string;
  name: string;
  criterion: EligibilityCriterion;
  profile: ExecutionProfile;
  margin_offers: number | null;
  require_optimal: boolean;
  time_limit_seconds: number | null;
  created_at: string;
  status: "AGUARDANDO" | "EXECUTANDO" | "CONCLUIDO" | "PARCIAL";
  modules: BatchModule[];
  totals: {
    modules: number;
    runnable: number;
    queued_or_running: number;
    concluded: number;
    offers: number;
    allocated: number;
    coverage_pct: number;
  };
};

// ---------------------------------------------------------------------------
// Estudo em lote: a mesma pergunta aplicada a vários módulos do ano.
// ---------------------------------------------------------------------------

/** Lote com rodada concluída, oferecido como base de um estudo. */
export type StudyBaseline = {
  id: string;
  name: string;
  criterion: EligibilityCriterion;
  profile: ExecutionProfile;
  created_at: string;
  modules: Array<{ module: number; baseline_job_id: string; round_name: string | null }>;
};

/**
 * Premissa do estudo. O alvo é a chave de negócio — a chapa do docente —, e
 * não a linha da planilha: a linha muda quando a base anual é fatiada.
 */
export type StudyPremise = {
  id: string;
  premise_type: "CAPACIDADE" | "COMPATIBILIDADE" | "AGENDA";
  target_type: "TEACHER_BADGE" | "COURSE" | "DISCIPLINE";
  target_value: string;
  target_label: string;
  field_name: string;
  operation: "SET" | "ADJUST";
  value: string | number;
  created_at: string;
};

export type StudyModuleKpis = {
  transmissions: number;
  allocated: number;
  unassigned: number;
  used_teachers: number;
  solver_status: string | null;
  coverage_pct: number;
};

export type StudyModule = {
  module: number;
  baseline_job_id: string;
  scenario_id: string | null;
  scenario: Scenario | null;
  job: Job | null;
  change_count: number;
  /** A simulação existente ficou para trás das premissas atuais. */
  stale: boolean;
  baseline_kpis: StudyModuleKpis | null;
  kpis: StudyModuleKpis | null;
  promoted: boolean;
};

export type Study = {
  id: string;
  batch_id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  status: "AGUARDANDO" | "EXECUTANDO" | "CONCLUIDO" | "PARCIAL";
  premises: StudyPremise[];
  modules: StudyModule[];
  totals: {
    modules: number;
    runnable: number;
    queued_or_running: number;
    concluded: number;
    compared: number;
    baseline_offers: number;
    baseline_allocated: number;
    allocated: number;
    allocated_delta: number;
    baseline_coverage_pct: number;
    coverage_pct: number;
    coverage_delta_pp: number;
    unassigned_delta: number;
    used_teachers_delta: number;
  };
};

/** O que cada premissa produziu dentro de um módulo, com o motivo da recusa. */
export type StudyModuleProjection = {
  module: number;
  applied_count: number;
  results: Array<{ premise_id: string; applied: number; reason: string }>;
  locked: boolean;
  reason: string;
};

export type StudyPremiseResult = {
  study: Study;
  projection: StudyModuleProjection[];
};

/**
 * Alvo de oferta agregado de todos os módulos do estudo.
 *
 * `modules` diz onde o alvo existe e quantas lacunas ele deixou na rodada-base
 * de cada módulo — é o número que responde "qual curso vive com disciplina sem
 * docente" sem precisar sair da tela.
 */
export type StudyOfferTarget = {
  code: string;
  name: string;
  course_code: string;
  course_name: string;
  modules: Array<{ module: number; offers: number; unassigned: number }>;
  days: string[];
  times: string[];
  orders: string[];
  total_offers: number;
  total_unassigned: number;
};

export type StudyCatalog = {
  modules: number[];
  teachers: Array<{
    badge: string;
    name: string;
    status: string;
    job_function: string;
    teaching_capacity: number;
    contracted_capacity: number | null;
    manager: string;
    profile: string;
  }>;
  courses: StudyOfferTarget[];
  disciplines: StudyOfferTarget[];
  /** Dias, horários e ordens efetivamente praticados no ano. */
  practiced: {
    days: Array<{ value: string; offers: number }>;
    times: Array<{ value: string; offers: number }>;
    orders: Array<{ value: string; offers: number }>;
  };
};

export type StudyComparison = {
  study: Study;
  modules: Array<{
    module: number;
    scenario_id: string | null;
    comparison: ScenarioComparison | null;
    reason: string;
  }>;
};

/** Retorno da alteração em lote: o que entrou e o que foi ignorado, com motivo. */
export type BatchChangeResult = {
  applied: ScenarioChange[];
  skipped: Array<{ row_number: number; reason: string }>;
  applied_count: number;
  skipped_count: number;
};
