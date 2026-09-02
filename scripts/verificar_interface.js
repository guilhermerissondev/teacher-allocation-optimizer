/**
 * Varredura da interface em um navegador real.
 *
 * O pacote não tinha nenhuma verificação automatizada do frontend: o TypeScript
 * garante os tipos, e a auditoria de contraste garante a legibilidade, mas nada
 * garantia que a tela *desenha*. Uma resposta da API sem um campo que o tipo
 * prometia derrubava a página inteira, deixando só o fundo — e isso passava por
 * toda a suíte sem um arranhão.
 *
 * Este script percorre as cinco abas e o fluxo de lote de ponta a ponta, nos
 * dois temas, e reprova em qualquer exceção de render.
 *
 * É OPCIONAL e não faz parte de `testar.ps1`: exige Node.js, o Chrome instalado
 * e a aplicação já em execução. O portão canônico do release continua sendo
 * apenas Python.
 *
 *   node scripts/verificar_interface.js --url http://127.0.0.1:8000
 *
 * O Playwright é procurado nos locais usuais; para apontar outro, defina
 * PLAYWRIGHT_CORE com o caminho do pacote `playwright-core`.
 */

const fs = require("fs");
const path = require("path");

const RAIZ = path.resolve(__dirname, "..");

function carregarPlaywright() {
  const candidatos = [
    process.env.PLAYWRIGHT_CORE,
    path.join(RAIZ, "frontend", "node_modules", "playwright-core"),
    path.join(RAIZ, "frontend", "node_modules", "playwright"),
    path.join(
      process.env.LOCALAPPDATA || "",
      "ms-playwright-go", "1.57.0", "package",
    ),
  ].filter(Boolean);
  for (const caminho of candidatos) {
    if (fs.existsSync(caminho)) {
      try {
        return require(caminho);
      } catch {
        // Caminho existe mas não é um pacote utilizável; segue para o próximo.
      }
    }
  }
  console.error(
    "Playwright não encontrado. Instale-o em frontend/node_modules ou defina " +
    "PLAYWRIGHT_CORE com o caminho do pacote playwright-core.",
  );
  process.exit(3);
}

function argumento(nome, padrao) {
  const indice = process.argv.indexOf(nome);
  return indice > -1 && process.argv[indice + 1] ? process.argv[indice + 1] : padrao;
}

const URL = argumento("--url", "http://127.0.0.1:8000").replace(/\/$/, "") + "/";
const EXEMPLOS = path.join(RAIZ, "exemplos");
const ANUAL = path.join(EXEMPLOS, "BASE_DEMONSTRACAO_ANONIMIZADA_LOTE_ANUAL.xlsx");
const MODULO = path.join(EXEMPLOS, "BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx");

const problemas = [];

function check(nome, ok, detalhe = "") {
  console.log((ok ? "  PASS  " : "  FALHA ") + nome + (detalhe ? " :: " + detalhe : ""));
  if (!ok) problemas.push(nome + (detalhe ? " :: " + detalhe : ""));
}

const ROTAS = [
  ["processamento", "Processar uma nova alocação"],
  ["dashboard", null],
  ["insights", null],
  ["cenarios", "Cenários de reajuste"],
  ["exportacao", null],
];

async function percorrer(browser, tema) {
  const page = await browser.newPage({
    colorScheme: tema === "dark" ? "dark" : "light",
  });
  const excecoes = [];
  page.on("pageerror", (erro) => excecoes.push(String(erro.message)));
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("Failed to load resource")) {
      excecoes.push("console: " + msg.text());
    }
  });

  console.log("\n" + "=".repeat(70));
  console.log("TEMA " + tema.toUpperCase());
  console.log("=".repeat(70));

  // 1. Toda aba desenha, e nenhuma cai na barreira de erro.
  for (const [rota, marca] of ROTAS) {
    await page.goto(URL + "#/" + rota, { waitUntil: "networkidle" });
    await page.waitForTimeout(700);
    const raiz = await page.locator("#root").innerHTML();
    check(`${tema}: aba ${rota} desenha`, raiz.length > 500, `${raiz.length} caracteres`);
    check(
      `${tema}: aba ${rota} sem falha de render`,
      !(await page.getByText("Não foi possível desenhar").isVisible().catch(() => false)),
    );
    if (marca) {
      check(
        `${tema}: aba ${rota} mostra "${marca}"`,
        await page.getByText(marca).first().isVisible().catch(() => false),
      );
    }
  }

  // 2. O lote faz as mesmas perguntas da rodada única e sobrevive à validação.
  await page.goto(URL + "#/processamento", { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "Lote de módulos" }).click();
  await page.waitForTimeout(300);
  for (const pergunta of [
    "Quem pode assumir cada disciplina?",
    "Quanta prova a rodada precisa entregar?",
  ]) {
    check(
      `${tema}: lote oferece "${pergunta}"`,
      await page.getByText(pergunta).first().isVisible().catch(() => false),
    );
  }

  if (!fs.existsSync(ANUAL)) {
    check(`${tema}: base anual de demonstração disponível`, false, ANUAL);
    await page.close();
    return;
  }

  await page.locator('input[type="file"]').setInputFiles(ANUAL);
  await page.waitForTimeout(5000);
  check(
    `${tema}: inspeção lista os módulos encontrados`,
    await page.getByText("Módulos encontrados nas planilhas").isVisible().catch(() => false),
  );

  await page.getByRole("button", { name: /Validar \d+ módulo/ }).click();
  await page.waitForTimeout(15000);
  const raizPos = await page.locator("#root").innerHTML();
  // Este é o caso que já quebrou: a tela sumia inteira durante a validação.
  check(`${tema}: a tela sobrevive à validação`, raizPos.length > 500, `${raizPos.length} caracteres`);
  check(
    `${tema}: passo 2 aparece com o resultado da validação`,
    await page.getByText("Resultado da validação").isVisible().catch(() => false),
  );

  // 3. Voltar para a rodada única pela aba, como o operador faz.
  await page.getByRole("tab", { name: "Rodada única" }).click();
  await page.waitForTimeout(500);
  check(
    `${tema}: voltar para rodada única mostra o fluxo de sempre`,
    await page.getByText("Uma planilha, um módulo, uma rodada.").isVisible().catch(() => false),
  );
  check(
    `${tema}: rodada única pede o módulo esperado`,
    await page.getByText("Módulo esperado").isVisible().catch(() => false),
  );
  if (fs.existsSync(MODULO)) {
    await page.locator('input[type="file"]').setInputFiles(MODULO);
    await page.waitForTimeout(1500);
    check(
      `${tema}: rodada única aceita a planilha`,
      (await page.locator(".dropzone.has-file").count()) > 0,
    );
  }

  check(`${tema}: nenhuma exceção de render`, excecoes.length === 0, excecoes.join(" | "));
  await page.close();
}

(async () => {
  const { chromium } = carregarPlaywright();
  let browser;
  try {
    browser = await chromium.launch({ channel: "chrome", headless: true });
  } catch (erro) {
    console.error("Não foi possível abrir o Chrome:", erro.message);
    process.exit(3);
  }
  try {
    for (const tema of ["light", "dark"]) {
      await percorrer(browser, tema);
    }
  } finally {
    await browser.close();
  }
  console.log("\n" + "=".repeat(70));
  console.log("FALHAS: " + problemas.length);
  problemas.forEach((item) => console.log("  - " + item));
  process.exit(problemas.length ? 1 : 0);
})().catch((erro) => {
  console.error("A verificação não pôde ser concluída:", erro);
  process.exit(2);
});
