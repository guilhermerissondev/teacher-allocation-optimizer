import { useCallback, useEffect, useState } from "react";
import DashboardPage from "./pages/DashboardPage";
import ProcessPage from "./pages/ProcessPage";
import ScenariosPage from "./pages/ScenariosPage";
import InsightsPage from "./pages/InsightsPage";
import ExportPage from "./pages/ExportPage";
import OptimalLogo from "./components/OptimalLogo";
import ErrorBoundary from "./components/ErrorBoundary";
import { BUILD_STAMP } from "./types";

type Route = "processamento" | "dashboard" | "insights" | "cenarios" | "exportacao";
type ThemeChoice = "light" | "dark" | "system";

const routeTitles: Record<Route, string> = {
  processamento: "Processamento",
  dashboard: "Dashboard",
  insights: "Insights",
  cenarios: "Cenários",
  exportacao: "Exportação",
};

const routes: { id: Route; number: string; label: string }[] = [
  { id: "processamento", number: "01", label: "Processamento" },
  { id: "dashboard", number: "02", label: "Dashboard" },
  { id: "insights", number: "03", label: "Insights" },
  { id: "cenarios", number: "04", label: "Cenários" },
  { id: "exportacao", number: "05", label: "Exportação" },
];

const themeChoices: { id: ThemeChoice; label: string; title: string }[] = [
  { id: "light", label: "Claro", title: "Sempre usar o tema claro" },
  { id: "dark", label: "Escuro", title: "Sempre usar o tema escuro" },
  { id: "system", label: "Auto", title: "Seguir a preferência do sistema" },
];

const THEME_KEY = "optimal-theme";

function currentRoute(): Route {
  const route = window.location.hash.replace("#/", "") as Route;
  return routes.some((item) => item.id === route) ? route : "processamento";
}

function storedTheme(): ThemeChoice {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    if (value === "light" || value === "dark" || value === "system") return value;
  } catch {
    // Navegador sem armazenamento disponível: a preferência do sistema basta.
  }
  return "system";
}

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute);
  const [theme, setTheme] = useState<ThemeChoice>(storedTheme);

  useEffect(() => {
    const onHashChange = () => {
      setRoute(currentRoute());
      window.requestAnimationFrame(() => {
        document.getElementById("main-content")?.focus({ preventScroll: true });
      });
    };
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) window.location.hash = "#/processamento";
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    document.title = `${routeTitles[route]} · Alocação Docente`;
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [route]);

  // "system" não carimba atributo: nesse estado só prefers-color-scheme decide.
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      // Preferência não persistida; a sessão atual continua correta.
    }
  }, [theme]);

  const chooseTheme = useCallback((choice: ThemeChoice) => setTheme(choice), []);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Ir para o conteúdo principal</a>

      <header className="topbar">
        <OptimalLogo />
        <div className="brand-copy">
          <strong>Alocação Docente</strong>
          <span>Inteligência para o planejamento acadêmico</span>
        </div>

        <nav className="main-nav" aria-label="Módulos da aplicação">
          {routes.map((item) => (
            <a
              key={item.id}
              className={route === item.id ? "active" : ""}
              aria-current={route === item.id ? "page" : undefined}
              href={`#/${item.id}`}
            >
              <span className="nav-number">{item.number}</span>
              {item.label}
            </a>
          ))}
        </nav>

        <div className="header-meta">
          <div className="theme-switch" role="group" aria-label="Tema da interface">
            {themeChoices.map((choice) => (
              <button
                key={choice.id}
                type="button"
                title={choice.title}
                aria-pressed={theme === choice.id}
                onClick={() => chooseTheme(choice.id)}
              >
                {choice.label}
              </button>
            ))}
          </div>
          <div className="environment-badge" title={`Build ${BUILD_STAMP} · se este carimbo não muda após uma nova versão, a página veio do cache do navegador`}>
            VERSÃO 2.0<small>build {BUILD_STAMP}</small>
          </div>
          <div className="developer-credit" aria-label="Créditos do autor">
            <span>Desenvolvido por</span>
            <strong>Guilherme Henrique Risson Silva</strong>
          </div>
        </div>
      </header>

      <main id="main-content" tabIndex={-1}>
        {/* A chave por rota remonta o quadro a cada troca de aba, que e o
            que dispara a transicao de entrada declarada no CSS. */}
        <div className="route-frame" key={route}>
          {/* A barreira fica por rota: uma falha em uma aba não pode levar a
              casca da aplicação junto, deixando o operador sem navegação. */}
          <ErrorBoundary area={routeTitles[route]}>
            {route === "processamento" && <ProcessPage />}
            {route === "dashboard" && <DashboardPage />}
            {route === "insights" && <InsightsPage />}
            {route === "cenarios" && <ScenariosPage />}
            {route === "exportacao" && <ExportPage />}
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
