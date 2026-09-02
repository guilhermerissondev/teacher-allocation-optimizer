import { useEffect, useMemo, useState } from "react";
import MultiSelect from "./MultiSelect";

/**
 * Alvo de uma premissa de estudo, já reduzido a uma chave de negócio.
 *
 * O seletor do cenário avulso trabalha com o número da linha da planilha, que
 * só existe dentro de um módulo. Aqui o alvo é a chapa, o código do curso ou o
 * da disciplina, e o mesmo alvo vale para o ano inteiro — por isso a estrutura
 * é própria, e não uma adaptação daquele componente.
 */
export type StudyTarget = {
  key: string;
  label: string;
  detail: string;
  /** Valor de cada faceta. É lista porque um curso existe em vários módulos. */
  facets: Record<string, string[]>;
};

export type StudyFacetDef = { key: string; label: string; numeric?: boolean };

type Props = {
  label: string;
  targets: StudyTarget[];
  facetDefs: StudyFacetDef[];
  selected: string[];
  onSelectedChange: (keys: string[]) => void;
  disabled?: boolean;
};

/**
 * Seleção de vários alvos por filtro, com a mesma mecânica da tela de cenário
 * avulso: dentro de um filtro as escolhas são OU, entre filtros são E, e cada
 * filtro oferece apenas o que ainda existe depois dos outros.
 */
export default function StudyEntityPicker({
  label,
  targets,
  facetDefs,
  selected,
  onSelectedChange,
  disabled = false,
}: Props) {
  const [facetValues, setFacetValues] = useState<Record<string, string[]>>({});

  // Um filtro com um valor só na base inteira não restringe nada e apenas
  // ocupa espaço; a conta usa a base completa para que a lista de filtros não
  // apareça e suma conforme o operador escolhe.
  const usefulFacets = useMemo(
    () => facetDefs.filter((def) => {
      const values = new Set<string>();
      targets.forEach((item) => (item.facets[def.key] ?? []).forEach((value) => values.add(value)));
      return values.size > 1;
    }),
    [facetDefs, targets],
  );

  const passes = (item: StudyTarget, key: string) => {
    const chosen = facetValues[key];
    if (!chosen?.length) return true;
    return (item.facets[key] ?? []).some((value) => chosen.includes(value));
  };

  const facets = useMemo(() => usefulFacets.map((def) => {
    // A própria faceta fica de fora do cálculo das suas opções, senão a
    // primeira escolha anularia as opções irmãs.
    const available = targets.filter((item) =>
      usefulFacets.every((other) => other.key === def.key || passes(item, other.key)));
    const counts = new Map<string, number>();
    available.forEach((item) => (item.facets[def.key] ?? []).forEach((value) => {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }));
    const values = [...counts.keys()].sort((a, b) =>
      def.numeric ? Number(a) - Number(b) : a.localeCompare(b, "pt-BR"));
    return { ...def, values, counts };
  }), [targets, usefulFacets, facetValues]);

  // Uma escolha que deixou de existir depois de outro filtro travaria o
  // resultado em zero sem explicar por quê; ela sai da seleção.
  useEffect(() => {
    let changed = false;
    const adjusted: Record<string, string[]> = {};
    for (const facet of facets) {
      const current = facetValues[facet.key] ?? [];
      const valid = current.filter((value) => facet.values.includes(value));
      if (valid.length !== current.length) changed = true;
      if (valid.length) adjusted[facet.key] = valid;
    }
    if (changed) setFacetValues(adjusted);
  }, [facets, facetValues]);

  const filtered = useMemo(
    () => targets.filter((item) => facets.every((facet) => passes(item, facet.key))),
    [targets, facets, facetValues],
  );

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const filteredKeys = useMemo(() => filtered.map((item) => item.key), [filtered]);
  const allSelected = filteredKeys.length > 0 && filteredKeys.every((key) => selectedSet.has(key));
  const activeFilters = Object.values(facetValues).some((values) => values.length > 0);

  return <div className="entity-picker">
    {facets.length > 0 && <div className="entity-picker-filters">
      {facets.map((facet) => (
        <div key={facet.key} className="entity-picker-facet entity-picker-facet-menu">
          <MultiSelect
            label={facet.label}
            values={facetValues[facet.key] ?? []}
            options={facet.values.map((value) => ({
              value,
              label: `${value} · ${facet.counts.get(value) ?? 0}`,
            }))}
            onChange={(values) => setFacetValues((current) => ({ ...current, [facet.key]: values }))}
            disabled={disabled}
            emptyLabel="Todos"
            emptyHint="Sem restrição"
            clearLabel="Limpar filtro"
          />
        </div>
      ))}
    </div>}

    <div className="entity-picker-actions">
      <button
        type="button"
        className="button ghost"
        disabled={disabled || !filteredKeys.length}
        onClick={() => onSelectedChange(allSelected
          ? selected.filter((key) => !filteredKeys.includes(key))
          : [...new Set([...selected, ...filteredKeys])])}
      >
        {allSelected
          ? `Desmarcar os ${filteredKeys.length} filtrados`
          : `Selecionar os ${filteredKeys.length} filtrados`}
      </button>
      <button type="button" className="button ghost" disabled={disabled || !selected.length} onClick={() => onSelectedChange([])}>
        Limpar seleção
      </button>
      {activeFilters && <button type="button" className="button ghost" disabled={disabled} onClick={() => setFacetValues({})}>
        Limpar filtros
      </button>}
      <span className="entity-picker-count">
        <strong>{selected.length}</strong> selecionado(s) de {filtered.length} exibido(s)
        {targets.length !== filtered.length && ` · ${targets.length} no total`}
      </span>
    </div>

    <div className="entity-picker-choice">
      <MultiSelect
        label={label}
        values={selected}
        options={filtered.map((item) => ({
          value: item.key,
          label: item.detail ? `${item.label} · ${item.detail}` : item.label,
        }))}
        onChange={onSelectedChange}
        disabled={disabled}
        emptyLabel={filtered.length ? `Selecione entre ${filtered.length} registro(s)` : "Nenhum registro atende aos filtros"}
        emptyHint="Nenhum"
        clearLabel="Limpar seleção"
      />
    </div>
  </div>;
}
