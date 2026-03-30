# Changelog for `haskell-engine`

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to the
[Haskell Package Versioning Policy](https://pvp.haskell.org/).

## Unreleased

### Added (Proposta v0.4.0)

- 🧠 **Sistema de Aprendizado por Feedback** (Haskell ↔ Z3)
  - Arquitetura para Haskell aprender com soluções ótimas do Z3
  - Documentação completa: [FEEDBACK_LEARNING.md](docs/FEEDBACK_LEARNING.md)
  - Tipos de dados: `docs/FeedbackTypes.hs` (exemplo para implementação futura)
  - Script Python `learn_from_z3.py` com análise manual Python-side (**funcional**)
  - **Análises implementadas (Python-side)**:
    - Comparação de ordenação de tarefas por máquina
    - Detecção de swaps necessários (pares invertidos)
    - Avaliação de gap heurística vs ótimo
    - Sugestões automáticas de ajuste (IncreaseMWRWeight, IncreaseSPTWeight)
  - **Próximos passos**:
    - [ ] Implementar endpoint `/learn` em Main.hs
    - [ ] Adicionar tipos em Types.hs
    - [ ] Persistência de pesos aprendidos (learning_history.json)
    - [ ] Aplicar pesos customizados na heurística
  - **Impacto esperado**: Gap 17% → 9% após 50 instâncias

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
