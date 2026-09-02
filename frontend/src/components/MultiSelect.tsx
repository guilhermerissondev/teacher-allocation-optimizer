import { useEffect, useRef, useState } from "react";

export type MultiSelectOption = { value: string; label: string };

type Props = {
  label: string;
  values: string[];
  options: MultiSelectOption[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
  /** Texto do resumo quando nada esta selecionado. */
  emptyLabel?: string;
  /** Legenda do contador quando nada esta selecionado. */
  emptyHint?: string;
  /** Rotulo do botao que limpa a selecao. */
  clearLabel?: string;
};

/**
 * Selecao multipla em janela suspensa, com busca a partir de oito opcoes.
 *
 * Serve a qualquer lista longa em que a escolha e naturalmente um conjunto:
 * os filtros do dashboard e os alvos de politica dos cenarios (cursos,
 * clusters, ofertas), onde antes era preciso repetir o formulario inteiro uma
 * vez por item.
 */
export default function MultiSelect({
  label,
  values,
  options,
  onChange,
  disabled,
  emptyLabel = "Todos",
  emptyHint = "Sem restrição",
  clearLabel = "Todos, sem restrição",
}: Props) {
  const [search, setSearch] = useState("");
  const menuRef = useRef<HTMLDetailsElement>(null);

  // O <details> nativo nao fecha com Esc nem ao clicar fora, mas o campo se
  // apresenta como uma lista suspensa e e isso que o teclado e o mouse esperam
  // dele. Sem os dois, o menu aberto cobre o formulario ate um novo clique no
  // proprio resumo.
  useEffect(() => {
    const fechar = () => {
      const menu = menuRef.current;
      if (menu?.open) menu.open = false;
    };
    const aoTeclar = (evento: KeyboardEvent) => {
      if (evento.key !== "Escape" || !menuRef.current?.open) return;
      fechar();
      // Devolve o foco ao campo, senao o teclado fica sem ponto de partida.
      menuRef.current?.querySelector("summary")?.focus();
    };
    const aoClicar = (evento: MouseEvent) => {
      const menu = menuRef.current;
      if (menu?.open && !menu.contains(evento.target as Node)) fechar();
    };
    document.addEventListener("keydown", aoTeclar);
    document.addEventListener("pointerdown", aoClicar);
    return () => {
      document.removeEventListener("keydown", aoTeclar);
      document.removeEventListener("pointerdown", aoClicar);
    };
  }, []);
  const normalize = (text: string) =>
    text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");
  const term = normalize(search).trim();
  const visibleOptions = term
    ? options.filter((option) => normalize(option.label).includes(term))
    : options;
  const selectedLabel = values.length === 1
    ? options.find((option) => option.value === values[0])?.label ?? values[0]
    : values.length > 1 ? `${values.length} selecionados` : emptyLabel;
  const toggle = (value: string) => {
    onChange(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  };
  // Marcar tudo respeita o filtro de busca: e o atalho esperado depois de
  // digitar, e mantem fora do conjunto o que a busca escondeu.
  const selectVisible = () => {
    const merged = new Set(values);
    for (const option of visibleOptions) merged.add(option.value);
    onChange([...merged]);
  };

  return (
    <fieldset className="multi-filter" disabled={disabled}>
      <legend>{label}</legend>
      <details ref={menuRef}>
        <summary>
          <span>{selectedLabel}</span>
          <small>{values.length ? `${values.length}/${options.length}` : emptyHint}</small>
        </summary>
        <div className="multi-filter-menu" role="group" aria-label={`Opções de ${label}`}>
          {options.length > 7 && (
            <label className="multi-filter-search">
              <span className="sr-only">Buscar em {label}</span>
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={`Buscar ${label.toLocaleLowerCase("pt-BR")}`}
              />
            </label>
          )}
          <div className="multi-filter-bulk">
            <button
              type="button"
              className="multi-filter-clear"
              disabled={!visibleOptions.length}
              onClick={selectVisible}
            >
              {term ? `Marcar ${visibleOptions.length} encontrado(s)` : "Marcar todos"}
            </button>
            <button
              type="button"
              className="multi-filter-clear"
              disabled={!values.length}
              onClick={() => onChange([])}
            >
              {clearLabel}
            </button>
          </div>
          <div className="multi-filter-options">
            {visibleOptions.length === 0 && <p className="multi-filter-empty">Nenhuma opção encontrada.</p>}
            {visibleOptions.map((option) => (
              <label key={option.value}>
                <input
                  type="checkbox"
                  checked={values.includes(option.value)}
                  onChange={() => toggle(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </div>
      </details>
    </fieldset>
  );
}
