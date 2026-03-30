# Sistema de Aprendizado por Feedback - Haskell ↔ Z3

## 🎯 Objetivo

Permitir que o **servidor Haskell aprenda** com as diferenças entre:
- **Sua solução heurística** (MWR+SPT)
- **Solução ótima do Z3**

Para melhorar progressivamente:
1. **Detecção de gargalos**: Quais máquinas realmente limitam o makespan
2. **Ordenação de tarefas**: Qual a melhor permutação em cada máquina
3. **Pesos da heurística**: Ajustar MWR vs SPT dinamicamente

---

## 🏗️ Arquitetura

### Fluxo Atual (v0.3.0)

```
┌──────────┐  POST /validate   ┌──────────┐
│  Python  │ ──────────────→   │ Haskell  │
│          │                   │          │
│          │  ← heuristica     │ MWR+SPT  │
│          │    (makespan)     │          │
└────┬─────┘                   └──────────┘
     │
     ↓ Resolve com Z3
     │ (ótimo global)
     │
     ✅ Fim (sem feedback)
```

### Fluxo Proposto (v0.4.0+)

```
┌──────────┐  POST /validate   ┌──────────┐
│  Python  │ ──────────────→   │ Haskell  │
│          │                   │          │
│          │  ← heuristica     │ MWR+SPT  │
│    Z3    │    (makespan)     │          │
│          │                   │          │
│          │  POST /learn      │          │
│  Ótimo!  │ ──────────────→   │ Compara  │
│ (1234h)  │   z3_solution     │  1451h   │
│          │                   │  vs      │
│          │                   │  1234h   │
└──────────┘                   └────┬─────┘
                                    │
                                    ↓
                              📚 Aprende:
                              • Máquinas críticas
                              • Ordenação correta
                              • Ajusta heurística
```

---

## 📋 Tipos de Dados (Types.hs)

### 1. Solução do Z3 (entrada do `/learn`)

```haskell
-- Solução ótima retornada pelo Z3
data OptimalSolution = OptimalSolution
    { optimal_starts :: Map.Map Int Int  -- id_tarefa -> tempo_inicio
    , optimal_makespan :: Int
    , z3_solver_time :: Double  -- tempo de otimização (segundos)
    } deriving (Show, Generic)

instance FromJSON OptimalSolution
instance ToJSON OptimalSolution
```

### 2. Análise de Diferenças (saída do `/learn`)

```haskell
-- Análise comparativa entre heurística e ótimo
data LearningInsights = LearningInsights
    { heuristic_makespan :: Int
    , optimal_makespan :: Int
    , gap_hours :: Int                           -- diferença em horas
    , gap_percentage :: Double                    -- diferença percentual
    
    -- Máquinas onde o ordenamento diferiu
    , mismatched_machines :: [MachineComparison]
    
    -- Tarefas que deveriam ter sido priorizadas
    , should_prioritize :: [TaskPriority]
    
    -- Gargalos detectados corretamente vs incorretamente
    , bottleneck_accuracy :: BottleneckAccuracy
    
    -- Sugestões de ajuste de heurística
    , heuristic_adjustments :: [HeuristicAdjustment]
    } deriving (Show, Generic)

-- Comparação de ordenação em uma máquina
data MachineComparison = MachineComparison
    { machine_id :: Int
    , heuristic_order :: [Int]  -- ordem das tarefas na heurística
    , optimal_order :: [Int]    -- ordem na solução ótima
    , swap_pairs :: [(Int, Int)]  -- pares que deveriam ter sido trocados
    , impact_hours :: Int       -- impacto desta diferença no makespan
    } deriving (Show, Generic)

-- Tarefa que deveria ter recebido prioridade diferente
data TaskPriority = TaskPriority
    { task_id :: Int
    , heuristic_priority :: Double  -- prioridade calculada (MWR+SPT)
    , optimal_priority :: Double    -- prioridade inferida do ótimo
    , should_increase :: Bool       -- deve aumentar (True) ou reduzir?
    } deriving (Show, Generic)

-- Precisão da detecção de gargalos
data BottleneckAccuracy = BottleneckAccuracy
    { correctly_identified :: [Int]    -- máquinas corretamente marcadas
    , false_positives :: [Int]          -- marcadas mas não eram gargalo
    , false_negatives :: [Int]          -- eram gargalo mas não detectadas
    , accuracy_score :: Double          -- % de acerto (0.0-1.0)
    } deriving (Show, Generic)

-- Sugestão de ajuste na heurística
data HeuristicAdjustment = HeuristicAdjustment
    { adjustment_type :: AdjustmentType
    , description :: String
    , weight_change :: Double  -- quanto mudar o peso (+/-)
    } deriving (Show, Generic)

data AdjustmentType 
    = IncreaseMWRWeight      -- aumentar peso do Most Work Remaining
    | IncreaseSPTWeight      -- aumentar peso do Shortest Processing Time
    | PrioritizeCriticalPath -- focar mais no caminho crítico
    | BalanceLoadBetter      -- melhorar balanceamento
    deriving (Show, Generic, Eq)

instance FromJSON LearningInsights
instance ToJSON LearningInsights
instance FromJSON MachineComparison
instance ToJSON MachineComparison
instance FromJSON TaskPriority
instance ToJSON TaskPriority
instance FromJSON BottleneckAccuracy
instance ToJSON BottleneckAccuracy
instance FromJSON HeuristicAdjustment
instance ToJSON HeuristicAdjustment
instance FromJSON AdjustmentType
instance ToJSON AdjustmentType
```

---

## 🧠 Algoritmos de Análise (Main.hs)

### 1. Comparar Ordenação em Máquinas

```haskell
-- Compara ordem de execução das tarefas em cada máquina
compareTaskOrdering :: [TaskReq] 
                    -> Map.Map Int Int  -- heuristic starts
                    -> Map.Map Int Int  -- optimal starts
                    -> [MachineComparison]
compareTaskOrdering tasks hStarts oStarts =
    let -- Agrupa tarefas por máquina
        machineGroups = Map.fromListWith (++) 
            [(machine_id t, [t]) | t <- tasks]
        
        -- Para cada máquina, compara ordenação
        compareMachine mId mTasks =
            let -- Ordena por tempo de início (heurística)
                hOrder = List.sortBy (comparing (\t -> Map.findWithDefault 0 (id_t t) hStarts)) mTasks
                hIds = map id_t hOrder
                
                -- Ordena por tempo de início (ótimo)
                oOrder = List.sortBy (comparing (\t -> Map.findWithDefault 0 (id_t t) oStarts)) mTasks
                oIds = map id_t oOrder
                
                -- Identifica pares que deveriam ter sido trocados
                swaps = findSwapPairs hIds oIds
                
                -- Estima impacto (diferença de makespans ponderada)
                impact = estimateImpact swaps mTasks hStarts oStarts
                
            in MachineComparison mId hIds oIds swaps impact
        
    in Map.elems $ Map.mapWithKey compareMachine machineGroups

-- Identifica pares de tarefas que estão em ordem diferente
findSwapPairs :: [Int] -> [Int] -> [(Int, Int)]
findSwapPairs hOrder oOrder =
    let hPos = Map.fromList $ zip hOrder [0..]
        oPos = Map.fromList $ zip oOrder [0..]
        
        -- Para cada par (i, j) onde i < j em heurística
        pairs = [(i, j) | i <- hOrder, j <- hOrder, 
                 Map.findWithDefault 0 i hPos < Map.findWithDefault 0 j hPos]
        
        -- Filtra apenas os que estão invertidos no ótimo
        swaps = [(i, j) | (i, j) <- pairs,
                 let oI = Map.findWithDefault 0 i oPos
                     oJ = Map.findWithDefault 0 j oPos
                 in oI > oJ]  -- invertidos!
        
    in swaps

-- Estima quanto cada swap custou em termos de makespan
estimateImpact :: [(Int, Int)] -> [TaskReq] 
               -> Map.Map Int Int -> Map.Map Int Int -> Int
estimateImpact swaps tasks hStarts oStarts =
    -- Implementação simplificada: conta diferença de makespan
    -- proporcional ao número de swaps
    let totalDiff = abs (maximum (Map.elems hStarts) - maximum (Map.elems oStarts))
        numSwaps = length swaps
    in if numSwaps > 0 then totalDiff `div` numSwaps else 0
```

### 2. Analisar Prioridades Incorretas

```haskell
-- Identifica tarefas que deveriam ter recebido prioridade diferente
analyzeTaskPriorities :: [TaskReq]
                      -> Map.Map Int Int  -- heuristic starts
                      -> Map.Map Int Int  -- optimal starts
                      -> [TaskPriority]
analyzeTaskPriorities tasks hStarts oStarts =
    let taskLookup = Map.fromList [(id_t t, t) | t <- tasks]
        workRemaining = Map.unions [remainingWork tasks j | j <- List.nub [job_id t | t <- tasks]]
        
        -- Para cada tarefa, calcula prioridade da heurística
        hPriorities = Map.fromList
            [(id_t t, computeHeuristicPriority t workRemaining) | t <- tasks]
        
        -- Infere prioridade "ideal" do ótimo
        -- (tarefas que começam mais cedo têm prioridade maior)
        oPriorities = inferOptimalPriorities tasks oStarts
        
        -- Identifica discrepâncias significativas
        threshold = 0.2  -- 20% de diferença
        
    in [TaskPriority (id_t t) 
                     (Map.findWithDefault 0.0 (id_t t) hPriorities)
                     (Map.findWithDefault 0.0 (id_t t) oPriorities)
                     (shouldIncrease t hPriorities oPriorities)
       | t <- tasks
       , let hP = Map.findWithDefault 0.0 (id_t t) hPriorities
             oP = Map.findWithDefault 0.0 (id_t t) oPriorities
       , abs (hP - oP) > threshold * max hP oP
       ]

-- Calcula prioridade que a heurística usou (para análise)
computeHeuristicPriority :: TaskReq -> Map.Map Int Int -> Double
computeHeuristicPriority t workRem =
    let wr = fromIntegral $ Map.findWithDefault 0 (id_t t) workRem
        dur = fromIntegral $ duration t
        -- Normaliza: MWR (peso 2) + SPT (peso 1)
    in (2.0 * wr) / 1000.0 - dur / 100.0

-- Infere prioridade ideal baseado na ordenação ótima
inferOptimalPriorities :: [TaskReq] -> Map.Map Int Int -> Map.Map Int Double
inferOptimalPriorities tasks oStarts =
    -- Tarefas que começam mais cedo têm prioridade maior
    let maxStart = fromIntegral $ maximum $ Map.elems oStarts
        normalize start = 1.0 - (fromIntegral start / maxStart)
    in Map.map normalize oStarts

shouldIncrease :: TaskReq -> Map.Map Int Double -> Map.Map Int Double -> Bool
shouldIncrease t hPriorities oPriorities =
    let hP = Map.findWithDefault 0.0 (id_t t) hPriorities
        oP = Map.findWithDefault 0.0 (id_t t) oPriorities
    in oP > hP  -- se ótimo tem maior prioridade, devemos aumentar
```

### 3. Avaliar Detecção de Gargalos

```haskell
-- Compara detecção de gargalos: heurística vs realidade (ótimo)
evaluateBottleneckDetection :: [TaskReq]
                             -> Map.Map Int Int  -- heuristic starts
                             -> Map.Map Int Int  -- optimal starts
                             -> Map.Map Int Double  -- heuristic utilization
                             -> BottleneckAccuracy
evaluateBottleneckDetection tasks hStarts oStarts hUtil =
    let hMakespan = maximum $ Map.elems hStarts
        oMakespan = maximum $ Map.elems oStarts
        
        -- Máquinas identificadas como gargalo pela heurística (>85% uso)
        hBottlenecks = Set.fromList $ Map.keys $ Map.filter (> 0.85) hUtil
        
        -- Máquinas que REALMENTE são gargalos (calculado do ótimo)
        oUtil = analyzeMachineUtilization tasks oStarts oMakespan
        oBottlenecks = Set.fromList $ Map.keys $ Map.filter (> 0.85) oUtil
        
        -- Análise de acerto
        correct = Set.intersection hBottlenecks oBottlenecks
        falsePos = Set.difference hBottlenecks oBottlenecks  -- marcou mas não era
        falseNeg = Set.difference oBottlenecks hBottlenecks  -- era mas não marcou
        
        total = Set.size oBottlenecks
        accuracy = if total == 0 
                   then 1.0  -- sem gargalos, trivial
                   else fromIntegral (Set.size correct) / fromIntegral total
        
    in BottleneckAccuracy 
        (Set.toList correct)
        (Set.toList falsePos)
        (Set.toList falseNeg)
        accuracy
```

### 4. Gerar Sugestões de Ajuste

```haskell
-- Gera sugestões concretas de como ajustar a heurística
generateHeuristicAdjustments :: LearningInsights -> [HeuristicAdjustment]
generateHeuristicAdjustments insights =
    let gap = gap_percentage insights
        bottleneckAcc = accuracy_score $ bottleneck_accuracy insights
        machineErrors = length $ mismatched_machines insights
        
        -- Heurísticas de ajuste baseadas nos problemas encontrados
        adjustments = []
        
        -- Se gap grande E muitos erros de ordenação → ajustar SPT
        adj1 = if gap > 15.0 && machineErrors > 2
               then [HeuristicAdjustment 
                      IncreaseSPTWeight
                      "Muitas trocas de ordem detectadas. Priorize tarefas mais curtas."
                      0.3]  -- +30% no peso do SPT
               else []
        
        -- Se bottleneck detection ruim → focar no caminho crítico
        adj2 = if bottleneckAcc < 0.7
               then [HeuristicAdjustment
                      PrioritizeCriticalPath
                      "Detecção de gargalos incorreta. Analise caminho crítico melhor."
                      0.5]  -- +50% no peso de tarefas críticas
               else []
        
        -- Se prioridades muito erradas → ajustar MWR
        adj3 = let priorityErrors = length $ should_prioritize insights
               in if priorityErrors > 5
                  then [HeuristicAdjustment
                         IncreaseMWRWeight
                         "Priorizações incorretas. Foque em jobs com mais trabalho restante."
                         0.2]  -- +20% no peso do MWR
                  else []
        
    in adj1 ++ adj2 ++ adj3
```

---

## 🔌 Endpoint REST (Main.hs)

```haskell
main :: IO ()
main = scotty 3000 $ do
    -- Endpoint existente
    post "/validate" $ do
        tasks <- jsonData :: ActionM [TaskReq]
        -- ... código atual ...
    
    -- NOVO: Endpoint de aprendizado
    post "/learn" $ do
        input <- jsonData :: ActionM (OptimalSolution, [TaskReq])
        let (optimalSol, tasks) = input
        
        -- 1. Recalcula solução heurística (para comparar)
        let (hStarts, hMakespan, slacks, critPath) = solveWithRefinement tasks
            machineUtil = analyzeMachineUtilization tasks hStarts hMakespan
            
        -- 2. Compara com solução ótima
        let oStarts = optimal_starts optimalSol
            oMakespan = optimal_makespan optimalSol
            
            gap = hMakespan - oMakespan
            gapPct = (fromIntegral gap / fromIntegral oMakespan) * 100.0
            
        -- 3. Analisa diferenças
        let machineComps = compareTaskOrdering tasks hStarts oStarts
            priorityIssues = analyzeTaskPriorities tasks hStarts oStarts
            bottleneckAcc = evaluateBottleneckDetection tasks hStarts oStarts machineUtil
            
        -- 4. Monta insights
        let insights = LearningInsights 
                hMakespan oMakespan gap gapPct
                machineComps priorityIssues bottleneckAcc
                (generateHeuristicAdjustments $ ... ) -- recursivo
            
            adjustments = generateHeuristicAdjustments insights
            
            finalInsights = insights { heuristic_adjustments = adjustments }
        
        -- 5. Retorna análise completa
        json $ object [ "status" .= ("ok" :: String)
                      , "learned" .= True
                      , "insights" .= finalInsights
                      ]
```

---

## 🐍 Cliente Python (script-python/learn_from_z3.py)

```python
"""
Módulo para enviar solução ótima do Z3 de volta ao Haskell para aprendizado
"""

import requests
from typing import Dict, List, Any


def send_learning_feedback(
    tasks: List[Dict[str, Any]],
    z3_solution: Dict[int, int],  # task_id -> start_time
    z3_makespan: int,
    z3_time: float,
    haskell_url: str = "http://localhost:3000"
) -> Dict[str, Any]:
    """
    Envia solução ótima do Z3 para o Haskell aprender com as diferenças.
    
    Args:
        tasks: Lista de tarefas (formato TaskReq)
        z3_solution: Mapeamento task_id -> start_time da solução Z3
        z3_makespan: Makespan da solução ótima
        z3_time: Tempo que o Z3 levou para resolver (segundos)
        haskell_url: URL do servidor Haskell
    
    Returns:
        Insights de aprendizado do Haskell
    """
    optimal_sol = {
        "optimal_starts": z3_solution,
        "optimal_makespan": z3_makespan,
        "z3_solver_time": z3_time
    }
    
    payload = [optimal_sol, tasks]
    
    try:
        response = requests.post(
            f"{haskell_url}/learn",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao enviar feedback: {e}")
        return {"status": "error", "learned": False}


def print_learning_report(insights: Dict[str, Any]):
    """Imprime relatório de aprendizado em formato legível"""
    
    if not insights.get("learned"):
        print("❌ Aprendizado falhou")
        return
    
    data = insights["insights"]
    
    print("\n" + "="*70)
    print("📚 RELATÓRIO DE APRENDIZADO - Haskell ↔ Z3")
    print("="*70)
    
    # Gap
    print(f"\n🎯 Desempenho:")
    print(f"   Heurística: {data['heuristic_makespan']}h")
    print(f"   Ótimo (Z3): {data['optimal_makespan']}h")
    print(f"   Gap: {data['gap_hours']}h ({data['gap_percentage']:.1f}%)")
    
    # Detecção de gargalos
    acc = data['bottleneck_accuracy']
    print(f"\n🎯 Detecção de Gargalos:")
    print(f"   Acurácia: {acc['accuracy_score']*100:.1f}%")
    print(f"   ✅ Corretos: {acc['correctly_identified']}")
    print(f"   ⚠️ Falsos Positivos: {acc['false_positives']}")
    print(f"   ❌ Falsos Negativos: {acc['false_negatives']}")
    
    # Máquinas com ordenação diferente
    print(f"\n🔄 Máquinas com Ordenação Diferente:")
    for mc in data['mismatched_machines']:
        print(f"   Máquina {mc['machine_id']}:")
        print(f"      Heurística: {mc['heuristic_order']}")
        print(f"      Ótimo:      {mc['optimal_order']}")
        print(f"      Swaps necessários: {len(mc['swap_pairs'])} (impacto: {mc['impact_hours']}h)")
    
    # Prioridades incorretas
    priority_issues = data['should_prioritize']
    if priority_issues:
        print(f"\n⚡ Tarefas com Prioridade Incorreta:")
        for pr in priority_issues[:5]:  # top 5
            action = "AUMENTAR" if pr['should_increase'] else "REDUZIR"
            print(f"   Tarefa {pr['task_id']}: {action} prioridade")
            print(f"      Heurística: {pr['heuristic_priority']:.2f}")
            print(f"      Ideal:      {pr['optimal_priority']:.2f}")
    
    # Sugestões de ajuste
    print(f"\n💡 Sugestões de Ajuste:")
    for adj in data['heuristic_adjustments']:
        print(f"   [{adj['adjustment_type']}] {adj['description']}")
        print(f"      Ajuste de peso: {adj['weight_change']:+.1%}")
    
    print("\n" + "="*70 + "\n")


# Exemplo de uso integrado
def solve_and_learn(instance_file: str):
    """
    Resolve instância e envia feedback para aprendizado
    """
    from instance_loader import load_instance
    from z3 import *
    import requests
    import time
    
    # 1. Carregar instância
    instance = load_instance(instance_file)
    tasks = instance['tasks']
    
    # 2. Obter heurística do Haskell
    resp = requests.post("http://localhost:3000/validate", json=tasks)
    heuristic = resp.json()
    
    print(f"Heurística: {heuristic['makespan_heuristic']}h")
    
    # 3. Resolver com Z3
    opt = Optimize()
    starts = {t["id_t"]: Int(f"s_{t['id_t']}") for t in tasks}
    makespan = Int('makespan')
    
    # ... constraints (código do example_usage.py) ...
    
    start_time = time.time()
    if opt.check() == sat:
        z3_time = time.time() - start_time
        m = opt.model()
        z3_makespan = m[makespan].as_long()
        z3_solution = {tid: m[starts[tid]].as_long() for tid in starts}
        
        print(f"Z3 Ótimo: {z3_makespan}h (tempo: {z3_time:.2f}s)")
        
        # 4. FEEDBACK: Enviar para Haskell aprender
        print("\n📤 Enviando feedback para Haskell aprender...")
        insights = send_learning_feedback(
            tasks, z3_solution, z3_makespan, z3_time
        )
        
        # 5. Mostrar insights
        print_learning_report(insights)


if __name__ == "__main__":
    solve_and_learn("instances/AdamsBalasZawack1988/abz5.txt")
```

---

## 🔄 Aprendizado Persistente (v0.5.0+)

### Problema
Após o programa encerrar, o aprendizado é perdido.

### Solução: Persistência em Arquivo JSON

```haskell
-- Types.hs
data LearningHistory = LearningHistory
    { total_instances_solved :: Int
    , average_gap_percentage :: Double
    , learned_patterns :: [LearnedPattern]
    , heuristic_weights :: HeuristicWeights
    } deriving (Show, Generic)

data LearnedPattern = LearnedPattern
    { pattern_id :: String
    , description :: String
    , observed_count :: Int
    , confidence :: Double  -- 0.0-1.0
    } deriving (Show, Generic)

data HeuristicWeights = HeuristicWeights
    { mwr_weight :: Double   -- Most Work Remaining
    , spt_weight :: Double   -- Shortest Processing Time
    , critical_path_weight :: Double
    , load_balance_weight :: Double
    } deriving (Show, Generic)

-- Padrões iniciais
defaultWeights :: HeuristicWeights
defaultWeights = HeuristicWeights 2.0 1.0 1.0 1.0

-- Salvar/carregar histórico
saveHistory :: LearningHistory -> IO ()
saveHistory history = 
    LBS.writeFile "learning_history.json" (encode history)

loadHistory :: IO LearningHistory
loadHistory = do
    exists <- doesFileExist "learning_history.json"
    if exists
        then do
            content <- LBS.readFile "learning_history.json"
            case decode content of
                Just h -> return h
                Nothing -> return $ LearningHistory 0 0.0 [] defaultWeights
        else return $ LearningHistory 0 0.0 [] defaultWeights

-- Atualizar histórico após aprendizado
updateHistory :: LearningInsights -> LearningHistory -> LearningHistory
updateHistory insights oldHistory =
    let newGap = gap_percentage insights
        oldAvg = average_gap_percentage oldHistory
        oldCount = total_instances_solved oldHistory
        
        newAvg = (oldAvg * fromIntegral oldCount + newGap) / fromIntegral (oldCount + 1)
        
        -- Atualiza pesos baseado nas sugestões
        newWeights = applyAdjustments 
            (heuristic_adjustments insights)
            (heuristic_weights oldHistory)
        
    in oldHistory 
        { total_instances_solved = oldCount + 1
        , average_gap_percentage = newAvg
        , heuristic_weights = newWeights
        }

applyAdjustments :: [HeuristicAdjustment] -> HeuristicWeights -> HeuristicWeights
applyAdjustments [] weights = weights
applyAdjustments (adj:rest) weights =
    let newWeights = case adjustment_type adj of
            IncreaseMWRWeight -> 
                weights { mwr_weight = mwr_weight weights * (1.0 + weight_change adj) }
            IncreaseSPTWeight -> 
                weights { spt_weight = spt_weight weights * (1.0 + weight_change adj) }
            PrioritizeCriticalPath -> 
                weights { critical_path_weight = critical_path_weight weights * (1.0 + weight_change adj) }
            BalanceLoadBetter -> 
                weights { load_balance_weight = load_balance_weight weights * (1.0 + weight_change adj) }
    in applyAdjustments rest newWeights
```

### Usar Pesos Aprendidos na Heurística

```haskell
-- Modificar solveHeuristic para aceitar pesos customizados
solveHeuristic' :: [TaskReq] -> HeuristicWeights -> (Map.Map Int Int, Int)
solveHeuristic' tasks weights = (startTimes, makespan)
  where
    -- ... código similar ...
    
    -- Prioridade ajustada com pesos aprendidos
    priority t = 
        let wr = fromIntegral $ Map.findWithDefault 0 (id_t t) workRemaining
            dur = fromIntegral $ duration t
            
            -- Aplica pesos aprendidos
            wrScore = mwr_weight weights * wr / 1000.0
            sptScore = negate $ spt_weight weights * dur / 100.0
            
        in (wrScore + sptScore, id_t t)  -- tie-breaker
    
    -- ... resto do código ...

-- Main com persistência
main :: IO ()
main = do
    -- Carregar histórico ao iniciar
    historyRef <- newIORef =<< loadHistory
    
    scotty 3000 $ do
        post "/validate" $ do
            tasks <- jsonData
            history <- liftIO $ readIORef historyRef
            
            -- Usar pesos aprendidos
            let weights = heuristic_weights history
                (hints, hMakespan, slacks, critPath) = solveHeuristic' tasks weights
            
            -- ... resto do código ...
        
        post "/learn" $ do
            (optimalSol, tasks) <- jsonData
            oldHistory <- liftIO $ readIORef historyRef
            
            -- ... análise ...
            
            let insights = LearningInsights { ... }
                newHistory = updateHistory insights oldHistory
            
            -- Salvar novo histórico
            liftIO $ saveHistory newHistory
            liftIO $ writeIORef historyRef newHistory
            
            json $ object ["status" .= "ok", "insights" .= insights]
```

---

## 📊 Métricas de Sucesso

### Curto Prazo (após 10 instâncias)
- ✅ Gap médio reduz de 15% → 12%
- ✅ Acurácia de gargalos melhora de 70% → 85%

### Médio Prazo (após 50 instâncias)
- ✅ Gap médio reduz para 8%
- ✅ Heurística encontra ótimo em 20% dos casos

### Longo Prazo (após 200+ instâncias)
- ✅ Gap médio < 5%
- ✅ Heurística competitiva com solvers comerciais em instâncias pequenas

---

## 🚀 Roadmap de Implementação

### Fase 1: Protótipo Básico (v0.4.0)
- [ ] Adicionar tipos em `Types.hs`
- [ ] Implementar funções de comparação em `Main.hs`
- [ ] Criar endpoint `/learn`
- [ ] Script Python `learn_from_z3.py`
- [ ] Testar em ft06, la01, abz5

### Fase 2: Refinamento (v0.4.1)
- [ ] Melhorar algoritmos de inferência de prioridades
- [ ] Adicionar mais tipos de ajustes heurísticos
- [ ] Visualização de comparações (Gantt lado a lado)

### Fase 3: Persistência (v0.5.0)
- [ ] Salvar/carregar histórico
- [ ] Aplicar pesos aprendidos na heurística
- [ ] Dashboard de evolução do aprendizado

### Fase 4: Aprendizado Avançado (v0.6.0)
- [ ] Clustering de padrões de instâncias
- [ ] Diferentes pesos para diferentes tipos de problema
- [ ] Meta-aprendizado (quando aplicar cada heurística)

---

## 🎓 Referências

- **Learning to Schedule**: Zhang et al. (2020) - Neural combinatorial optimization
- **Feature-based Learning**: Bengio et al. (2021) - ML for combinatorial optimization
- **Local Search Learning**: Khalil et al. (2017) - Learning to run heuristics

---

**Status**: 📝 Proposta Técnica  
**Próximo Passo**: Implementar Fase 1 (Protótipo Básico)  
**Impacto Esperado**: Gap 15% → 8% após 50 instâncias
