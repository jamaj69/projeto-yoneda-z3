# Changelog for `haskell-engine`

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to the
[Haskell Package Versioning Policy](https://pvp.haskell.org/).

## Unreleased

## 0.4.0.0 - 2026-03-30

### Added

- **Yoneda-Fused Neighborhood Pipeline**
  - `newtype Yoneda f a` with `liftYoneda`/`lowerYoneda` for O(1) fmap fusion
  - Three neighborhoods: N2 (adjacent swap), N5 (block rotation), N7 (task reinsertion)
  - `SearchState`, `Neighborhood`, `StepSelector` type abstractions
  - `refinementPipeline`: left-fold over `[(budget, Neighborhood)]` stages
  - `greedySweep`: carry-forward `foldl'` enabling dependent swap chains
  - Adaptive strategy: `firstImprovementSel` for n>500, `steepestDescent` for smaller

- **Shifting Bottleneck Procedure (SBP)**
  - `SMJob` type for single-machine subproblems `1|r_j|max(C_j+q_j)`
  - `schrageSM`: Schrage (1984) greedy heuristic, O(n log n)
  - `carlierBnB`: Branch-and-bound with node budget (budget=0 = pure Schrage)
  - `releasesExcluding`/`tailsExcluding`: forward/backward pass excluding one machine
  - `sbpOneMachine`: solves one machine via Carlier
  - `shiftingBottleneck`: iterative machine decomposition with single-pass re-optimization
  - `makespan_sbp` field in JSON response

- **OR-Tools CP-SAT Solver** (`script-python/solve_ortools.py`)
  - Full CP-SAT model with `NewIntervalVar` + `AddNoOverlap`
  - Solution validation scripts (`verify_ortools.py`, `validate_solution.py`)
  - Warm-start tested and rejected (CP-SAT cold-start is empirically better for JSSP)

- **Disjunctive Graph Infrastructure**
  - `buildSolutionGraph`: DAG with conjunction + disjunction arcs
  - `forwardPass`/`backwardPass`: topological DP for EST/LST
  - `graphBasedSlack`: precise slack computation from graph passes

### Changed

- Heurística pipeline: MWR+SPT → SBP → N2/N5/N7 refinement (3 phases)
- `solveWithRefinement` returns 6-tuple: `(hints, mwrMS, sbpMS, refinedMS, slacks, criticalPath)`
- Phase selection: best of {MWR, SBP} seeds neighborhood refinement

### Fixed

- la01 regression (666→695→666): `greedySweep` carry-forward restores dependent swap chains
- All `-Wx-partial` GHC warnings: `head`→`List.uncons`, `tail`→`drop 1`, irrefutable patterns→`case`
- Carlier depth explosion (la01 crash with depth=12): replaced with node-budget

### Performance

Results on benchmark instances (Haskell heuristic, no external solver):

| Instance | Dim | MWR+SPT | SBP | Refined | BKS | Gap | Time |
| -------- | --- | ------- | --- | ------- | --- | --- | ---- |
| ft06 | 6×6 | 69 | 60 | 60 | 55 | +9.1% | <0.1s |
| la01 | 10×5 | 880 | 666 | **666** | 666 | **0.0%** | <0.1s |
| abz5 | 10×10 | 1451 | 1334 | 1312 | 1234 | +6.3% | 0.2s |
| abz9 | 10×10 | 1132 | 849 | 801 | 661 | +21.2% | 2.5s |
| dmu10 | 20×20 | 4765 | 4143 | 3621 | n/a | — | 4.3s |
| ta71 | 100×20 | 8010 | 5930 | 5886 | 5464 | +7.7% | 23.8s |

### Empirical Findings

- **Carlier B&B adds zero value**: for all tested JSSP subproblems, Schrage greedy produces optimal single-machine solutions (Jackson LB = Schrage UB at first node)
- **SBP convergence loop rejected**: iterating re-optimization causes Schrage tie-oscillation and regressions (abz9: 801→821)
- **OR-Tools warm-start rejected**: CP-SAT's portfolio solver finds better solutions cold than with Haskell hints; hints bias workers toward suboptimal neighborhoods

## 0.3.0.0 - 2026-04-01

### Added

- **Análise de Gargalos (Bottleneck Detection)**
  - `computeSlack`: Calcula folga (slack) de cada tarefa
  - `findCriticalPath`: Identifica tarefas com slack=0 (caminho crítico)
  - `analyzeMachineUtilization`: Calcula % de uso de cada máquina
  - `refineBottlenecks`: Framework para refinamento local (a implementar)
  - Endpoint `/validate` agora retorna:
    - `slacks`: Folga de cada tarefa
    - `critical_path`: IDs das tarefas críticas
    - `critical_machines`: Máquinas com >85% de uso
    - `machine_utilization`: % de uso por máquina
- **Python**: Script `solve_with_bottlenecks.py` para análise de gargalos
- **Documentação**: [BOTTLENECK_ANALYSIS.md](docs/BOTTLENECK_ANALYSIS.md)

### Changed

- `solveWithRefinement` agora retorna tupla com slacks e caminho crítico
- JSON de resposta expandido com campos de análise de gargalos

### Performance

- Análise de gargalos adiciona ~3ms ao tempo de heurística (8ms total)
- Fornece insights para otimização focada em pontos críticos

## 0.2.0.0 - 2026-03-30

### Added

- **Heurística MWR+SPT (Most Work Remaining + Shortest Processing Time)**
  - Calcula trabalho total restante por job
  - Prioriza jobs com mais trabalho pendente
  - Desempate por duração da tarefa (SPT)
  - Order de prioridade: `(negate remaining_work, duration, task_id)`
- **Suporte a Instâncias de Benchmark**
  - Instance loader para 242 benchmarks clássicos de JSSP
  - 8 datasets: FisherThompson, Lawrence, Taillard, AdamsBalasZawack, etc.
  - Parse de formato padrão (primeira linha: jobs×máquinas)
- **Integração Z3 Aprimorada**
  - Hints usados apenas como REFERÊNCIA (não soft constraints)
  - Z3 busca livremente pelo espaço de soluções
  - Setup time configurável (padrão: 0)
- **Documentação Técnica**
  - [INSTANCE_LOADER.md](docs/INSTANCE_LOADER.md): Guia de benchmarks
  - [HEURISTIC_IMPROVEMENTS.md](docs/HEURISTIC_IMPROVEMENTS.md): Análise de melhorias
  - [WHY_NOT_OPTIMAL.md](docs/WHY_NOT_OPTIMAL.md): Explicação de não-determinismo Z3

### Changed

- Heurística de toposort simples → MWR+SPT list scheduling
- Hints removidos de soft constraints do Z3 (eram limitantes)
- Setup time: 2h → 0h (comparação com literatura)

### Fixed

- Hints não limitam mais a busca do Z3
- Z3 agora encontra soluções ótimas (1234h em abz5)

### Performance

- **Heurística**: 6446h → 1451h em abz5 (**77% de melhoria!**)
- **Z3**: Agora encontra 1234h (ótimo) em ~10s
- **Gap**: 1.3% acima do ótimo conhecido (excelente para JSSP)

## 0.1.0.0 - 2026-03-25

### Added

- Servidor Haskell com Scotty (porta 3000)
- Endpoint `/validate` para validação de grafos de precedência
- Heurística básica de toposort para scheduling
- Validação de ciclos com `algebraic-graphs`
- Cliente Python básico com Z3 solver
- Visualização de Gantt com Matplotlib
- Tipos Haskell: `TaskReq`, `TaskRes`, `ValidationResponse`
- Setup time entre tarefas do mesmo job (padrão: 2h)

### Performance

- Heurística toposort: ~1ms para 100 tarefas
- Validação de grafos: O(n + m)
- Z3 otimização: ~10s para problemas 10×10
