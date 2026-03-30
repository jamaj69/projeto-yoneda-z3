# Projeto Yoneda-Z3: Otimizador Híbrido de Job Shop Scheduling

## 📋 Descrição

Sistema híbrido de otimização para **Job Shop Scheduling Problem (JSSP)** que combina:

1. **Haskell (servidor REST)**: Pipeline de 3 fases — MWR+SPT, Shifting Bottleneck, Yoneda-fused neighborhoods (N2/N5/N7)
2. **Python + Z3/OR-Tools**: Solvers exatos para soluções ótimas globais

O Haskell fornece soluções heurísticas de alta qualidade (0-21% do ótimo) em milissegundos a segundos, enquanto os solvers exatos buscam o ótimo global.

### 🎯 Resultados (v0.4.0)

| Instância | Dimensão | MWR+SPT | SBP | Refinado | Best Known | Gap |
| --------- | -------- | ------- | --- | -------- | ---------- | --- |
| **la01** | 10×5 | 880 | 666 | **666** | 666 | **0.0% OPT** |
| **ft06** | 6×6 | 69 | 60 | **60** | 55 | +9.1% |
| **abz5** | 10×10 | 1451 | 1334 | **1312** | 1234 | +6.3% |
| **abz9** | 10×10 | 1132 | 849 | **801** | 661 | +21.2% |
| **dmu10** | 20×20 | 4765 | 4143 | **3621** | n/a | — |
| **ta71** | 100×20 | 8010 | 5930 | **5886** | 5464 | +7.7% |

💡 **Destaques**:

- **la01 ótimo** encontrado pela heurística pura (sem solver!)
- Pipeline de 3 fases proporciona reduções compostas: MWR→SBP→N2/N5/N7
- Instâncias de 2000 tarefas (100×20) resolvidas em ~24s

## 🏗️ Arquitetura

```text
┌─────────────────────────────────────────────────────────────┐
│  Python (script-python/)                                   │
│  • Define problema JSSP                                    │
│  • Requisita solução ao Haskell                           │
│  • Opcionalmente: Z3 ou OR-Tools para ótimo exato         │
└───────────────────┬─────────────────────────────────────────┘
                    │ POST /validate
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  Haskell Server (app-haskell/Main.hs) - Porta 3000        │
│                                                            │
│  Phase 1a: MWR+SPT (list scheduling com priorização)      │
│       ↓                                                    │
│  Phase 1b: Shifting Bottleneck (Schrage + Carlier)        │
│       ↓  (best of 1a/1b seeds Phase 2)                    │
│  Phase 2: Yoneda-fused N2/N5/N7 neighborhoods             │
│       ↓  (greedySweep + refinementPipeline)               │
│  Phase 3: Bottleneck analysis (slack, critical path)      │
│                                                            │
│  Retorna: hints, makespan_heuristic, makespan_sbp,        │
│           makespan_refined, slacks, critical_path,         │
│           critical_machines, machine_utilization           │
└─────────────────────────────────────────────────────────────┘
```

## 🧠 Técnicas Implementadas

### Phase 1a: MWR+SPT (Haskell)

**Most Work Remaining (MWR)** + **Shortest Processing Time (SPT)** list scheduling:

- Calcula trabalho total restante para cada job
- Prioriza jobs com mais operações pendentes (MWR)
- Desempate por duração da tarefa (SPT)
- Performance: O(n² log n) — processa 100 tarefas em ~5ms

### Phase 1b: Shifting Bottleneck Procedure (SBP)

Implementação de Adams, Balas & Zawack (1988):

- **Schrage heuristic** para subproblemas `1|r_j|max(C_j+q_j)`, O(n log n)
- **Carlier B&B** com budget de nós (budget=0 na prática — Schrage já é ótimo por subproblema)
- Decomposição iterativa: pick bottleneck machine → fix ordering → re-optimize scheduled machines
- Resultados: SBP é consistentemente melhor que MWR+SPT (ex: abz5: 1451→1334)

### Phase 2: Yoneda-Fused Neighborhoods

Pipeline de refinamento local usando o **Yoneda lemma** para fusão de fmap:

```haskell
newtype Yoneda f a = Yoneda { runYoneda :: forall b. (a -> b) -> f b }
-- Cada fmap é O(1), composição na continuação. lowerYoneda aplica tudo em uma passagem.
```

**Três vizinhanças** aplicadas em sequência (N2 → N5 → N7):

| Neighborhood | Técnica | Referência |
| ------------ | ------- | ---------- |
| **N2** | Swap de tarefas adjacentes no caminho crítico | Nowicki & Smutnicki 1996 |
| **N5** | Rotação de endpoints de blocos críticos | van Laarhoven et al. 1992 |
| **N7** | Reinserção de tarefas críticas em todas as posições | Dell'Amico & Trubian 1993 |

- **`greedySweep`**: carry-forward via `foldl'` que permite cadeias dependentes de swaps
- **`refinementPipeline`**: left-fold `[(budget, Neighborhood)]` — cada neighborhood converge antes da próxima
- **Adaptive strategy**: `firstImprovementSel` para n>500 tarefas, `steepestDescent` para menores

### Phase 3: Análise de Gargalos

- **Forward/backward pass** no grafo disjuntivo para EST/LST preciso
- **Slack** = LST - EST (zero = caminho crítico)
- **Utilização de máquinas**: `workload / makespan` por máquina
- Dados retornados na resposta JSON para uso por solvers externos

### Solvers Exatos (Python)

| Solver | Script | Uso |
| ------ | ------ | --- |
| **Z3** (SMT) | `example_usage.py` | Ótimo para instâncias ≤200 tarefas |
| **OR-Tools CP-SAT** | `solve_ortools.py` | Melhor para instâncias maiores, portfolio solver |

### Quando Usar Cada Modo

| Critério | Heurística Haskell | Solver Exato |
| -------- | ------------------ | ------------ |
| **Velocidade** | ⚡ ms a ~24s | ⏱️ Segundos a minutos |
| **Qualidade** | 📊 0-21% do ótimo | 🎯 Ótimo global |
| **Tamanho** | 📦 Até 2000+ tarefas | 📏 Até ~400 tarefas (60s) |

📖 **Documentação detalhada**: [HEURISTIC_IMPROVEMENTS.md](docs/HEURISTIC_IMPROVEMENTS.md)

## 🚀 Instalação

### Pré-requisitos

- **Haskell Stack** ([instalação](https://docs.haskellstack.org/en/stable/install_and_upgrade/))
- **Python 3.11+**
- **Poetry** (opcional) ou `pip`

### Setup

```bash
# 1. Clone o repositório
git clone <repo-url>
cd projeto-yoneda-z3

# 2. Instalar dependências Haskell
stack build

# 3. Instalar dependências Python
pip install z3-solver requests matplotlib
# ou com poetry:
poetry install
```

## ▶️ Execução

### 1. Iniciar o servidor Haskell

```bash
stack run
```

O servidor estará disponível em `http://localhost:3000`.

### 2. Executar o otimizador Python

Em outro terminal:

```bash
python script-python/main.py
```

### Saída Esperada

```text
--- Consultando Pré-Otimizador Haskell ---
MAKESPAN HASKELL (Heurística + Setup): 23h
MAKESPAN Z3 (Ótimo Global): 21h
Sucesso: O Z3 melhorou a heurística em 2h!
[Gráfico de Gantt é exibido]
```

## 📊 Instâncias de Benchmark

O projeto inclui **242 instâncias clássicas** de JSSP de 8 benchmarks reconhecidos:

| Benchmark | Instâncias | Descrição |
| --------- | ---------- | --------- |
| **FisherThompson1963** | 3 | Instâncias clássicas 6×6, 10×10, 20×5 |
| **Lawrence1984** | 40 | Problemas la01-la40 (10-30 jobs, 5-15 máquinas) |
| **Taillard1993** | 80 | Instâncias difíceis ta01-ta80 (15-100 jobs) |
| **AdamsBalasZawack1988** | 5 | Problemas desafiadores |
| **ApplegateCook1991** | 10 | Benchmarks da década de 90 |
| **DemirkolMehtaUzsoy1998** | 80 | Problemas de escala variada |
| **StorerWuVaccari1992** | 20 | Instâncias para comparação |
| **YamadaNakano1992** | 4 | Benchmarks japoneses |

### 🔧 Carregando Instâncias

```python
from script-python.instance_loader import load_instance

# Carregar instância específica
instance = load_instance("instances/FisherThompson1963/ft06.txt")
print(f"Jobs: {instance['num_jobs']}, Máquinas: {instance['num_machines']}")

# As tarefas já estão no formato TaskReq para o Haskell
tasks = instance['tasks']
```

### 🚀 Resolvendo Instâncias

```bash
# Resolver instância específica
python script-python/example_usage.py instances/FisherThompson1963/ft06.txt

# Ou usar o problema exemplo em main.py
python script-python/main.py
```

## 🧪 Testes

```bash
# Executar testes Haskell
stack test

# Executar servidor Haskell em modo verboso
stack exec -- haskell-engine-exe --verbose
```

## 📝 Endpoints da API Haskell

### `POST /validate`

**Entrada**:

```json
[
  {
    "id_t": 1,
    "job_id": 1,
    "machine_id": 1,
    "duration": 3,
    "next_t": 2,
    "prev_t": null
  },
  ...
]
```

**Saída** (válido):

```json
{
  "status": "ok",
  "valid": true,
  "hints": {"1": 0, "2": 3, ...},
  "makespan_heuristic": 880,
  "makespan_sbp": 666,
  "makespan_refined": 666,
  "refined_starts": {"1": 0, "2": 3, ...},
  "slacks": {"1": 0, "2": 50, ...},
  "critical_path": [1, 5, 12, ...],
  "critical_machines": [3, 7],
  "machine_utilization": {"0": 0.85, "1": 0.72, ...}
}
```

**Saída** (ciclo detectado):

```json
{
  "status": "erro",
  "valid": false,
  "msg": "Ciclo detectado!"
}
```

## 🔬 Tecnologias

| Componente | Tecnologia | Propósito |
| ---------- | ---------- | --------- |
| Pré-otimizador | Haskell + Scotty + algebraic-graphs | Servidor REST com heurística gulosa |
| Otimizador | Python + Z3 | SMT solver para otimização exata |
| Visualização | Matplotlib | Gráficos de Gantt comparativos |

## 📦 Estrutura do Projeto

```text
.
├── app-haskell/
│   └── src/Main.hs          # Servidor + pipeline completo (MWR→SBP→N2/N5/N7)
├── script-python/
│   ├── main.py              # Exemplo básico (4×3)
│   ├── instance_loader.py   # Parser de 242 benchmarks clássicos
│   ├── example_usage.py     # Integração Haskell + Z3
│   ├── solve_ortools.py     # Solver OR-Tools CP-SAT
│   ├── solve_with_bottlenecks.py  # Análise de gargalos
│   ├── validate_solution.py # Validação de soluções
│   ├── verify_ortools.py    # Verificação de soluções OR-Tools
│   ├── learn_from_z3.py     # Análise comparativa heurística vs Z3
│   └── debug_z3.py          # Debug de comportamento Z3
├── instances/               # 242 instâncias de 8 benchmarks clássicos
│   ├── FisherThompson1963/
│   ├── Lawrence1984/
│   ├── Taillard1993/
│   └── ...
├── src/
│   ├── Types.hs             # Tipos da aplicação Haskell
│   ├── Run.hs               # Lógica de execução
│   └── Util.hs              # Utilitários
├── test/
│   └── UtilSpec.hs          # Testes unitários
├── package.yaml             # Configuração Haskell (Stack)
├── pyproject.toml           # Dependências Python
└── README.md
```

## 📚 Documentação Técnica

### Guias e Análises

1. **[HEURISTIC_IMPROVEMENTS.md](docs/HEURISTIC_IMPROVEMENTS.md)** - Evolução da heurística Haskell
   - Comparação toposort vs MWR+SPT vs SBP vs N2/N5/N7
   - Análise de resultados por versão

2. **[BOTTLENECK_ANALYSIS.md](docs/BOTTLENECK_ANALYSIS.md)** - Análise de gargalos e caminho crítico
   - Cálculo de slack via forward/backward pass
   - Identificação de tarefas críticas e máquinas gargalo

3. **[INSTANCE_LOADER.md](docs/INSTANCE_LOADER.md)** - Como carregar e usar os 242 benchmarks

4. **[WHY_NOT_OPTIMAL.md](docs/WHY_NOT_OPTIMAL.md)** - Z3 non-determinism e variação de resultados

5. **[FEEDBACK_LEARNING.md](docs/FEEDBACK_LEARNING.md)** - Sistema de aprendizado por feedback (Haskell ↔ Z3)

## 📚 Referências

- **Job Shop Scheduling Problem**: Problema NP-difícil de escalonamento de tarefas
- **Z3 Theorem Prover**: [Microsoft Research Z3](https://github.com/Z3Prover/z3)
- **Algebraic Graphs**: [Biblioteca Haskell](https://hackage.haskell.org/package/algebraic-graphs)

## 👤 Autor

**Jose Augusto M de Andrade Jr**  
📧 <jamaj@jamaj.com.br>  
📅 2026

## 📄 Licença

BSD-3-Clause
