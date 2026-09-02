import { useEffect, useMemo, useState } from "react";
import MultiSelect from "./MultiSelect";
import type { ScenarioCatalog } from "../types";

type Teacher = ScenarioCatalog["teachers"][number];
type Offer = ScenarioCatalog["offers"][number];
type Entity = Teacher | Offer;

function isTeacher(item: Entity): item is Teacher {
  return "name" in item;
}

/** Busca sem acento e sem caixa, como o resto da tela já faz. */
function fold(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
}

/** Valores distintos de um campo, para montar as listas de filtro. */
function distinct(
  items: Entity[],
  pick: (item: Entity) => string,
  numeric = false,
): string[] {
  const seen = new Set<string>();
  items.forEach((item) => {
    const value = pick(item).trim();
    if (value) seen.add(value);
  });
  return [...seen].sort((a, b) =>
    numeric ? Number(a) - Number(b) : a.localeCompare(b, "pt-BR"),
  );
}

type Facet = {
  key: string;
  label: string;
  values: string[];
  pick: (item: Entity) => string;
  /** Rotulo exibido para o valor bruto, quando ele precisa de unidade. */
  format?: (value: string) => string;
};

export type EntityPickerProps = {
  entityType: "teacher" | "offer";
  teachers: Teacher[];
  offers: Offer[];
  selected: number[];
  onSelectedChange: (rows: number[]) => void;
  disabled?: boolean;
};

/**
 * Seleção de várias entidades por filtro.
 *
 * O problema que resolve: aplicar a mesma premissa a dezenas de docentes exigia
 * repetir o formulário um a um. Aqui o operador restringe por função, status ou
 * faixa de CH, confere quantos sobraram e marca todos de uma vez.
 */
export default function ScenarioEntityPicker({
  entityType,
  teachers,
  offers,
  selected,
  onSelectedChange,
  disabled = false,
}: EntityPickerProps) {
  const [facetValues, setFacetValues] = useState<Record<string, string[]>>({});

  const entities: Entity[] = entityType === "teacher" ? teachers : offers;

  // Definicao estavel das facetas: chave, rotulo e como extrair o valor. Os
  // valores disponiveis nao entram aqui porque dependem do que as outras
  // facetas ja restringiram.
  const facetDefs = useMemo(() => {
    const build = (
      key: string,
      label: string,
      pick: (item: Entity) => string,
      extras: { numeric?: boolean; format?: (value: string) => string } = {},
    ) => ({ key, label, pick, numeric: extras.numeric ?? false, format: extras.format });
    const candidates = entityType === "teacher"
      ? [
          // A CH letiva tem poucas faixas distintas na base; escolher entre
          // elas e mais direto do que preencher um intervalo de/ate, e deixa
          // todos os filtros com o mesmo formato.
          build(
            "teaching_capacity",
            "CH letiva",
            (item: Entity) => String((item as Teacher).teaching_capacity ?? ""),
            { numeric: true, format: (value: string) => `${value}h` },
          ),
          build("job_function", "Cargo", (item: Entity) => (item as Teacher).job_function),
          build("status", "Status", (item: Entity) => (item as Teacher).status),
          build("manager", "Gestor", (item: Entity) => (item as Teacher).manager),
        ]
      : [
          build("cluster", "Cluster", (item: Entity) => (item as Offer).cluster),
          build("course", "Curso", (item: Entity) => (item as Offer).course),
          build("day", "Dia", (item: Entity) => (item as Offer).day),
          build("order", "Ordem", (item: Entity) => (item as Offer).order),
          build("baseline_status", "Situação na base", (item: Entity) => (item as Offer).baseline_status),
        ];
    // Um filtro com um valor so na base inteira nao ajuda a restringir nada.
    // A conta usa a base completa de proposito: assim a lista de filtros nao
    // aparece e some conforme o operador vai escolhendo.
    return candidates.filter((def) => distinct(entities, def.pick, def.numeric).length > 1);
  }, [entities, entityType]);

  const passesFacet = (item: Entity, def: { key: string; pick: (item: Entity) => string }) => {
    const chosen = facetValues[def.key];
    // Dentro do mesmo filtro as escolhas sao OU; entre filtros, E.
    return !chosen?.length || chosen.includes(def.pick(item).trim());
  };

  // Cada faceta oferece apenas o que ainda existe depois das OUTRAS facetas.
  // Escolher CH letiva 0h deixa em Cargo so os cargos que tem alguem com 0h.
  // A propria faceta fica de fora do calculo para nao anular as suas opcoes
  // irmas assim que a primeira e marcada.
  const facets: Facet[] = useMemo(() => {
    return facetDefs.map((def) => {
      const disponiveis = entities.filter((item) =>
        facetDefs.every((outra) => outra.key === def.key || passesFacet(item, outra)),
      );
      const contagem = new Map<string, number>();
      for (const item of disponiveis) {
        const valor = def.pick(item).trim();
        if (valor) contagem.set(valor, (contagem.get(valor) ?? 0) + 1);
      }
      const values = [...contagem.keys()].sort((a, b) =>
        def.numeric ? Number(a) - Number(b) : a.localeCompare(b, "pt-BR"),
      );
      return {
        key: def.key,
        label: def.label,
        pick: def.pick,
        values,
        format: (valor: string) => {
          const rotulo = def.format ? def.format(valor) : valor;
          return `${rotulo} · ${contagem.get(valor) ?? 0}`;
        },
      };
    });
  }, [entities, facetDefs, facetValues]);

  // Uma escolha que deixou de existir apos outro filtro travaria o resultado em
  // zero sem explicar por que; ela sai da selecao em vez de virar beco sem saida.
  useEffect(() => {
    let mudou = false;
    const ajustado: Record<string, string[]> = {};
    for (const facet of facets) {
      const atual = facetValues[facet.key] ?? [];
      const validos = atual.filter((valor) => facet.values.includes(valor));
      if (validos.length !== atual.length) mudou = true;
      if (validos.length) ajustado[facet.key] = validos;
    }
    if (mudou) setFacetValues(ajustado);
  }, [facets, facetValues]);


  const filtered = useMemo(() => {
    return entities.filter((item) => {
      for (const facet of facets) {
        const chosen = facetValues[facet.key];
        // Dentro do mesmo filtro as escolhas são OU; entre filtros, E.
        if (chosen?.length && !chosen.includes(facet.pick(item).trim())) return false;
      }
      return true;
    });
  }, [entities, entityType, facets, facetValues]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const filteredRows = useMemo(() => filtered.map((item) => item.row_number), [filtered]);
  const allFilteredSelected =
    filteredRows.length > 0 && filteredRows.every((row) => selectedSet.has(row));

  const toggleFacetValue = (key: string, value: string) => {
    setFacetValues((previous) => {
      const current = previous[key] ?? [];
      const next = current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value];
      return { ...previous, [key]: next };
    });
  };

  const toggleRow = (row: number) => {
    onSelectedChange(
      selectedSet.has(row)
        ? selected.filter((item) => item !== row)
        : [...selected, row],
    );
  };

  const selectAllFiltered = () => {
    if (allFilteredSelected) {
      onSelectedChange(selected.filter((row) => !filteredRows.includes(row)));
      return;
    }
    onSelectedChange([...new Set([...selected, ...filteredRows])]);
  };

  const clearFilters = () => {
    setFacetValues({});
  };

  const activeFilters = Object.values(facetValues).some((values) => values.length > 0);

  return (
    <div className="entity-picker">
      <div className="entity-picker-filters">
        {/* Todo filtro usa o mesmo controle: lista suspensa com busca e
            selecao multipla. Antes so o Gestor era suspenso, por causa de um
            limiar de quantidade, e os demais ficavam como parede de chips. */}
        {facets.map((facet) => (
          <div key={facet.key} className="entity-picker-facet entity-picker-facet-menu">
            <MultiSelect
              label={facet.label}
              values={facetValues[facet.key] ?? []}
              options={facet.values.map((value) => ({
                value,
                label: facet.format ? facet.format(value) : value,
              }))}
              onChange={(values) => setFacetValues((current) => ({ ...current, [facet.key]: values }))}
              disabled={disabled}
              emptyLabel="Todos"
              emptyHint="Sem restrição"
              clearLabel="Limpar filtro"
            />
          </div>
        ))}
      </div>

      <div className="entity-picker-actions">
        <button type="button" className="button ghost" disabled={disabled || !filteredRows.length} onClick={selectAllFiltered}>
          {allFilteredSelected
            ? `Desmarcar os ${filteredRows.length} filtrados`
            : `Selecionar os ${filteredRows.length} filtrados`}
        </button>
        <button type="button" className="button ghost" disabled={disabled || !selected.length} onClick={() => onSelectedChange([])}>
          Limpar seleção
        </button>
        {activeFilters && (
          <button type="button" className="button ghost" disabled={disabled} onClick={clearFilters}>
            Limpar filtros
          </button>
        )}
        <span className="entity-picker-count">
          <strong>{selected.length}</strong> selecionado(s) de {filtered.length} exibido(s)
          {entities.length !== filtered.length && ` · ${entities.length} no total`}
        </span>
      </div>

      <div className="entity-picker-choice">
        <MultiSelect
          label={entityType === "teacher" ? "Docentes" : "Ofertas"}
          values={selected.map(String)}
          options={filtered.map((item) => ({
            value: String(item.row_number),
            label: isTeacher(item)
              ? `${item.name} · ${item.badge} · ${item.job_function} · CH ${item.teaching_capacity}h${item.contracted_capacity ? ` de ${item.contracted_capacity}h` : ""} · ${item.status}`
              : `${item.discipline_name} · ${item.course} · ${item.order} · ${item.day} ${item.time} · ${item.baseline_status === "ALOCADA" ? item.baseline_teacher_name : "sem docente"}`,
          }))}
          onChange={(values) => onSelectedChange(values.map(Number))}
          disabled={disabled}
          emptyLabel={filtered.length ? `Selecione entre ${filtered.length} registro(s)` : "Nenhum registro atende aos filtros"}
          emptyHint="Nenhum"
          clearLabel="Limpar seleção"
        />
      </div>
    </div>
  );
}
