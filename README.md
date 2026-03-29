# Projeto Yoneda-Z3: Otimizador Híbrido de Job Shop Scheduling

## 📋 Descrição

Sistema híbrido de otimização para **Job Shop Scheduling Problem (JSSP)** que combina:

1. **Pré-otimizador Haskell**: Heurística gulosa com validação de grafos e ordenação topológica
2. **Otimizador Z3**: Provador de teoremas SMT para encontrar a solução ótima global

O Haskell fornece hints (sugestões de tempo inicial) que o Z3 utiliza como ponto de partida para acelerar a convergência, combinando eficiência heurística com garantia de otimalidade.

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  Python (script-python/main.py)                            │
│  • Define problema JSSP                                    │
│  • Requisita validação + hints ao Haskell                 │
└───────────────────┬─────────────────────────────────────────┘
                    │ POST /validate
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  Haskell Server (app-haskell/Main.hs) - Porta 3000        │
│  • Valida grafos (detecta ciclos)                         │
│  • Ordenação topológica                                   │
│  • Heurística gulosa com setup time                       │
│  • Retorna hints de scheduling                            │
└───────────────────┬─────────────────────────────────────────┘
                    │ {hints, makespan_heuristic}
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  Z3 Solver (script-python/main.py)                         │
│  • Aplica hints como soft constraints                      │
│  • Restrições de precedência e setup time                 │
│  • Minimiza makespan globalmente                          │
│  • Gera gráfico de Gantt comparativo                      │
└─────────────────────────────────────────────────────────────┘
```

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

```
--- Consultando Pré-Otimizador Haskell ---
MAKESPAN HASKELL (Heurística + Setup): 23h
MAKESPAN Z3 (Ótimo Global): 21h
Sucesso: O Z3 melhorou a heurística em 2h!
[Gráfico de Gantt é exibido]
```

## 📊 Exemplo de Problema

O problema padrão em `main.py` é um **JSSP 4×3** (4 jobs, 3 máquinas):

- **Setup Time**: 2 horas entre jobs diferentes na mesma máquina
- **Restrições**: Precedência de tarefas dentro de cada job
- **Objetivo**: Minimizar o makespan (tempo total de conclusão)

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
  "makespan_heuristic": 23
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
|------------|-----------|-----------|
| Pré-otimizador | Haskell + Scotty + algebraic-graphs | Servidor REST com heurística gulosa |
| Otimizador | Python + Z3 | SMT solver para otimização exata |
| Visualização | Matplotlib | Gráficos de Gantt comparativos |

## 📦 Estrutura do Projeto

```
.
├── app-haskell/
│   └── src/Main.hs          # Servidor web Haskell + heurística
├── script-python/
│   └── main.py              # Cliente Python + Z3 solver
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

## 📚 Referências

- **Job Shop Scheduling Problem**: Problema NP-difícil de escalonamento de tarefas
- **Z3 Theorem Prover**: [Microsoft Research Z3](https://github.com/Z3Prover/z3)
- **Algebraic Graphs**: [Biblioteca Haskell](https://hackage.haskell.org/package/algebraic-graphs)

## 👤 Autor

**Jose Augusto M de Andrade Jr**  
📧 jamaj@jamaj.com.br  
📅 2026

## 📄 Licença

BSD-3-Clause
