# Teacher Allocation Optimizer

<!-- TODO: descomentar quando o CI estiver ativo (Fase 1 do plano)
![CI](https://github.com/guilhermehrsilva/teacher-allocation-optimizer/actions/workflows/ci.yml/badge.svg)
-->
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**How do you optimally assign hundreds of teachers to courses while respecting eligibility rules, workload limits, and institutional constraints?**

Full-stack optimization system that automates teacher-to-course allocation using CP-SAT constraint programming, with data validation, audit trails, scenario simulation, and a web dashboard for operational monitoring.

<!-- TODO: substituir por um GIF de 10-15s mostrando upload → validação → alocação → dashboard.
     Grave com ScreenToGif (Windows). É o item de maior impacto deste README. -->
<!-- ![Demo](docs/evidencias/demo.gif) -->

<!-- TODO: publicar com dados sintéticos e adicionar aqui:
**[▶ Live demo](https://...)** — sample spreadsheet included, no real data required.
-->

## Why this exists

Teacher allocation in a large distance-learning operation was handled manually through spreadsheets: slow, hard to audit, and impossible to simulate alternatives. Each round required reconciling eligibility rules, workload caps, and institutional policy by hand.

This system turns that into a reproducible pipeline — validate, solve, audit, simulate — where every allocation round is traceable and every policy change can be tested before it is adopted.

<!-- TODO: preencher com números reais. Sem eles o projeto parece um exercício.
| Metric | Before | After |
|--------|--------|-------|
| Time per allocation round | ? hours | ? minutes |
| Teachers handled | — | ? |
| Courses handled | — | ? |
| Constraints enforced | manual | ? automated rules |
-->

## Key highlights

| Feature | Detail |
|---------|--------|
| Solver | Google OR-Tools CP-SAT |
| Approach | Constraint programming + GRASP metaheuristic |
| Validation | Automated rule checking with inconsistency reports |
| Scenarios | Isolated what-if engine for policy simulation |
| Audit | Full traceability per round (JSON + XLSX) |
| Interface | React + FastAPI web dashboard |
| Quality | Test suite, SBOM (CycloneDX), third-party license inventory |

## Stack

`Python 3.12` · `OR-Tools (CP-SAT)` · `FastAPI` · `React 19` · `TypeScript` · `Vite` · `Pandas` · `SQLite`

## How it works

1. **Upload** — institutional spreadsheet with teachers, courses, and constraints
2. **Validate** — automated rule-checking flags inconsistencies before solving
3. **Optimize** — CP-SAT solver finds optimal teacher-course assignments
4. **Audit** — every round generates traceability reports
5. **Simulate** — an isolated secondary engine runs alternative scenarios without touching the primary solver
6. **Monitor** — web dashboard tracks execution and results

The two engines are deliberately separated: the scenario tab can never modify or silently replace the primary solver's published round.

## Architecture

```
├── engines/
│   ├── primary/        # main solver, preserved and versioned
│   └── scenarios/      # isolated what-if engine
├── backend/            # FastAPI, orchestration, audit, security middleware
├── frontend/           # React + TypeScript dashboard
├── docs/               # executive, functional and technical documentation
├── scripts/            # install, test and release tooling
└── exemplos/           # synthetic sample data
```

## Running locally

```bash
git clone https://github.com/guilhermehrsilva/teacher-allocation-optimizer.git
cd teacher-allocation-optimizer

# Backend — Python 3.12 or 3.13, 64-bit
pip install -r requirements.txt

# Frontend — builds the dashboard the API serves
pwsh scripts/construir_frontend.ps1

python executar.py
```

The dashboard opens at `http://127.0.0.1:8000`. A synthetic sample spreadsheet is available in `exemplos/` — no real institutional data is required or included in this repository.

The build step needs Node.js 20.19+ or 22.12+ and runs once. The production bundle is not versioned, so a fresh clone builds it locally; `executar.py` refuses to start without it rather than serving a stale interface.

<!-- TODO Fase 1: substituir por
```bash
docker compose up
```
-->

### Frontend development

```bash
cd frontend && npm install && npm run dev
```

Requires Node.js 20.19+ or 22.12+. The production build is generated at release time and is not versioned.

## Documentation

Full documentation lives in [`docs/`](docs/) — start with the [Operational Manual](docs/MANUAL_OPERACIONAL.md) for setup and usage, or the [executive overview](docs/00_VISAO_EXECUTIVA.md) for the business context (Portuguese). Business rules, architecture, solver design, API, security, and QA are documented separately.

## Data privacy

This repository contains **no real institutional data**. All examples are synthetic. Real datasets are kept outside the package by design — see [`docs/07_SEGURANCA_PRIVACIDADE.md`](docs/07_SEGURANCA_PRIVACIDADE.md).

## License

MIT — see [LICENSE](LICENSE).
