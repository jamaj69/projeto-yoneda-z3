{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE DeriveGeneric #-}

import Web.Scotty (scotty, post, json, jsonData, ActionM)
import Data.Aeson (FromJSON, ToJSON, object, (.=))
import GHC.Generics
import qualified Algebra.Graph.AdjacencyMap as AM
import qualified Algebra.Graph.AdjacencyMap.Algorithm as Algo
import qualified Data.Map as Map

-- Constante de Setup entre Jobs diferentes
setupTime :: Int
setupTime = 2

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


solveHeuristic :: [TaskReq] -> (Map.Map Int Int, Int)
solveHeuristic tasks = (startTimes, makespan)
  where
    -- 1. Construção do Grafo e Ordenação Topológica
    adjMap = AM.stars [ (id_t t, maybe [] (\n -> [n]) (next_t t)) | t <- tasks ]
    topoOrder = case Algo.topSort adjMap of
                  Right order -> order
                  Left _      -> [] 
    
    taskLookup = Map.fromList [(id_t t, t) | t <- tasks]
    
    -- 2. Simulação (Gulosa) considerando Precedência e Setup de Máquina
    -- Acumulador: (Mapa de Fim das Tarefas, Estado das Máquinas)
    (endTimes, _) = foldl assignTask (Map.empty, Map.empty) topoOrder
    
    assignTask (ends, machs) tId =
        let t = taskLookup Map.! tId
            -- Regra de Precedência: Terminar a tarefa anterior do mesmo Job
            tPrevEnd = maybe 0 (\pId -> Map.findWithDefault 0 pId ends) (prev_t t)
            
            -- Regra de Recurso: Disponibilidade da máquina e Setup
            (mFree, lastJob) = Map.findWithDefault (0, -1) (machine_id t) machs
            
            -- Aplica setup se mudar o Job na mesma máquina (exceto se for a 1ª tarefa)
            currentSetup = if lastJob /= (-1) && lastJob /= job_id t 
                           then setupTime 
                           else 0
            
            startTime = max tPrevEnd (mFree + currentSetup)
            endTime   = startTime + duration t
        in (Map.insert tId endTime ends, Map.insert (machine_id t) (endTime, job_id t) machs)

    -- 3. Cálculo de Inícios e Makespan
    startTimes = Map.mapWithKey (\tId end -> end - (duration (taskLookup Map.! tId))) endTimes
    makespan   = if Map.null endTimes then 0 else maximum (Map.elems endTimes)

main :: IO ()
main = scotty 3000 $ do
    post "/validate" $ do
        tasks <- jsonData :: ActionM [TaskReq]
        let adjMap = AM.stars [ (id_t t, maybe [] (\n -> [n]) (next_t t)) | t <- tasks ]
        
        if Algo.isAcyclic adjMap
            then do
                let (hints, hMakespan) = solveHeuristic tasks
                json $ object [ "status" .= ("ok" :: String)
                              , "valid"  .= True
                              , "hints"  .= hints
                              , "makespan_heuristic" .= hMakespan ]
            else json $ object [ "status" .= ("erro" :: String)
                               , "valid"  .= False
                               , "msg"    .= ("Ciclo detectado!" :: String) ]
