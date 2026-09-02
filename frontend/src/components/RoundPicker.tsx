import { useEffect, useMemo, useState } from "react";
import { listModuleBatches } from "../api";
import {
  criterionLabel,
  formatJobDate,
  jobContextLabel,
  profileLabel,
  formatRoundOptionLabel,
} from "../jobPresentation";
import type { Job, ModuleBatch } from "../types";

type Props = {
  label: string;
  jobs: Job[];
  value: string;
  onChange: (jobId: string) => void;
  emptyLabel?: string;
  disabled?: boolean;
  /** Primeira opcao quando nada esta escolhido ainda. */
  placeholder?: string;
  /** Texto extra por opcao, para o que muda entre rodadas do mesmo lote. */
  optionSuffix?: (job: Job) => string;
  /** Descrição acessível quando o rótulo visível não basta. */
  ariaLabel?: string;
};

const AVULSAS = "__avulsas__";

/**
 * Seletor de rodada usado por todas as abas.
 *
 * O rótulo da opção carrega só o que distingue uma rodada da outra — módulo e
 * número da rodada — porque um lote produz várias rodadas idênticas em tudo
 * mais. O restante do contexto (critério, perfil, arquivo) fica na legenda
 * abaixo do campo, onde cabe por inteiro em vez de ser cortado pelo select.
 */
export default function RoundPicker({
  label, jobs, value, onChange, emptyLabel, ariaLabel, disabled, placeholder, optionSuffix,
}: Props) {
  const [batches, setBatches] = useState<ModuleBatch[]>([]);

  useEffect(() => {
    let active = true;
    // A falha aqui é tolerável: sem os nomes dos lotes o seletor ainda agrupa
    // as rodadas pelo identificador, apenas com um rótulo menos amigável.
    void listModuleBatches()
      .then((items) => { if (active) setBatches(items); })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  const batchNames = useMemo(
    () => new Map(batches.map((item) => [item.id, item])),
    [batches],
  );

  // Um grupo por lote, na ordem em que as rodadas chegam (mais recentes
  // primeiro), e um grupo final para as rodadas avulsas.
  const groups = useMemo(() => {
    const buckets = new Map<string, Job[]>();
    for (const job of jobs) {
      const key = job.batch_id ?? AVULSAS;
      const bucket = buckets.get(key);
      if (bucket) bucket.push(job);
      else buckets.set(key, [job]);
    }
    const avulsas = buckets.get(AVULSAS);
    buckets.delete(AVULSAS);
    const ordered = [...buckets.entries()];
    if (avulsas) ordered.push([AVULSAS, avulsas]);
    return ordered;
  }, [jobs]);

  const groupLabel = (key: string, members: Job[]) => {
    if (key === AVULSAS) return "Rodadas avulsas";
    const batch = batchNames.get(key);
    const when = formatJobDate(batch?.created_at ?? members[0].created_at);
    return `Lote · ${batch?.name || "Sem nome"} · ${when}`;
  };

  const selectedJob = jobs.find((item) => item.id === value) ?? null;

  return (
    <div className="round-picker">
      <label className="compact-field">
        <span>{label}</span>
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          aria-label={ariaLabel}
        >
          {jobs.length === 0 && <option value="">{emptyLabel ?? "Nenhuma rodada concluída"}</option>}
          {jobs.length > 0 && placeholder && <option value="">{placeholder}</option>}
          {groups.map(([key, members]) => (
            <optgroup key={key} label={groupLabel(key, members)}>
              {members.map((job) => (
                <option key={job.id} value={job.id}>
                  {formatRoundOptionLabel(job)}{optionSuffix ? ` · ${optionSuffix(job)}` : ""}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
      {selectedJob && (
        <p className="round-picker-context">
          <span className="round-picker-tag">{jobContextLabel(selectedJob)}</span>
          <span>{criterionLabel(selectedJob)}</span>
          <span aria-hidden="true">·</span>
          <span>{profileLabel(selectedJob)}</span>
          <span aria-hidden="true">·</span>
          <span className="round-picker-file" title={selectedJob.filename}>{selectedJob.filename}</span>
        </p>
      )}
    </div>
  );
}
