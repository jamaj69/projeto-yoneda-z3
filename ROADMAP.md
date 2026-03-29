# 🗺️ Roadmap - Projeto Yoneda-Z3

## Status Atual: v0.3.0 ✅

### Funcionalidades Implementadas

- ✅ **Servidor Haskell REST**: Scotty + algebraic-graphs
- ✅ **Heurística MWR+SPT**: 77% melhor que toposort simples
- ✅ **Z3 Integration**: Busca livre (hints apenas referência)
- ✅ **Benchmark Loader**: 242 instâncias de 8 datasets clássicos
- ✅ **Análise de Gargalos**:
  - Cálculo de slack (folga)
  - Identificação de caminho crítico
  - Análise de utilização de máquinas
  - Detecção de bottlenecks (>85% uso)
- ✅ **Documentação Técnica**: 4 guias completos
- ✅ **Visualização**: Gráficos de Gantt comparativos

---

## 🎯 Próximos Passos (v0.4.0)

### 1. Refinamento Local com Gargalos (ALTA PRIORIDADE)

**Objetivo**: Usar análise de gargalos para melhorar heurística antes do Z3

#### A) Swap de Tarefas em Máquinas Críticas

```haskell
-- Em Main.hs
swapTasksOnCriticalMachine :: Machine -> [Task] -> Starts -> Maybe Starts
swapTasksOnCriticalMachine m tasks starts =
    -- Para máquinas com >90% de uso:
    -- 1. Listar tarefas consecutivas na máquina
    -- 2. Tentar trocar ordem de pares de tarefas
    -- 3. Verificar se respeita precedências
    -- 4. Recalcular makespan
    -- 5. Aceitar se melhorou
```

**Teste esperado**:

- abz5: 1451h → ~1350h (8% de melhoria adicional)
- Tempo: +50ms (ainda muito rápido)

#### B) Shift de Tarefas Críticas

```haskell
shiftCriticalTask :: Task -> Slack -> Starts -> Maybe Starts
shiftCriticalTask task slack starts =
    -- Para tarefas críticas (slack=0):
    -- Tentar mover ±duration dentro dos limites
    -- Explorar janelas de slack vizinhas
```

**Benefício esperado**:

- Encontrar soluções localmente ótimas
- Reduzir gap Z3: 15% → 8%

#### C) Load Balancing Iterativo

```haskell
balanceMachineLoad :: [(Machine, [Task])] -> Starts
balanceMachineLoad machines =
    iterateUntil convergence $ \starts ->
        let overloaded = filter (utilization > 0.85) machines
            underloaded = filter (utilization < 0.50) machines
        in tryMoveTask overloaded underloaded starts
```

**Resultado esperado**:

- Máquinas mais equilibradas (60% → 75% uso médio)
- Redução de gargalos

**Meta**: Implementar em 1-2 dias

---

### 2. Otimização Z3 Focada (MÉDIA PRIORIDADE)

**Objetivo**: Usar bottlenecks para reduzir espaço de busca do Z3

#### Estratégia 1: Fixar Tarefas Não-Críticas

```python
# Em example_usage.py
def optimize_with_fixed_tasks(tasks, hints, slacks, critical_path):
    opt = Optimize()
    
    # Fixar 95% das tarefas (não-críticas)
    for task in non_critical_tasks:
        opt.add(starts[task.id] == hints[task.id])
    
    # Otimizar apenas 5% (críticas)
    for task in critical_tasks:
        pass  # Deixar livre
    
    return opt.minimize(makespan)
```

**Benefício**:

- ✅ Espaço de busca: O(n^n) → O((0.05n)^n) = **redução massiva**
- ✅ Tempo: 10s → ~2s (5x mais rápido)
- ⚠️ Risco: Pode perder ótimo global se análise de slack estiver imprecisa

#### Estratégia 2: Priorizar Branching em Tarefas Críticas

```python
# Z3 táticas customizadas
opt.set("priority", "critical_path_first")
opt.set("search_mode", "depth_first_critical")
```

**Meta**: Implementar em 2-3 dias

---

### 3. Visualização de Gargalos (BAIXA PRIORIDADE)

**Objetivo**: Tornar análise de bottlenecks visual

#### Gráfico de Gantt com Slack

```python
import matplotlib.pyplot as plt

def plot_with_critical_path(solution, slacks):
    for task in solution:
        # Cor baseada em slack
        color = 'red' if slacks[task.id] == 0 else \
                'orange' if slacks[task.id] < 10 else \
                'green'
        
        plt.barh(task.machine, task.duration, 
                left=task.start, color=color, alpha=0.8)
    
    # Destacar caminho crítico
    for task in critical_path:
        plt.scatter(task.start, task.machine, 
                   color='black', marker='>', s=100)
```

**Saída visual**:

- 🔴 Vermelho: Tarefas críticas (slack=0)
- 🟠 Laranja: Quase críticas (slack<10)
- 🟢 Verde: Com folga (slack≥10)
- ➡️ Setas: Caminho crítico

#### Gráfico de Utilização

```python
def plot_machine_utilization(machine_util):
    machines = sorted(machine_util.keys())
    utils = [machine_util[m] * 100 for m in machines]
    
    colors = ['red' if u > 90 else 
              'orange' if u > 70 else 
              'green' for u in utils]
    
    plt.bar(machines, utils, color=colors)
    plt.axhline(y=90, color='r', linestyle='--', label='Gargalo')
    plt.ylabel('Utilização (%)')
    plt.title('Análise de Gargalos - Máquinas')
```

**Meta**: Implementar em 1 dia

---

## 🚀 Futuro (v0.5.0+)

### 1. Heurísticas Alternativas

- **Tabu Search**: Memória de movimentos ruins
- **Simulated Annealing**: Aceitar pioras probabilisticamente
- **Genetic Algorithm**: População de soluções

### 2. Paralelização

- Resolver múltiplas instâncias em paralelo
- Z3 com múltiplos cores (`opt.set("threads", 4)`)
- Batch processing de benchmarks

### 3. Interface Web

- Dashboard com visualizações interativas
- Upload de instâncias customizadas
- Comparação de heurísticas lado a lado

### 4. Machine Learning

- Aprender prioridades de dispatching regras
- Prever makespan antes de resolver
- Classificar instâncias fáceis/difíceis

---

## 📊 Métricas de Sucesso

### v0.4.0 (Refinamento Local)

| Métrica | Atual (v0.3.0) | Meta (v0.4.0) | Melhoria |
| ------- | -------------- | ------------- | -------- |
| **Makespan abz5** | 1451h | ≤1350h | -7% |
| **Gap vs Z3** | 15% | ≤10% | -33% |
| **Tempo Heurística** | 8ms | ≤60ms | +650% OK |
| **Uso médio máquinas** | 60% | ≥70% | +17% |

### v0.5.0 (Z3 Focado)

| Métrica | Atual (v0.3.0) | Meta (v0.5.0) | Melhoria |
| ------- | -------------- | ------------- | -------- |
| **Tempo Z3** | 10s | ≤3s | -70% |
| **Qualidade** | 1234h | 1234h | Mantém ótimo |
| **Espaço busca** | 100% | ~10% | -90% |

---

## 🎓 Aprendizados e Insights

### Do que funcionou bem

1. **MWR+SPT**: Melhoria drástica com lógica simples
2. **Z3 sem hints**: Remover constraints foi contra-intuitivo mas correto
3. **Benchmarks**: 242 instâncias dão confiança estatística
4. **Análise de slack**: Revela estrutura do problema

### Do que precisa de atenção

1. **Slack calculation**: Apenas 1 tarefa crítica em abz5 parece baixo
   - Pode ser erro no cálculo de LST (Latest Start Time)
   - Revisar algoritmo reverso de computação
2. **Z3 non-determinism**: 1234h vs 1250h (~1% variação)
   - Aceitável para prática, mas investigar se há erro lógico
3. **Setup time**: Atualmente fixo (0), poderia ser por job/máquina

---

## 📅 Timeline Proposto

```text
Semana 1-2:  Implementar refinamento local (swaps + shifts)
Semana 3:    Testes em todos os 242 benchmarks
Semana 4:    Otimização Z3 focada (fixar não-críticas)
Semana 5:    Visualizações de gargalos
Semana 6:    Documentação final + paper draft
```

---

## 🤝 Como Contribuir

Se você quiser implementar alguma dessas features:

1. Escolha um item da lista acima
2. Crie uma branch: `git checkout -b feature/nome-da-feature`
3. Implemente + testes + documentação
4. Pull request com descrição detalhada

**Prioridades sugeridas**:

- 🔥 Alta: Refinamento local (impacto imediato)
- 🔶 Média: Z3 focado (otimização importante)
- 🔹 Baixa: Visualizações (nice to have)

---

## 📖 Referências para Implementação

### Refinamento Local

- Aarts & Lenstra (1997): "Local Search in Combinatorial Optimization"
- Taillard (1993): Tabu search original para JSSP
- Nowicki & Smutnicki (1996): i-TSAB algorithm

### Critical Path Analysis

- Kelley & Walker (1959): CPM (Critical Path Method)
- Roy (1959): PERT analysis
- Johnson (1954): Algorithms for JSSP

### Z3 Optimization

- Bjørner & Phan (2014): "νZ - Maximal Satisfaction with Z3"
- SMT-LIB 2.0: Optimization extensions
- Microsoft Z3 Documentation: Tactics & Strategies

---

**Última atualização**: 2026-04-01  
**Versão**: 0.3.0  
**Status**: 🟢 Ativo
