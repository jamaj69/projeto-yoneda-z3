{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE DeriveGeneric #-}

import Web.Scotty (scotty, post, json, jsonData, ActionM)
import Data.Aeson (FromJSON, ToJSON, object, (.=))
import GHC.Generics
import qualified Algebra.Graph.AdjacencyMap as AM
import qualified Algebra.Graph.AdjacencyMap.Algorithm as Algo
import qualified Data.Map as Map
import qualified Data.List as List
import Data.Ord (comparing)
import Data.Maybe (isNothing)

-- Constante de Setup entre Jobs diferentes
setupTime :: Int
setupTime = 0

data TaskReq = TaskReq 
    { id_t       :: Int
    , job_id     :: Int
    , machine_id :: Int
    , duration   :: Int
    , next_t     :: Maybe Int 
    , prev_t     :: Maybe Int 
    } deriving (Show, Generic)

instance FromJSON TaskReq
instance ToJSON TaskReq

-- Calcula trabalho restante de cada job
remainingWork :: [TaskReq] -> Int -> Map.Map Int Int
remainingWork tasks jobId = 
    let jobTasks = filter (\t -> job_id t == jobId) tasks
        taskMap = Map.fromList [(id_t t, t) | t <- jobTasks]
        
        computeWork tid = case Map.lookup tid taskMap of
            Nothing -> 0
            Just t -> duration t + maybe 0 computeWork (next_t t)
    in Map.fromList [(id_t t, computeWork (id_t t)) | t <- jobTasks]

-- Heurística melhorada: Most Work Remaining + Shortest Processing Time
solveHeuristic :: [TaskReq] -> (Map.Map Int Int, Int)
solveHeuristic tasks = (startTimes, makespan)
  where
    taskLookup = Map.fromList [(id_t t, t) | t <- tasks]
    
    -- Calcular trabalho restante para cada tarefa
    allJobs = List.nub [job_id t | t <- tasks]
    workRemaining = Map.unions [remainingWork tasks j | j <- allJobs]
    
    -- Lista scheduling com priorização
    schedule = go (filter (isNothing . prev_t) tasks) Map.empty Map.empty
      where
        go :: [TaskReq] -> Map.Map Int Int -> Map.Map Int (Int, Int) -> Map.Map Int Int
        go [] endTimes _ = endTimes
        go ready endTimes machs =
            let -- Ordena tarefas ready por prioridade:
                -- 1. Maior trabalho restante no job (MWR - Most Work Remaining)
                -- 2. Menor duração (SPT - Shortest Processing Time)
                priority t = ( negate (Map.findWithDefault 0 (id_t t) workRemaining)
                            , duration t
                            , id_t t)  -- tie-breaker
                
                sortedReady = List.sortBy (comparing priority) ready
                
                -- Escolhe primeira tarefa
                t:rest = sortedReady
                tId = id_t t
                
                -- Calcula tempo de início
                tPrevEnd = maybe 0 (\pId -> Map.findWithDefault 0 pId endTimes) (prev_t t)
                (mFree, lastJob) = Map.findWithDefault (0, -1) (machine_id t) machs
                currentSetup = if lastJob /= (-1) && lastJob /= job_id t 
                              then setupTime else 0
                
                startTime = max tPrevEnd (mFree + currentSetup)
                endTime = startTime + duration t
                
                -- Atualiza estruturas
                newEndTimes = Map.insert tId endTime endTimes
                newMachs = Map.insert (machine_id t) (endTime, job_id t) machs
                
                -- Adiciona próxima tarefa do job se houver
                newReady = case next_t t of
                    Just nextId -> (taskLookup Map.! nextId) : rest
                    Nothing -> rest
                
            in go newReady newEndTimes newMachs
    
    -- Calcula tempos de início e makespan
    startTimes = Map.mapWithKey (\tId end -> end - (duration (taskLookup Map.! tId))) schedule
    makespan = if Map.null schedule then 0 else maximum (Map.elems schedule)

-- Análise de Slack (folga) de cada tarefa
-- Slack = quanto a tarefa pode atrasar sem afetar o makespan
computeSlack :: [TaskReq] -> Map.Map Int Int -> Int -> Map.Map Int Int
computeSlack tasks startTimes makespan' = 
    let taskLookup = Map.fromList [(id_t t, t) | t <- tasks]
        endTimes = Map.mapWithKey (\tid start -> start + duration (taskLookup Map.! tid)) startTimes
        
        -- Calcula Latest Start Time (LST) - mais tarde que pode começar
        latestStarts = computeLST tasks makespan' Map.empty
          where
            computeLST [] _ acc = acc
            computeLST (t:ts) ms acc =
                let tid = id_t t
                    -- LST baseado nos sucessores
                    lstFromSuccessors = case next_t t of
                        Nothing -> ms - duration t  -- Última tarefa
                        Just nextId -> 
                            case Map.lookup nextId acc of
                                Just nextLST -> nextLST - duration t
                                Nothing -> ms - duration t  -- Conservador
                    
                    -- LST também limitado por máquina (se houver sucessor na mesma máquina)
                    currentLST = lstFromSuccessors
                    
                in computeLST ts ms (Map.insert tid currentLST acc)
        
        -- Slack = LST - EST (earliest start time)
    in Map.mapWithKey (\tid est -> 
        let lst = Map.findWithDefault est tid latestStarts
        in max 0 (lst - est)
       ) startTimes

-- Identifica caminho crítico (tarefas com slack = 0)
findCriticalPath :: [TaskReq] -> Map.Map Int Int -> [Int]
findCriticalPath tasks slacks = 
    [id_t t | t <- tasks, Map.findWithDefault 0 (id_t t) slacks == 0]

-- Analisa utilização de máquinas
analyzeMachineUtilization :: [TaskReq] -> Map.Map Int Int -> Int -> Map.Map Int Double
analyzeMachineUtilization tasks startTimes makespan' =
    let taskLookup = Map.fromList [(id_t t, t) | t <- tasks]
        endTimes = Map.mapWithKey (\tid start -> start + duration (taskLookup Map.! tid)) startTimes
        
        -- Agrupa por máquina
        machineGroups = Map.fromListWith (++) 
            [(machine_id t, [(id_t t, t)]) | t <- tasks]
        
        -- Calcula tempo total ocupado em cada máquina
        machineWorkload = Map.map (\taskList -> 
            sum [duration t | (_, t) <- taskList]
          ) machineGroups
        
        -- Utilização = workload / makespan
    in Map.map (\workload -> fromIntegral workload / fromIntegral makespan') machineWorkload

-- Refinamento local: tenta melhorar a solução focando nos gargalos
refineBottlenecks :: [TaskReq] -> Map.Map Int Int -> Int -> (Map.Map Int Int, Int)
refineBottlenecks tasks initialStarts initialMakespan =
    let slacks = computeSlack tasks initialStarts initialMakespan
        criticalTasks = findCriticalPath tasks slacks
        machineUtil = analyzeMachineUtilization tasks initialStarts initialMakespan
        
        -- Identifica máquinas críticas (utilização > 0.9)
        criticalMachines = Map.keys $ Map.filter (> 0.9) machineUtil
        
        -- Tenta swap de tarefas em máquinas críticas
        -- (Implementação simplificada - apenas retorna solução original por enquanto)
        -- TODO: Implementar local search mais sofisticado
        
    in (initialStarts, initialMakespan)

-- Heurística completa com análise e refinamento
solveWithRefinement :: [TaskReq] -> (Map.Map Int Int, Int, Map.Map Int Int, [Int])
solveWithRefinement tasks = 
    let -- Fase 1: Solução inicial MWR+SPT
        (initialStarts, initialMakespan) = solveHeuristic tasks
        
        -- Fase 2: Análise de gargalos
        slacks = computeSlack tasks initialStarts initialMakespan
        criticalPath = findCriticalPath tasks slacks
        
        -- Fase 3: Refinamento (futuro)
        (refinedStarts, refinedMakespan) = refineBottlenecks tasks initialStarts initialMakespan
        
    in (refinedStarts, refinedMakespan, slacks, criticalPath)

main :: IO ()
main = scotty 3000 $ do
    post "/validate" $ do
        tasks <- jsonData :: ActionM [TaskReq]
        let adjMap = AM.stars [ (id_t t, maybe [] (\n -> [n]) (next_t t)) | t <- tasks ]
        
        if Algo.isAcyclic adjMap
            then do
                let (hints, hMakespan, slacks, criticalPath) = solveWithRefinement tasks
                    machineUtil = analyzeMachineUtilization tasks hints hMakespan
                    criticalMachines = Map.keys $ Map.filter (> 0.85) machineUtil
                    
                json $ object [ "status" .= ("ok" :: String)
                              , "valid"  .= True
                              , "hints"  .= hints
                              , "makespan_heuristic" .= hMakespan
                              , "slacks" .= slacks
                              , "critical_path" .= criticalPath
                              , "critical_machines" .= criticalMachines
                              , "machine_utilization" .= machineUtil
                              ]
            else json $ object [ "status" .= ("erro" :: String)
                               , "valid"  .= False
                               , "msg"    .= ("Ciclo detectado!" :: String) ]
