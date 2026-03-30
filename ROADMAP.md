# 🗺️ Roadmap - Projeto Yoneda-Z3

## Status Atual: v0.4.0 ✅

### Funcionalidades Implementadas

- ✅ **Servidor Haskell REST**: Scotty + algebraic-graphs, porta 3000
- ✅ **Phase 1a — MWR+SPT**: List scheduling, 77% melhor que toposort
- ✅ **Phase 1b — Shifting Bottleneck Procedure**:
  - Schrage heuristic para `1|r_j|max(C_j+q_j)`
  - Carlier B&B com node budget (empiricamente budget=0 = pure Schrage)
  - Iterative machine decomposition + single-pass re-optimization
- ✅ **Phase 2 — Yoneda-fused Neighborhoods**:
  - `newtype Yoneda f a` para fmap fusion O(1)
  - N2 (adjacent swap), N5 (block rotation), N7 (task reinsertion)
  - `greedySweep` carry-forward com `foldl'`
  - `refinementPipeline` left-fold com convergência por estágio
  - Adaptive: `firstImprovementSel` para n>500, `steepestDescent` para menores
- ✅ **Phase 3 — Bottleneck Analysis**: Slack, critical path, machine utilization
- ✅ **OR-Tools CP-SAT**: Full solver com `NewIntervalVar` + `AddNoOverlap`
- ✅ **Benchmark Loader**: 242 instâncias de 8 datasets clássicos
- ✅ **Documentação Técnica**: 5 guias

### Resultados Atuais (Haskell heurística pura)

| Instance | Dim | MWR | SBP | Refined | BKS | Gap | Time |
|----------|-----|-----|-----|---------|-----|-----|------|
| ft06 | 6×6 | 69 | 60 | 60 | 55 | +9.1% | <0.1s |
| la01 | 10×5 | 880 | 666 | **666** | 666 | **OPT** | <0.1s |
| abz5 | 10×10 | 1451 | 1334 | 1312 | 1234 | +6.3% | 0.2s |
| abz9 | 10×10 | 1132 | 849 | 801 | 661 | +21.2% | 2.5s |
| dmu10 | 20×20 | 4765 | 4143 | 3621 | n/a | — | 4.3s |
| ta71 | 100×20 | 8010 | 5930 | 5886 | 5464 | +7.7% | 24s |

### Empirical Findings (tested and rejected)

- ❌ **Carlier B&B depth/budget > 0**: Schrage already optimal per subproblem for all tested JSSP instances
- ❌ **SBP convergence loop**: Schrage tie-breaking causes oscillation between equally-good orderings (abz9 regressed 801→821)
- ❌ **OR-Tools warm-start from Haskell**: CP-SAT cold-start is empirically better; hints bias workers toward suboptimal neighborhoods

---

## 🎯 v0.5.0 — Haskell Engine Improvements

### 1. Replace `algebraic-graphs` with IntMap Adjacency (ALTA PRIORIDADE)

**Problem**: `buildSolutionGraph` does a full `algebraic-graphs` rebuild (O(V log V)) on every `evalCandidate` call. For ta71 (2000 tasks), this is the dominant cost.

**Solution**: Replace with `IntMap IntSet` adjacency list:
- O(1) amortized edge add/remove
- Incremental swap: modify only 2-4 edges instead of rebuilding entire graph
- Forward pass reuses unchanged portions

```haskell
type AdjList = IntMap IntSet

swapEdges :: AdjList -> Int -> Int -> AdjList
-- O(1) amortized: disconnect old arcs, add new arcs

incrementalForwardPass :: AdjList -> Map Int Int -> Int -> Int -> Map Int Int
-- Recompute ESTs only for affected descendants
```

**Expected impact**:
- `evalCandidate` from O(V log V) → O(affected nodes)
- ta71: 24s → ~5s estimated
- Enables more iterations in N2/N5/N7 within same time budget

### 2. Tabu Search over N2/N5 (ALTA PRIORIDADE)

**Problem**: Current neighborhoods converge to first local minimum. No mechanism to escape.

**Solution**: Short-term memory tabu list prevents revisiting recent swaps:

```haskell
data TabuState = TabuState
  { tsBest   :: SearchState
  , tsCurrent :: SearchState
  , tsTabu   :: Seq (Int, Int)  -- ring buffer of forbidden swap pairs
  , tsIter   :: Int
  }

tabuSearch :: Int -> Int -> [TaskReq] -> Map Int TaskReq -> SearchState -> SearchState
-- maxIter, tabuTenure, tasks, taskMap, initial -> best found
```

**Key design decisions**:
- Tabu tenure: `sqrt(n)` where n = number of tasks
- Accept non-improving moves when all neighbors are tabu
- Aspiration: accept tabu move if it improves global best
- Budget: 1000 iterations for n≤100, 500 for n≤500, 200 for n>500

**Expected impact**: abz5: 1312→~1260, abz9: 801→~720

### 3. SBP with Disjunctive Graph Caching (MÉDIA PRIORIDADE)

**Problem**: `shiftingBottleneck` rebuilds the full disjunctive graph for every `sbpOneMachine` call. For ta71 (20 machines × ~20 SBP calls = 400 graph rebuilds), this is expensive.

**Solution**: Thread the graph through SBP iterations:

```haskell
shiftingBottleneck' :: [TaskReq] -> AdjList -> MachineOrder -> (MachineOrder, AdjList)
-- Carry forward the graph, only add/modify disjunction arcs for newly scheduled machine
```

**Expected impact**: SBP phase from ~8s → ~2s for ta71

### 4. Better Schrage Tie-Breaking (MÉDIA PRIORIDADE)

**Problem**: When multiple released jobs have equal `q`, Schrage picks arbitrarily. This creates the oscillation that prevents SBP convergence.

**Solution**: Composite tie-breaker: `(negate q, remaining_work, spt, task_id)`:

```haskell
schrageSM' :: [SMJob] -> Map Int Int -> ([Int], Int)
-- Extra parameter: remaining work per job for tie-breaking
```

**Expected impact**: SBP convergence may become feasible → better SBP-only results before N2/N5/N7

### 5. Parallel Neighborhood Evaluation (BAIXA PRIORIDADE)

**Problem**: N7 generates up to 500 candidates, evaluated sequentially.

**Solution**: Use `Control.Parallel.Strategies` for parallel candidate evaluation:

```haskell
n7Parallel :: [TaskReq] -> Map Int TaskReq -> SearchState -> SearchState
n7Parallel tasks taskMap ss =
  let candidates = generateN7Candidates tasks taskMap ss
      evaluated = parMap rseq (evalCandidate tasks taskMap ss) candidates
  in minimumBy (comparing ssMS) (catMaybes evaluated)
```

**Expected impact**: 2-4× speedup on N7 phase for multi-core systems. Only worthwhile after IntMap adjacency (item 1) reduces per-candidate cost.

### 6. Instance-Adaptive Phase Selection (BAIXA PRIORIDADE)

**Problem**: Fixed pipeline (MWR→SBP→N2→N5→N7) regardless of instance structure. Some instances respond better to different orderings.

**Solution**: Quick feature extraction → phase selection:

```haskell
data InstanceFeatures = InstanceFeatures
  { ifJobMachineRatio :: Double
  , ifDurationVariance :: Double
  , ifMachineContention :: Double  -- avg tasks per machine
  }

selectPipeline :: InstanceFeatures -> [(Int, Neighborhood)]
-- High contention → more N2/N5 iterations
-- High variance → SBP more valuable
-- Low ratio → skip N7 (too expensive for marginal gain)
```

---

## 🚀 Futuro (v0.6.0+)

### 1. Simulated Annealing / Late Acceptance Hill Climbing

- Accept worsening moves with probability `exp(-delta/T)`
- LAHC: accept if better than solution k iterations ago
- More robust than tabu search for large instances

### 2. Parallelização

- Resolver múltiplas instâncias em paralelo
- Multi-start: run N independent refinement pipelines, keep best
- OR-Tools: `solver.parameters.num_workers` for internal parallelism

### 3. Machine Learning para Dispatching

- Treinar modelo em pares (instance_features, optimal_ordering)
- Substituir MWR+SPT por learned priority function
- Usar dados dos 242 benchmarks como training set

### 4. Interface Web

- Dashboard com visualizações interativas (Gantt, utilização)
- Upload de instâncias customizadas
- Comparação side-by-side: heurística vs solver

---

## 📊 Métricas de Sucesso

### v0.5.0 (Engine Improvements)

| Métrica | Atual (v0.4.0) | Meta (v0.5.0) |
| ------- | -------------- | ------------- |
| **abz5** | 1312 | ≤1260 (-4%) |
| **abz9** | 801 | ≤720 (-10%) |
| **ta71** | 5886 | ≤5700 (-3%) |
| **ta71 time** | 24s | ≤8s (-67%) |
| **la01** | 666 OPT | 666 OPT (maintain) |

### v0.6.0 (Advanced Search)

| Métrica | Meta |
| ------- | ---- |
| **abz5** | ≤1240 (≤0.5% gap) |
| **ta71** | ≤5550 (≤1.6% gap) |
| **Instances at OPT** | ≥3 of benchmark set |

---

## 🎓 Aprendizados e Insights

### O que funcionou

1. **Yoneda fmap fusion**: Elimina listas intermediárias nos pipelines de vizinhança
2. **greedySweep carry-forward**: Permite cadeias dependentes de swaps (la01→OPT)
3. **Phase composition**: MWR→SBP→N2→N5→N7 dá reduções compostas
4. **Adaptive budgets**: `firstImprovementSel` para instâncias grandes evita explosão quadrática

### O que não funcionou

1. **Carlier B&B**: Para subproblemas JSSP, Schrage já é ótimo (Jackson LB = Schrage UB)
2. **SBP convergence loop**: Schrage tie-breaking causa ciclos entre soluções equivalentes
3. **OR-Tools warm-start**: CP-SAT's portfolio solver is already better cold

### Observações técnicas

1. **Bottleneck real**: `algebraic-graphs` rebuild é O(V log V) por candidato — domina custo
2. **N7 é caro mas efetivo**: Reinserção em todas as posições encontra melhorias que N2/N5 perdem
3. **SBP vs MWR**: SBP é consistentemente melhor, mas o ganho vem mais da decomposição do que do Carlier

---

## 📖 Referências

### Implementados

- Adams, Balas & Zawack (1988): Shifting Bottleneck Procedure
- Schrage (1984): Greedy heuristic for single-machine scheduling
- Carlier (1982): Branch-and-bound for `1|r_j|Lmax`
- Nowicki & Smutnicki (1996): N2 neighborhood (i-TSAB)
- van Laarhoven, Aarts & Lenstra (1992): N5 neighborhood
- Dell'Amico & Trubian (1993): N7 neighborhood

### Para implementação futura

- Nowicki & Smutnicki (2005): Path relinking for JSSP
- Balas & Vazacopoulos (1998): Guided Local Search
- Zhang, Gao & Shi (2007): Tabu search with N5+N7

---

**Última atualização**: 2026-03-30
**Versão**: 0.4.0
**Status**: 🟢 Ativo
