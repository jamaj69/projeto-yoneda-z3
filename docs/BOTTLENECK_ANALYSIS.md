# Análise de Gargalos e Otimização Focada

## 🎯 Objetivo

Detectar **pontos críticos** (bottlenecks) na solução heurística para:

1. Entender quais tarefas/máquinas limitam o makespan
2. Focar esforços de otimização onde terão mais impacto
3. Melhorar qualidade dos hints para o Z3

## 🔬 Técnicas Implementadas

### 1. Análise de Slack (Folga)

**O que é Slack?**

- Quantidade de tempo que uma tarefa pode **atrasar** sem afetar o makespan total
- Tarefas com slack = 0 estão no **caminho crítico**

**Cálculo:**

```haskell
Slack(tarefa) = Latest Start Time - Earliest Start Time
```

**Interpretação:**

- `Slack = 0` → Tarefa **crítica** (não pode atrasar)
- `Slack > 0` → Tarefa tem folga (pode ser otimizada depois)

### 2. Caminho Crítico (Critical Path)

**Definição:**

- Sequência de tarefas com slack = 0 que determina o makespan
- Qualquer atraso nessas tarefas **aumenta o makespan**

**Por que importa:**

- Otimizar tarefas críticas tem **impacto direto** no makespan
- Otimizar tarefas não-críticas pode não melhorar nada

### 3. Análise de Utilização de Máquinas

**Cálculo:**

```haskell
Utilização(máquina) = Tempo_Total_Trabalhado / Makespan
```

**Interpretação:**

- `Utilização > 90%` → **Gargalo** (máquina muito ocupada)
- `Utilização < 50%` → Ociosidade (pode receber mais tarefas)

**Impacto:**

- Máquinas com alta utilização são candidatas para:
  - Reordenamento de tarefas
  - Minimização de setup times
  - Paralelização quando possível

## 📊 Resultados do Sistema

### Teste com abz5 (10×10, 100 tarefas)

```text
===== HASKELL (Heurística MWR+SPT + Análise) =====
Makespan:              1451h
Caminho crítico:       1 tarefa
Máquinas críticas:     []
Utilização máxima:     59.8%
Tarefas críticas:      1/100 (1%)

===== Z3 (Otimização Focada) =====
Makespan:              1234h
Melhoria:              217h (15.0%)
Tarefas críticas:      6 (na solução ótima)
```

### Análise

**Observações:**

1. **Utilização baixa** (59.8%) → Espaço para melhoria no balanceamento
2. **Poucas tarefas críticas** na heurística → Muita folga desnecessária
3. **Z3 redistribuiu o trabalho** → Mais tarefas críticas (6) = melhor balanceamento

## 🚀 Estratégias de Otimização Baseadas em Gargalos

### Fase 1: Identificação (✅ Implementado)

```haskell
solveWithRefinement :: [TaskReq] -> (Starts, Makespan, Slacks, CriticalPath)
solveWithRefinement tasks = 
    let (starts, makespan) = solveHeuristic tasks  -- MWR+SPT
        slacks = computeSlack tasks starts makespan
        critical = findCriticalPath tasks slacks
    in (starts, makespan, slacks, critical)
```

**Retorna para o Python:**

- `hints`: Tempos de início de cada tarefa
- `makespan_heuristic`: Tempo total
- `slacks`: Folga de cada tarefa
- `critical_path`: IDs das tarefas críticas
- `critical_machines`: Máquinas com uso > 85%
- `machine_utilization`: % de uso de cada máquina

### Fase 2: Refinamento Local (🔜 A Implementar)

**Estratégias possíveis:**

#### A) Swap de Tarefas em Máquinas Críticas

```haskell
-- Tentar trocar ordem de tarefas na mesma máquina
swapTasksOnMachine :: Machine -> [Task] -> Maybe [Task]
swapTasksOnMachine m tasks =
    -- Para cada par de tarefas consecutivas na máquina:
    -- 1. Tentar inverter ordem
    -- 2. Verificar se respeita precedências
    -- 3. Recalcular makespan
    -- 4. Aceitar se melhorou
```

**Quando aplicar:**

- Máquina com utilização > 90%
- Tarefas sem dependência direta entre si

#### B) Earliest Deadline First (EDF)

```haskell
-- Priorizar tarefas com menor "deadline" restante
reorderByDeadline :: [Task] -> [Task]
reorderByDeadline = sortBy (comparing latestFinishTime)
```

**Quando aplicar:**

- Após identificar caminho crítico
- Priorizar tarefas que terminam no makespan

#### C) Load Balancing Iterativo

```haskell
-- Redistribuir tarefas para equilibrar máquinas
balanceMachines :: [(Machine, [Task])] -> [(Machine, [Task])]
balanceMachines machines =
    -- 1. Identificar máquina mais carregada
    -- 2. Identificar máquina mais ociosa
    -- 3. Mover tarefa elegível se possível
    -- 4. Repetir até convergir
```

**Quando aplicar:**

- Diferença de utilização > 30% entre máquinas
- Quando há flexibilidade de sequenciamento

### Fase 3: Integração com Z3 (💡 Proposta)

**Ideia:** Usar informação de gargalos para guiar o Z3

```python
# Em vez de buscar todo o espaço:
# 1. Fixar tarefas NÃO-críticas nos hints
# 2. Deixar Z3 otimizar apenas tarefas críticas

for task in non_critical_tasks:
    # Hard constraint (não soft)
    opt.add(starts[task.id] == hints[task.id])

for task in critical_tasks:
    # Deixar livre para otimizar
    pass
```

**Vantagens:**

- ✅ Reduz espaço de busca drasticamente
- ✅ Z3 foca onde realmente importa
- ✅ Converge mais rápido

**Desvantagens:**

- ⚠️ Pode perder ótimo global se análise de slack estiver errada
- ⚠️ Requer slack calculado corretamente

## 🎨 Visualização de Gargalos

### Diagrama de Gantt com Slack

```python
import matplotlib.pyplot as plt

def plot_with_slack(solution, slacks):
    for task in solution:
        # Cor baseada em slack
        if slacks[task.id] == 0:
            color = 'red'      # Crítica
        elif slacks[task.id] < 5:
            color = 'orange'   # Quase crítica
        else:
            color = 'green'    # Com folga
        
        plt.barh(task.machine, task.duration,
                left=task.start, color=color)
```

### Gráfico de Utilização de Máquinas

```python
def plot_utilization(machine_util):
    machines = list(machine_util.keys())
    utils = [machine_util[m] * 100 for m in machines]

    colors = ['red' if u > 90 else 'orange' if u > 70 else 'green'
              for u in utils]

    plt.bar(machines, utils, color=colors)
    plt.axhline(y=90, color='r', linestyle='--', label='Gargalo (90%)')
    plt.ylabel('Utilização (%)')
```

## 📈 Comparação com Abordagens Tradicionais

| Abordagem | makespan | Tempo | Comentário |
| ----------- | -------- | ----- | ------------ |
| **Heurística simples** | 6446h | 1ms | Toposort ingênuo |
| **Heurística MWR+SPT** | 1451h | 5ms | +77% melhor! |
| **+ Análise Gargalos** | 1451h | 8ms | Info para refinamento |
| **Z3 puro** | 1234h | 10s | Ótimo, mas lento |
| **Z3 + Gargalos** | 1234h | 10s | Mesma qualidade |
| **Z3 focado (futuro)** | ~1234h | ~5s | Busca reduzida |

## 🔧 Como Usar

### 1. Com análise básica (atual)

```bash
python script-python/solve_with_bottlenecks.py instances/abz5.txt
```

**Saída:**

- Identificação de tarefas críticas
- Máquinas gargalo
- Comparação heurística vs Z3

### 2. Com refinamento local (futuro)

```python
# No Haskell, após identificar gargalos:
refined_solution = refineBottlenecks(
    tasks,
    initialStarts,
    criticalTasks,
    criticalMachines
)
```

### 3. Com Z3 focado (futuro)

```python
# Fixar 95% das tarefas, otimizar 5% críticas
fix_non_critical_tasks(opt, starts, hints, non_critical)
optimize_critical_tasks(opt, starts, critical)
```

## 📚 Referências

- **Critical Path Method (CPM)**: PERT/CPM analysis (1950s)
- **Slack Time Analysis**: Roy (1959) "Graphes et ordonnancement"
- **Bottleneck Scheduling**: Goldratt "Theory of Constraints" (1984)
- **Local Search**: Aarts & Lenstra "Local Search in Combinatorial Optimization" (1997)

## 🎓 Conclusão

A análise de gargalos:

- ✅ Identifica onde focar otimização
- ✅ Permite refinamento dirigido
- ✅ Reduz espaço de busca do Z3
- ✅ Melhora entendimento do problema

**Próximo passo:** Implementar `refineBottlenecks` com local search em máquinas críticas para melhorar ainda mais a heurística antes de passar para o Z3!
