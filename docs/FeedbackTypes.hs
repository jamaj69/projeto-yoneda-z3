{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE OverloadedStrings #-}

{-|
Tipos para Sistema de Aprendizado por Feedback (v0.4.0+)

Este módulo define tipos para o endpoint /learn, onde o Haskell
recebe a solução ótima do Z3 e analisa diferenças com sua heurística.

Para usar: 
  1. Copiar tipos para src/Types.hs
  2. Implementar funções de análise em app-haskell/src/Main.hs
  3. Criar endpoint POST /learn
  4. Testar com script-python/learn_from_z3.py
-}

module FeedbackTypes where

import Data.Aeson (FromJSON, ToJSON)
import GHC.Generics
import qualified Data.Map as Map

-- | Solução ótima retornada pelo Z3
data OptimalSolution = OptimalSolution
    { optimal_starts :: Map.Map Int Int  -- ^ id_tarefa -> tempo_inicio
    , optimal_makespan :: Int            -- ^ Makespan da solução ótima
    , z3_solver_time :: Double           -- ^ Tempo de otimização (segundos)
    } deriving (Show, Generic)

instance FromJSON OptimalSolution
instance ToJSON OptimalSolution


-- | Entrada do endpoint /learn
data LearnRequest = LearnRequest
    { optimal_solution :: OptimalSolution  -- ^ Solução do Z3
    , tasks :: [TaskReq]                   -- ^ Tarefas da instância
    } deriving (Show, Generic)

instance FromJSON LearnRequest
instance ToJSON LearnRequest


-- | Análise comparativa entre heurística e ótimo
data LearningInsights = LearningInsights
    { heuristic_makespan :: Int
    , optimal_makespan :: Int
    , gap_hours :: Int                           -- ^ Diferença absoluta
    , gap_percentage :: Double                    -- ^ Diferença percentual
    
    -- Máquinas onde o ordenamento diferiu
    , mismatched_machines :: [MachineComparison]
    
    -- Tarefas que deveriam ter sido priorizadas diferentemente
    , should_prioritize :: [TaskPriority]
    
    -- Gargalos detectados corretamente vs incorretamente
    , bottleneck_accuracy :: BottleneckAccuracy
    
    -- Sugestões de ajuste de heurística
    , heuristic_adjustments :: [HeuristicAdjustment]
    } deriving (Show, Generic)

instance FromJSON LearningInsights
instance ToJSON LearningInsights


-- | Comparação de ordenação em uma máquina específica
data MachineComparison = MachineComparison
    { machine_id :: Int
    , heuristic_order :: [Int]  -- ^ Ordem das tarefas na heurística
    , optimal_order :: [Int]    -- ^ Ordem na solução ótima
    , swap_pairs :: [(Int, Int)] -- ^ Pares que deveriam ter sido trocados
    , impact_hours :: Int        -- ^ Impacto estimado no makespan
    } deriving (Show, Generic)

instance FromJSON MachineComparison
instance ToJSON MachineComparison


-- | Tarefa que deveria ter recebido prioridade diferente
data TaskPriority = TaskPriority
    { task_id :: Int
    , heuristic_priority :: Double  -- ^ Prioridade calculada (MWR+SPT)
    , optimal_priority :: Double    -- ^ Prioridade inferida do ótimo
    , should_increase :: Bool       -- ^ Deve aumentar prioridade?
    } deriving (Show, Generic)

instance FromJSON TaskPriority
instance ToJSON TaskPriority


-- | Precisão da detecção de gargalos
data BottleneckAccuracy = BottleneckAccuracy
    { correctly_identified :: [Int]    -- ^ Máquinas corretamente marcadas
    , false_positives :: [Int]          -- ^ Marcadas mas não eram gargalo
    , false_negatives :: [Int]          -- ^ Eram gargalo mas não detectadas
    , accuracy_score :: Double          -- ^ % de acerto (0.0-1.0)
    } deriving (Show, Generic)

instance FromJSON BottleneckAccuracy
instance ToJSON BottleneckAccuracy


-- | Sugestão de ajuste na heurística
data HeuristicAdjustment = HeuristicAdjustment
    { adjustment_type :: AdjustmentType
    , description :: String
    , weight_change :: Double  -- ^ Quanto mudar o peso (+/-)
    } deriving (Show, Generic)

instance FromJSON HeuristicAdjustment
instance ToJSON HeuristicAdjustment


-- | Tipos de ajuste possíveis
data AdjustmentType 
    = IncreaseMWRWeight      -- ^ Aumentar peso do Most Work Remaining
    | IncreaseSPTWeight      -- ^ Aumentar peso do Shortest Processing Time
    | PrioritizeCriticalPath -- ^ Focar mais no caminho crítico
    | BalanceLoadBetter      -- ^ Melhorar balanceamento de carga
    deriving (Show, Generic, Eq)

instance FromJSON AdjustmentType
instance ToJSON AdjustmentType


-- | Resposta do endpoint /learn
data LearnResponse = LearnResponse
    { status :: String
    , learned :: Bool
    , insights :: LearningInsights
    } deriving (Show, Generic)

instance FromJSON LearnResponse
instance ToJSON LearnResponse


-- ==========================================================================
-- APRENDIZADO PERSISTENTE (v0.5.0+)
-- ==========================================================================

-- | Histórico de aprendizado (salvo em arquivo JSON)
data LearningHistory = LearningHistory
    { total_instances_solved :: Int
    , average_gap_percentage :: Double
    , learned_patterns :: [LearnedPattern]
    , heuristic_weights :: HeuristicWeights
    } deriving (Show, Generic)

instance FromJSON LearningHistory
instance ToJSON LearningHistory


-- | Padrão aprendido durante execução
data LearnedPattern = LearnedPattern
    { pattern_id :: String
    , pattern_description :: String
    , observed_count :: Int
    , confidence :: Double  -- ^ 0.0-1.0
    } deriving (Show, Generic)

instance FromJSON LearnedPattern
instance ToJSON LearnedPattern


-- | Pesos da heurística (podem ser ajustados via aprendizado)
data HeuristicWeights = HeuristicWeights
    { mwr_weight :: Double             -- ^ Most Work Remaining
    , spt_weight :: Double             -- ^ Shortest Processing Time
    , critical_path_weight :: Double   -- ^ Peso de tarefas no caminho crítico
    , load_balance_weight :: Double    -- ^ Peso do balanceamento de máquinas
    } deriving (Show, Generic)

instance FromJSON HeuristicWeights
instance ToJSON HeuristicWeights


-- | Pesos padrão (antes de qualquer aprendizado)
defaultWeights :: HeuristicWeights
defaultWeights = HeuristicWeights
    { mwr_weight = 2.0
    , spt_weight = 1.0
    , critical_path_weight = 1.0
    , load_balance_weight = 1.0
    }


-- | Histórico inicial (para arquivo JSON vazio)
emptyHistory :: LearningHistory
emptyHistory = LearningHistory
    { total_instances_solved = 0
    , average_gap_percentage = 0.0
    , learned_patterns = []
    , heuristic_weights = defaultWeights
    }


-- ==========================================================================
-- EXEMPLO DE USO
-- ==========================================================================

{-
-- Em Main.hs, adicionar:

import FeedbackTypes
import Data.Aeson (decode, encode)
import qualified Data.ByteString.Lazy as LBS

main :: IO ()
main = do
    -- Carregar histórico ao iniciar
    historyRef <- newIORef =<< loadHistory
    
    scotty 3000 $ do
        -- Endpoint existente
        post "/validate" $ do
            tasks <- jsonData :: ActionM [TaskReq]
            history <- liftIO $ readIORef historyRef
            
            -- Usar pesos aprendidos
            let weights = heuristic_weights history
                (hints, hMakespan, ...) = solveWithWeights tasks weights
            
            json $ object [ ... ]
        
        -- NOVO: Endpoint de aprendizado
        post "/learn" $ do
            req <- jsonData :: ActionM LearnRequest
            let optSol = optimal_solution req
                tasks' = tasks req
            
            history <- liftIO $ readIORef historyRef
            let weights = heuristic_weights history
            
            -- Recalcula heurística
            let (hStarts, hMakespan, ...) = solveWithWeights tasks' weights
            
            -- Compara com ótimo
            let insights = analyzeComparison tasks' hStarts (optimal_starts optSol)
                                            hMakespan (optimal_makespan optSol)
            
            -- Atualiza histórico
            let newHistory = updateHistory insights history
            liftIO $ saveHistory newHistory
            liftIO $ writeIORef historyRef newHistory
            
            json $ object [ "status" .= ("ok" :: String)
                          , "learned" .= True
                          , "insights" .= insights
                          ]

-- Funções auxiliares
loadHistory :: IO LearningHistory
loadHistory = do
    exists <- doesFileExist "learning_history.json"
    if exists
        then do
            content <- LBS.readFile "learning_history.json"
            case decode content of
                Just h -> return h
                Nothing -> return emptyHistory
        else return emptyHistory

saveHistory :: LearningHistory -> IO ()
saveHistory history = 
    LBS.writeFile "learning_history.json" (encode history)

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
-}
