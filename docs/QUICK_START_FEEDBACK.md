# 🧠 Sistema de Aprendizado por Feedback

## 📖 Guia Rápido de Teste

### Pré-requisitos

```bash
# Terminal 1: Iniciar servidor Haskell
cd /home/jamaj/src/projeto-yoneda-z3
stack run

# Terminal 2: Ativar ambiente Python
source /home/python/pyenv/bin/activate
cd /home/jamaj/src/projeto-yoneda-z3
```

### Teste 1: Instância Pequena (ft06 - 6×6)

```bash
python script-python/learn_from_z3.py instances/FisherThompson1963/ft06.txt
```

**Resultado esperado** (~5 segundos):

```
🔬 SISTEMA DE APRENDIZADO POR FEEDBACK
======================================================================
Instância: instances/FisherThompson1963/ft06.txt

📋 ft06 (FisherThompson1963)
   6 jobs × 6 máquinas = 36 tarefas

🔍 Consultando Haskell (heurística MWR+SPT)...
✅ Makespan heurística: 69h

🧮 Resolvendo com Z3...
✅ Makespan Z3 (ótimo): 55h (tempo: 2.34s)
🎉 Z3 melhorou em 14h (20.3%)

📤 Enviando feedback para Haskell aprender...
⚠️  Endpoint /learn ainda não implementado no Haskell.
📖 Leia docs/FEEDBACK_LEARNING.md para implementar.

🔍 Executando análise manual (Python-side) enquanto /learn não existe...

======================================================================
📊 ANÁLISE COMPARATIVA (versão simplificada)
======================================================================

🎯 Desempenho:
   Heurística: 69h
   Ótimo (Z3): 55h
   Gap: 14h (25.5%)

🔄 Máquinas com Ordenação Diferente:
   Máquina 1:
      Heurística: [1, 8, 15, 22, 29, 36]
      Ótimo:      [1, 15, 8, 22, 29, 36]
      ⚠️  2 swaps necessários
   Máquina 3:
      Heurística: [3, 10, 17, 24, 31]
      Ótimo:      [10, 3, 17, 24, 31]
      ⚠️  1 swaps necessários

💡 Sugestões de Ajuste:
   • Muitas trocas de ordem detectadas. Priorize tarefas mais curtas.
     Tipo: IncreaseSPTWeight (+30%)

======================================================================
📝 Para implementar análise completa no Haskell:
   1. Leia docs/FEEDBACK_LEARNING.md
   2. Implemente endpoint /learn em Main.hs
   3. Execute novamente este script
======================================================================
```

### Teste 2: Instância Média (la01 - 10×5)

```bash
python script-python/learn_from_z3.py instances/Lawrence1984/la01.txt
```

**Resultado esperado** (~8 segundos):

```
🎯 Desempenho:
   Heurística: 880h
   Ótimo (Z3): 684h
   Gap: 196h (28.7%)

🔄 Máquinas com Ordenação Diferente:
   [... análise de 5 máquinas ...]

💡 Sugestões de Ajuste:
   • Gap muito grande. Foque mais em jobs com trabalho restante.
     Tipo: IncreaseMWRWeight (+20%)
```

### Teste 3: Instância Grande (abz5 - 10×10)

```bash
python script-python/learn_from_z3.py instances/AdamsBalasZawack1988/abz5.txt
```

**Resultado esperado** (~15 segundos):

```
🎯 Desempenho:
   Heurística: 1451h
   Ótimo (Z3): 1234h
   Gap: 217h (17.6%)

🔄 Máquinas com Ordenação Diferente:
   [... 4-6 máquinas com diferenças ...]

💡 Sugestões de Ajuste:
   • Muitas trocas detectadas. Priorize tarefas mais curtas.
     Tipo: IncreaseSPTWeight (+30%)
   • Gap muito grande. Foque mais em jobs com trabalho restante.
     Tipo: IncreaseMWRWeight (+20%)
```

---

## 🛠️ Implementação do Endpoint `/learn` (próximo passo)

### 1. Adicionar tipos em `src/Types.hs`

Copiar tipos de `docs/FeedbackTypes.hs` para `src/Types.hs`:

```haskell
-- Adicionar ao final de Types.hs
data OptimalSolution = OptimalSolution { ... }
data LearnRequest = LearnRequest { ... }
data LearningInsights = LearningInsights { ... }
-- ... etc (ver docs/FeedbackTypes.hs)
```

### 2. Implementar funções de análise em `app-haskell/src/Main.hs`

```haskell
-- Comparar ordenação em máquinas
compareTaskOrdering :: [TaskReq] -> Map Int Int -> Map Int Int -> [MachineComparison]
compareTaskOrdering tasks hStarts oStarts = ...

-- Analisar prioridades
analyzeTaskPriorities :: [TaskReq] -> Map Int Int -> Map Int Int -> [TaskPriority]
analyzeTaskPriorities tasks hStarts oStarts = ...

-- Avaliar detecção de gargalos
evaluateBottleneckDetection :: ... -> BottleneckAccuracy
evaluateBottleneckDetection tasks hStarts oStarts hUtil = ...

-- Gerar sugestões
generateHeuristicAdjustments :: LearningInsights -> [HeuristicAdjustment]
generateHeuristicAdjustments insights = ...
```

### 3. Adicionar endpoint em `main`

```haskell
main :: IO ()
main = scotty 3000 $ do
    post "/validate" $ do
        -- ... código existente ...
    
    -- NOVO
    post "/learn" $ do
        req <- jsonData :: ActionM LearnRequest
        let optSol = optimal_solution req
            tasks' = tasks req
        
        -- Recalcula heurística
        let (hStarts, hMakespan, slacks, critPath) = solveWithRefinement tasks'
            machineUtil = analyzeMachineUtilization tasks' hStarts hMakespan
        
        -- Compara com ótimo
        let oStarts = optimal_starts optSol
            oMakespan = optimal_makespan optSol
            
            gap = hMakespan - oMakespan
            gapPct = (fromIntegral gap / fromIntegral oMakespan) * 100.0
            
            machineComps = compareTaskOrdering tasks' hStarts oStarts
            priorityIssues = analyzeTaskPriorities tasks' hStarts oStarts
            bottleneckAcc = evaluateBottleneckDetection tasks' hStarts oStarts machineUtil
            
            insights = LearningInsights hMakespan oMakespan gap gapPct
                                       machineComps priorityIssues bottleneckAcc []
            
            adjustments = generateHeuristicAdjustments insights
            finalInsights = insights { heuristic_adjustments = adjustments }
        
        json $ object [ "status" .= ("ok" :: String)
                      , "learned" .= True
                      , "insights" .= finalInsights
                      ]
```

### 4. Testar novamente

```bash
stack build
stack run  # reiniciar servidor

# Em outro terminal
python script-python/learn_from_z3.py instances/FisherThompson1963/ft06.txt
```

Agora você deverá ver o relatório completo gerado pelo Haskell! 🎉

---

## 📚 Documentação

- **Guia Completo**: [FEEDBACK_LEARNING.md](FEEDBACK_LEARNING.md)
- **Tipos de Dados**: [FeedbackTypes.hs](FeedbackTypes.hs)
- **Roadmap**: [ROADMAP.md](../ROADMAP.md#sistema-de-aprendizado-por-feedback)
- **Changelog**: [CHANGELOG.md](../CHANGELOG.md#unreleased)

---

## 🎓 Conceitos do Sistema

### O que o sistema aprende?

1. **Ordenação de Tarefas em Máquinas**
   - Compara sequência heurística vs ótima
   - Identifica swaps necessários
   - Infere qual critério (MWR ou SPT) deveria ter mais peso

2. **Detecção de Gargalos**
   - Compara máquinas marcadas como críticas
   - Calcula accuracy (TP, FP, FN)
   - Ajusta threshold de detecção

3. **Priorização de Tarefas**
   - Compara prioridade calculada vs implícita no ótimo
   - Identifica tarefas sub/super-priorizadas
   - Ajusta pesos relativos (MWR, SPT, critical path)

### Como o Haskell melhora?

**Fase 1 (v0.4.0)**: Análise e relatório
- Mostra diferenças
- Sugere ajustes
- **Manual**: Desenvolvedor ajusta código

**Fase 2 (v0.5.0)**: Aprendizado automático
- Salva histórico em `learning_history.json`
- Aplica pesos ajustados na próxima execução
- Evolui progressivamente com cada instância

**Fase 3 (v0.6.0)**: Meta-aprendizado
- Clusteriza tipos de instância
- Aplica heurística diferente por cluster
- Aprende quando usar cada estratégia

---

## 🚀 Roadmap de Implementação

- [x] **Fase 0**: Protótipo Python-side (análise manual)
- [ ] **Fase 1**: Endpoint `/learn` no Haskell
- [ ] **Fase 2**: Persistência de pesos (JSON)
- [ ] **Fase 3**: Aplicação automática de pesos
- [ ] **Fase 4**: Meta-aprendizado

**Status atual**: Fase 0 completa ✅  
**Próximo passo**: Implementar Fase 1 (endpoint `/learn`)  
**Tempo estimado**: 2-3 dias
