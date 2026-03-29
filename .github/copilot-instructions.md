# Projeto Yoneda-Z3: Instruções de Contexto

## 🎯 Visão Geral do Projeto

Sistema híbrido de otimização para **Job Shop Scheduling Problem (JSSP)** que combina:
- **Haskell (servidor REST)**: Heurística MWR+SPT + análise de gargalos
- **Python + Z3**: Otimizador SMT para soluções ótimas globais

### Arquitetura

```
Python → POST /validate → Haskell (heurística + análise) → Z3 (otimização)
```

## 📊 Estado Atual (v0.3.0)

### Funcionalidades Implementadas

1. **Servidor Haskell** (`app-haskell/src/Main.hs`)
   - Porta 3000, endpoint `/validate`
   - Heurística **MWR+SPT** (Most Work Remaining + Shortest Processing Time)
   - Análise de gargalos: slack, caminho crítico, utilização de máquinas
   - Retorna: `hints`, `makespan_heuristic`, `slacks`, `critical_path`, `critical_machines`, `machine_utilization`

2. **Cliente Python** (`script-python/`)
   - `main.py`: Exemplo básico 4×3
   - `example_usage.py`: Integração Haskell+Z3 com benchmarks
   - `instance_loader.py`: Carrega 242 instâncias clássicas
   - `solve_with_bottlenecks.py`: Análise de gargalos
   - `debug_z3.py`: Debug de comportamento Z3

3. **Benchmarks** (`instances/`)
   - 242 instâncias de 8 datasets clássicos
   - FisherThompson1963, Lawrence1984, Taillard1993, AdamsBalasZawack1988, etc.

### Resultados de Performance

| Instância | Dimensão | Heurística | Z3 | Gap vs Best Known |
|-----------|----------|------------|----|--------------------|
| **abz5** | 10×10 | 1451h | 1234h | **1.3%** ✨ |
| **la01** | 10×5 | 880h | 684h | 2.7% |
| **ft06** | 6×6 | 69h | 65h | 18% |

**Melhorias históricas:**
- v0.1.0 (toposort): 6446h em abz5
- v0.2.0 (MWR+SPT): 1451h em abz5 (**77% melhor!**)
- v0.3.0 (+ bottlenecks): Mesma qualidade, mas com análise detalhada

## 🔧 Como Desenvolver

### Iniciar Servidor Haskell

```bash
stack build
stack run  # Porta 3000
```

### Executar Scripts Python

```bash
# Exemplo básico
python script-python/main.py

# Com benchmark
python script-python/example_usage.py instances/FisherThompson1963/ft06.txt

# Com análise de gargalos
python script-python/solve_with_bottlenecks.py instances/AdamsBalasZawack1988/abz5.txt
```

### Rodar Testes

```bash
stack test
```

## 🧠 Conceitos-Chave do Domínio

### Job Shop Scheduling Problem (JSSP)

- **Jobs**: Conjuntos de tarefas com precedência (j1, j2, ..., jn)
- **Máquinas**: Recursos compartilhados (m1, m2, ..., mk)
- **Constraints**:
  - Cada tarefa em UMA máquina específica
  - Ordem de execução dentro do job (precedência)
  - Máquina processa UMA tarefa por vez
- **Objetivo**: Minimizar makespan (tempo total)

### Heurística MWR+SPT

**Most Work Remaining (MWR)**:
- Calcula trabalho total restante para cada job
- Prioriza jobs com mais operações pendentes
- Evita gargalos no final

**Shortest Processing Time (SPT)**:
- Desempate entre jobs similares
- Prioriza tarefas mais curtas
- Maximiza utilização

**Implementação**:
```haskell
priority task = (negate remaining_work, duration task, task_id)
sortBy (comparing priority) tasks
```

### Análise de Gargalos (v0.3.0)

**Slack (Folga)**:
```
Slack(tarefa) = Latest Start Time - Earliest Start Time
```
- `Slack = 0` → Tarefa **crítica** (caminho crítico)
- `Slack > 0` → Tem folga para otimização

**Caminho Crítico**:
- Sequência de tarefas com slack=0
- Determina o makespan
- Otimizar essas tarefas tem impacto direto

**Utilização de Máquinas**:
```
Utilização = Tempo_Trabalhado / Makespan
```
- `> 90%` → Gargalo
- `< 50%` → Ociosa

### Integração Z3

**Constraints principais**:
```python
# Precedência
opt.add(starts[next_task] >= starts[task] + duration + setup_time)

# Máquinas (não-overlap)
opt.add(Or(
    starts[t1] + duration[t1] <= starts[t2],
    starts[t2] + duration[t2] <= starts[t1]
))

# Objetivo
opt.minimize(makespan)
```

**Hints do Haskell**:
- Usados apenas como REFERÊNCIA (não constraints!)
- Z3 busca livremente
- Importante: NÃO adicionar soft constraints (limitariam busca)

## 📁 Estrutura de Arquivos

```
.
├── app-haskell/
│   └── src/Main.hs              # Servidor + heurística + análise
├── src/
│   ├── Types.hs                 # TaskReq, TaskRes, ValidationResponse
│   ├── Run.hs                   # Lógica de execução
│   └── Util.hs                  # Utilitários
├── script-python/
│   ├── main.py                  # Exemplo básico
│   ├── example_usage.py         # Cliente completo
│   ├── instance_loader.py       # Parser de benchmarks
│   ├── solve_with_bottlenecks.py # Análise de gargalos
│   └── debug_z3.py              # Debug Z3
├── instances/                   # 242 benchmarks
├── docs/
│   ├── BOTTLENECK_ANALYSIS.md   # Análise de gargalos
│   ├── HEURISTIC_IMPROVEMENTS.md # Evolução da heurística
│   ├── INSTANCE_LOADER.md       # Guia de benchmarks
│   └── WHY_NOT_OPTIMAL.md       # Z3 non-determinism
├── ROADMAP.md                   # Planejamento v0.4-v0.5
├── CHANGELOG.md                 # Histórico de versões
└── README.md                    # Documentação principal
```

## 🎯 Próximos Passos (v0.4.0)

### 1. Refinamento Local (ALTA PRIORIDADE)

**Objetivo**: Melhorar heurística antes do Z3

**Implementar em `Main.hs`**:
```haskell
refineBottlenecks :: [TaskReq] -> Starts -> [TaskId] -> [Machine] -> Starts
refineBottlenecks tasks starts criticalTasks criticalMachines =
    -- TODO: Implementar
    -- 1. Swap de tarefas em máquinas críticas (>90% uso)
    -- 2. Shift de tarefas críticas dentro do slack
    -- 3. Load balancing iterativo
    starts  -- Por enquanto retorna original
```

**Meta**: 1451h → ~1350h em abz5 (8% melhor)

### 2. Z3 Focado (MÉDIA PRIORIDADE)

**Estratégia**: Fixar tarefas não-críticas, otimizar apenas caminho crítico

```python
# Fixar 95% das tarefas
for task in non_critical_tasks:
    opt.add(starts[task.id] == hints[task.id])

# Otimizar 5% críticas
# (deixar livre)
```

**Meta**: 10s → ~3s (70% mais rápido)

### 3. Visualizações (BAIXA PRIORIDADE)

- Gantt colorido por slack (vermelho=crítico, verde=folga)
- Gráfico de utilização de máquinas

## 🐛 Problemas Conhecidos

### 1. Slack Calculation

**Observado**: Apenas 1 tarefa crítica em abz5 (parece baixo)

**Possível causa**: Erro no cálculo de Latest Start Time (LST)

**Como investigar**:
```haskell
-- Verificar algoritmo de backward pass
computeSlack tasks starts makespan
-- LST deve ser calculado partindo do makespan e seguindo backward
```

### 2. Z3 Non-Determinism

**Comportamento**: Às vezes 1234h, às vezes 1250h (~1% variação)

**Causa**: Heurísticas internas do Z3 não são determinísticas

**Solução**: Aceitável para prática. Para forçar determinismo:
```python
opt.set("random_seed", 42)
opt.set("smt.random_seed", 42)
```

### 3. Setup Time

**Estado atual**: Fixo em 0 para todos os jobs

**Melhoria futura**: Matriz de setup times por (job_i, job_j, machine)

## ⚙️ Configurações Importantes

### Haskell

**Stack** (stack.yaml):
```yaml
resolver: lts-22.28
packages:
- .
```

**Dependências** (package.yaml):
```yaml
dependencies:
- scotty              # Web framework
- algebraic-graphs    # Validação de ciclos
- aeson               # JSON
- containers          # Data structures
```

### Python

**Versão**: 3.11+

**Dependências**:
```bash
pip install z3-solver requests matplotlib
```

**Setup time** (em example_usage.py):
```python
SETUP_TIME = 0  # Comparação com literatura
```

## 📚 Referências Técnicas

### Papers e Livros

- **JSSP**: Garey & Johnson "Computers and Intractability" (1979)
- **Critical Path**: Kelley & Walker "CPM" (1959)
- **Local Search**: Aarts & Lenstra "Local Search in Combinatorial Optimization" (1997)
- **Z3**: Bjørner & Phan "νZ - Maximal Satisfaction with Z3" (2014)

### Benchmarks

- **OR-Library**: http://people.brunel.ac.uk/~mastjjb/jeb/orlib/jobshopinfo.html
- **Best Known Solutions**: http://jobshop.jjvh.nl/

## 🔍 Comandos Úteis para Debug

### Ver estado do servidor

```bash
curl -X POST http://localhost:3000/validate \
  -H "Content-Type: application/json" \
  -d '[{"id_t":1,"job_id":1,"machine_id":1,"duration":3,"next_t":2,"prev_t":null}]'
```

### Comparar heurística vs Z3

```bash
python script-python/solve_with_bottlenecks.py instances/AdamsBalasZawack1988/abz5.txt
```

### Testar Z3 isolado (sem hints)

```bash
python script-python/debug_z3.py
```

### Profile Haskell

```bash
stack build --profile
stack run --profile -- +RTS -p
cat haskell-engine-exe.prof
```

## 💡 Dicas de Desenvolvimento

### Ao modificar heurística:

1. Testar em ft06 primeiro (6×6, rápido)
2. Depois em abz5 (10×10, benchmark principal)
3. Comparar com best known: ft06=55h, abz5=1234h
4. Atualizar CHANGELOG.md

### Ao adicionar análise:

1. Adicionar campo em `ValidationResponse` (Types.hs)
2. Implementar função de análise (Main.hs)
3. Atualizar endpoint `/validate`
4. Criar script Python correspondente
5. Documentar em docs/

### Ao testar:

1. Sempre rodar `stack test` antes de commit
2. Testar em pelo menos 3 instâncias (ft06, la01, abz5)
3. Verificar se gap vs optimal não piorou
4. Atualizar tabela de resultados no README.md

## 🚀 Workflow de Commit

```bash
# 1. Build e test
stack build && stack test

# 2. Verificar mudanças
git status
git diff

# 3. Commit semântico
git add -A
git commit -m "tipo: descrição

- Detalhe 1
- Detalhe 2"

# Tipos: feat, fix, docs, refactor, perf, test

# 4. Push
git push origin main
```

## 📞 Contato

**Autor**: Jose Augusto M de Andrade Jr  
**Email**: jamaj@jamaj.com.br  
**Repositório**: https://github.com/jamaj69/projeto-yoneda-z3

---

## 🎬 Checklist Rápido ao Retomar

Ao voltar ao projeto após pausa:

- [ ] Ler CHANGELOG.md para ver última versão
- [ ] Verificar ROADMAP.md para próximos passos
- [ ] Rodar `stack build && stack run` (servidor na porta 3000)
- [ ] Testar com `python script-python/solve_with_bottlenecks.py instances/AdamsBalasZawack1988/abz5.txt`
- [ ] Verificar se resultado ainda é ~1451h (heurística) e ~1234h (Z3)
- [ ] Escolher feature do ROADMAP.md para implementar

**Status de testes esperado**:
- ft06: heurística ~69h, Z3 ~55-65h
- la01: heurística ~880h, Z3 ~684h  
- abz5: heurística ~1451h, Z3 ~1234-1250h

Se os resultados mudarem significativamente, algo regrediu! 🚨
