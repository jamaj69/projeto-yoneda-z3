# Instance Loader - Guia Completo

## 📚 Visão Geral

O `instance_loader.py` fornece funções para carregar e converter instâncias de Job Shop Scheduling Problem (JSSP) do formato padrão de benchmarks para o formato esperado pelo servidor Haskell.

## 🗂️ Formato de Arquivo JSSP

As instâncias seguem o formato padrão da literatura:

```
num_jobs num_machines
machine_1 duration_1 machine_2 duration_2 ... (Job 1)
machine_1 duration_1 machine_2 duration_2 ... (Job 2)
...
```

**Exemplo: ft06.txt**
```
6 6
2 1 0 3 1 6 3 7 5 3 4 6
1 8 2 5 4 10 5 10 0 10 3 4
...
```

- **Linha 1**: 6 jobs, 6 máquinas
- **Linha 2**: Job 1 → Máquina 2 (1h) → Máquina 0 (3h) → Máquina 1 (6h) → ...

## 🔧 Funções Principais

### 1. `parse_jssp_file(filepath)`

Lê arquivo .txt e retorna a estrutura do problema.

```python
from instance_loader import parse_jssp_file

num_jobs, num_machines, jobs = parse_jssp_file("instances/FisherThompson1963/ft06.txt")
# jobs[0] = [(2, 1), (0, 3), (1, 6), ...] # Job 1: (máquina, duração)
```

**Retorna:**
- `num_jobs`: Número de jobs
- `num_machines`: Número de máquinas
- `jobs`: Lista de listas com tuplas (machine_id, duration)

### 2. `jssp_to_tasks(jobs)`

Converte para formato TaskReq do Haskell.

```python
from instance_loader import jssp_to_tasks

tasks = jssp_to_tasks(jobs)
# tasks = [
#   {"id_t": 1, "job_id": 1, "machine_id": 2, "duration": 1, 
#    "next_t": 2, "prev_t": None},
#   ...
# ]
```

**Retorna:**
- Lista de dicionários com campos: `id_t`, `job_id`, `machine_id`, `duration`, `next_t`, `prev_t`

### 3. `load_instance(filepath)`

Função completa: lê + converte em uma única chamada.

```python
from instance_loader import load_instance

instance = load_instance("instances/Lawrence1984/la01.txt")

print(instance)
# {
#   "name": "la01",
#   "benchmark": "Lawrence1984",
#   "num_jobs": 10,
#   "num_machines": 5,
#   "tasks": [...]  # Pronto para enviar ao Haskell
# }
```

### 4. `list_all_instances(instances_dir)`

Lista todos os arquivos .txt recursivamente.

```python
from instance_loader import list_all_instances

all_files = list_all_instances("../instances")
print(f"Total de instâncias: {len(all_files)}")
# Total de instâncias: 242
```

### 5. `list_instances_by_benchmark(instances_dir)`

Agrupa instâncias por benchmark.

```python
from instance_loader import list_instances_by_benchmark

benchmarks = list_instances_by_benchmark("../instances")
for name, files in benchmarks.items():
    print(f"{name}: {len(files)} instâncias")

# FisherThompson1963: 3 instâncias
# Lawrence1984: 40 instâncias
# Taillard1993: 80 instâncias
# ...
```

## 🚀 Uso Completo: Haskell + Z3

### Exemplo Básico

```python
import requests
from instance_loader import load_instance

# 1. Carregar instância
instance = load_instance("instances/FisherThompson1963/ft06.txt")

# 2. Enviar para o Haskell
response = requests.post("http://localhost:3000/validate", 
                        json=instance['tasks'])
result = response.json()

print(f"Válido: {result['valid']}")
print(f"Makespan (heurística): {result['makespan_heuristic']}")
print(f"Hints: {result['hints']}")
```

### Exemplo com Z3 (Completo)

Use `example_usage.py`:

```bash
# Resolver instância específica
python script-python/example_usage.py instances/FisherThompson1963/ft06.txt

# Saída:
# ✅ Makespan Haskell (heurística): 162h
# ✅ Makespan Z3 (ótimo): 162h
# ✨ Heurística do Haskell já encontrou o ótimo!
```

## 📊 Benchmarks Disponíveis

| Benchmark | Instâncias | Dimensões | Dificuldade |
|-----------|------------|-----------|-------------|
| **FisherThompson1963** | 3 | 6×6, 10×10, 20×5 | Clássicas (fácil) |
| **Lawrence1984** | 40 | 10-30 jobs, 5-15 máquinas | Média |
| **Taillard1993** | 80 | 15-100 jobs | Difícil |
| **AdamsBalasZawack1988** | 5 | 10×10, 20×15 | Desafiador |
| **ApplegateCook1991** | 10 | 10×10 | Média |
| **DemirkolMehtaUzsoy1998** | 80 | Variado | Média-Difícil |
| **StorerWuVaccari1992** | 20 | Variado | Média |
| **YamadaNakano1992** | 4 | 20×20 | Difícil |

### Recomendações por Tamanho

- **Teste rápido**: FisherThompson (`ft06`, `ft10`)
- **Desenvolvimento**: Lawrence (`la01` - `la10`)
- **Benchmark padrão**: Lawrence (`la21` - `la40`)
- **Teste de estresse**: Taillard (`ta41` - `ta80`)

## 🧪 Testes e Debugging

### Testar o Loader

```bash
cd script-python
python instance_loader.py
```

**Saída:**
```
📁 Benchmarks disponíveis: 8
  • FisherThompson1963: 3 instâncias
  • Lawrence1984: 40 instâncias
  ...
  
Instância: ft06 (FisherThompson1963)
Dimensões: 6 jobs × 6 máquinas
Total de tarefas: 36
```

### Debug de Instância Específica

```python
from instance_loader import load_instance, print_instance_summary

instance = load_instance("instances/Lawrence1984/la01.txt")
print_instance_summary(instance)
```

## ⚡ Performance

| Operação | Tempo | Descrição |
|----------|-------|-----------|
| `parse_jssp_file()` | <1ms | Parse de arquivo .txt |
| `jssp_to_tasks()` | <1ms | Conversão para TaskReq |
| `list_all_instances()` | ~50ms | Busca recursiva (242 arquivos) |
| Haskell validation (ft06) | ~100ms | 36 tarefas |
| Z3 optimization (ft06) | 1-5s | 36 variáveis |

## 🐛 Troubleshooting

### Erro: "Servidor Haskell não responde"

```bash
# Em um terminal, iniciar o servidor:
cd /home/jamaj/src/projeto-yoneda-z3
stack run
```

### Erro: "FileNotFoundError"

Verifique o caminho relativo. De dentro de `script-python/`:

```python
# ✅ Correto
load_instance("../instances/FisherThompson1963/ft06.txt")

# ❌ Errado
load_instance("instances/FisherThompson1963/ft06.txt")
```

### Erro: "Z3 timeout"

Instâncias muito grandes podem demorar. Use timeout maior:

```python
response = requests.post("http://localhost:3000/validate", 
                        json=tasks, 
                        timeout=120)  # 2 minutos
```

## 📖 Referências

- **Formato JSSP**: http://jobshop.jjvh.nl/
- **Benchmarks OR-Library**: http://people.brunel.ac.uk/~mastjjb/jeb/info.html
- **Taillard Instances**: http://mistic.heig-vd.ch/taillard/problemes.dir/ordonnancement.dir/ordonnancement.html

## 🎯 Próximos Passos

1. **Adicionar cache**: Evitar re-parse de instâncias grandes
2. **Suporte JSON**: Carregar instâncias pré-processadas (.json)
3. **Validação**: Verificar consistência dos dados
4. **Estatísticas**: Calcular bounds inferiores conhecidos
