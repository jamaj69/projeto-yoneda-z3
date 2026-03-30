{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE DeriveGeneric     #-}
{-# LANGUAGE RankNTypes        #-}

import Web.Scotty (scotty, post, json, jsonData, ActionM)
import Data.Aeson (FromJSON, ToJSON, object, (.=))
import GHC.Generics
import qualified Algebra.Graph.AdjacencyMap as AM
import qualified Algebra.Graph.AdjacencyMap.Algorithm as Algo
import qualified Data.Map as Map
import qualified Data.Set as Set
import qualified Data.List as List
import Data.Ord (comparing)
import Data.Maybe (isNothing, listToMaybe, mapMaybe)

-- Machine ordering: machine_id -> [task_id] in scheduled order
type MachineOrder = Map.Map Int [Int]

-- ─────────────────────────────────────────────────────────────────────────────
-- Yoneda embedding for list fmap fusion
--
--   Yoneda lemma:  F(a)  ≅  ∀b. Hom(b, F(-))   (for any functor F)
--   Haskell encoding:
--     newtype Yoneda [] a = Yoneda { runYoneda :: ∀b. (a → b) → [b] }
--
--   Key property: every fmap is O(1) — it merely extends the continuation chain.
--   lowerYoneda performs ONE traversal of the source list, applying the entire
--   accumulated chain of fmaps in a single pass — no intermediate lists.
--
--   The N-neighborhood generators exploit this: up to three logical steps
--   (raw descriptor → machine sequence → graph evaluation → SearchState)
--   are expressed as three O(1) fmaps, then collapsed by lowerYoneda into
--   a single pass.  mapMaybe is lazy: the chain is lowered only as far as the
--   consumer (firstImprovement) demands, stopping at the first improvement.
-- ─────────────────────────────────────────────────────────────────────────────

newtype Yoneda f a = Yoneda { runYoneda :: forall b. (a -> b) -> f b }

liftYoneda :: Functor f => f a -> Yoneda f a
liftYoneda fa = Yoneda (`fmap` fa)

lowerYoneda :: Yoneda f a -> f a
lowerYoneda (Yoneda f) = f id

instance Functor (Yoneda f) where
    -- Compose g into the continuation: O(1), no traversal until lowerYoneda
    fmap g (Yoneda f) = Yoneda (f . (. g))

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
                (t, rest) = case sortedReady of
                    (x:xs) -> (x, xs)
                    []     -> error "solveHeuristic: empty ready list (invariant violated)"
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

-- ─────────────────────────────────────────────────────────────────────────────
-- Disjunctive Graph: JSSP solution as a directed graph
-- Conjunction arcs  (fixed)    = job precedence: task_i → task_{i+1}
-- Disjunction arcs  (variable) = machine ordering: t1 → t2 means t1 runs first
-- Makespan = length of the critical (longest weighted) path in this DAG
-- Swapping two adjacent machine tasks = reversing one disjunction arc
-- isAcyclic check ensures the swap doesn't create an infeasible cycle
-- ─────────────────────────────────────────────────────────────────────────────

-- Extract machine ordering from start times
machineOrderFromStarts :: [TaskReq] -> Map.Map Int Int -> MachineOrder
machineOrderFromStarts tasks startTimes =
    let tasksByMachine = Map.fromListWith (++) [(machine_id t, [id_t t]) | t <- tasks]
    in Map.map (List.sortBy (comparing (\tid -> Map.findWithDefault 0 tid startTimes))) tasksByMachine

-- Build the complete directed graph (conjunction + machine disjunction arcs)
buildSolutionGraph :: [TaskReq] -> MachineOrder -> AM.AdjacencyMap Int
buildSolutionGraph tasks machOrder =
    let jobArcs  = AM.stars [(id_t t, maybe [] (:[]) (next_t t)) | t <- tasks]
        machArcs = AM.edges
            [ (t1, t2)
            | taskList <- Map.elems machOrder
            , (t1, t2) <- zip taskList (drop 1 taskList)
            ]
    in AM.overlay jobArcs machArcs

-- Forward pass: Earliest Start Time for each task via topological DP
-- EST[v] = max over predecessors p of  (EST[p] + duration[p])
forwardPass :: [TaskReq] -> AM.AdjacencyMap Int -> Map.Map Int Int
forwardPass tasks graph =
    case Algo.topSort graph of
        Left  _         -> Map.empty   -- cycle (invalid schedule)
        Right topoOrder ->
            let taskMap = Map.fromList [(id_t t, t) | t <- tasks]
                predMap = AM.adjacencyMap (AM.transpose graph)  -- vertex → predecessors
            in foldl (\acc tid ->
                let preds = maybe [] Set.toList (Map.lookup tid predMap)
                    est   = maximum (0 : [ Map.findWithDefault 0 p acc
                                          + duration (taskMap Map.! p)
                                        | p <- preds ])
                in Map.insert tid est acc
              ) Map.empty topoOrder

-- Backward pass: Latest Start Time for each task via reverse topological DP
-- LST[v] = min over successors s of  (LST[s] - duration[v])
backwardPass :: [TaskReq] -> AM.AdjacencyMap Int -> Int -> Map.Map Int Int
backwardPass tasks graph makespan =
    case Algo.topSort graph of
        Left  _         -> Map.empty
        Right topoOrder ->
            let taskMap = Map.fromList [(id_t t, t) | t <- tasks]
                succMap = AM.adjacencyMap graph  -- vertex → successors
            in foldl (\acc tid ->
                let succs = maybe [] Set.toList (Map.lookup tid succMap)
                    task  = taskMap Map.! tid
                    lst   = minimum
                              ( makespan - duration task
                              : [ Map.findWithDefault (makespan - duration task) s acc
                                  - duration task
                                | s <- succs ])
                in Map.insert tid lst acc
              ) Map.empty (reverse topoOrder)

-- Graph-based slack: accurate because it includes machine ordering arcs
-- Slack[v] = LST[v] - EST[v]   (zero → on the critical path)
graphBasedSlack :: [TaskReq] -> AM.AdjacencyMap Int -> Int -> Map.Map Int Int
graphBasedSlack tasks graph makespan =
    let ests = forwardPass  tasks graph
        lsts = backwardPass tasks graph makespan
    in Map.mapWithKey (\tid est ->
        max 0 (Map.findWithDefault est tid lsts - est)
      ) ests

-- ─────────────────────────────────────────────────────────────────────────────
-- N2 Neighborhood Local Search  (Nowicki & Smutnicki, 1996)
-- For each consecutive pair of critical-path tasks on the same machine,
-- try reversing their order. Accept if the swap is acyclic and reduces makespan.
-- ─────────────────────────────────────────────────────────────────────────────

-- Swap two adjacent elements in a list
swapAdjacent :: Eq a => a -> a -> [a] -> [a]
swapAdjacent _ _ []        = []
swapAdjacent _ _ [x]       = [x]
swapAdjacent a b (x:y:rest)
    | x == a && y == b = b : a : rest
    | otherwise        = x : swapAdjacent a b (y : rest)

-- ─────────────────────────────────────────────────────────────────────────────
-- Unified search state
-- ─────────────────────────────────────────────────────────────────────────────

data SearchState = SearchState
    { ssOrder :: MachineOrder
    , ssESTs  :: Map.Map Int Int  -- Earliest Start Times (result of forward pass)
    , ssMS    :: Int              -- Makespan
    } deriving (Show)

initSearchState :: [TaskReq] -> Map.Map Int Int -> Int -> SearchState
initSearchState tasks ests ms =
    SearchState (machineOrderFromStarts tasks ests) ests ms

-- ─────────────────────────────────────────────────────────────────────────────
-- Yoneda-fused candidate evaluator
--
-- Each (mId, newSeq) candidate passes through four logical steps:
--   (Int,[Int])  →  MachineOrder  →  AdjacencyMap  →  EST map  →  Maybe SearchState
-- Sequential map/filter passes would build three intermediate lists.
-- evalCandidate fuses them into ONE function; in multi-step Yoneda pipelines
-- (N5, N7) the additional fmaps are O(1) continuations — lowerYoneda then
-- applies the entire composed chain in a single traversal of the raw descriptors.
-- ─────────────────────────────────────────────────────────────────────────────

evalCandidate :: [TaskReq] -> Map.Map Int TaskReq -> SearchState
              -> (Int, [Int]) -> Maybe SearchState
evalCandidate tasks taskMap ss (mId, newSeq) =
    let newOrd = Map.insert mId newSeq (ssOrder ss)
        g      = buildSolutionGraph tasks newOrd
    in if not (Algo.isAcyclic g) then Nothing
       else let ests = forwardPass tasks g
                ms'  = makespanFromESTs ests taskMap
            in if ms' < ssMS ss then Just (SearchState newOrd ests ms') else Nothing

-- ─────────────────────────────────────────────────────────────────────────────
-- Neighborhood pipeline
--
-- A Neighborhood is a lazy stream of strictly-better SearchStates.
-- Haskell lists are lazy: mapMaybe demands elements only until firstImprovement
-- finds its result — the Yoneda continuation chain is lowered only as far as
-- needed, stopping evaluation of the remaining candidates.
-- ─────────────────────────────────────────────────────────────────────────────

type Neighborhood = SearchState -> [SearchState]

-- A step selector chooses which improving SearchState to accept from a
-- non-empty list of candidates.
type StepSelector = [SearchState] -> SearchState

-- Steepest descent: pick the candidate with minimum makespan ("best-first").
-- Equivalent to the old carry-forward n2Pass behavior; avoids greedy dead-ends
-- on small instances.  Requires forcing the whole candidate list — only use
-- when the neighborhood is small (small/medium instances).
steepestDescent :: StepSelector
steepestDescent = List.minimumBy (comparing ssMS)

-- First improvement: pick the first improving candidate (lazy — stops early).
-- Preferred for large instances where forcing the full neighborhood is
-- expensive; also keeps N7's lazy-stop property.
firstImprovementSel :: StepSelector
firstImprovementSel (x:_) = x
firstImprovementSel []    = error "firstImprovementSel: called on empty list (invariant violated)"

-- Iterate to local minimum using a given step selector, bounded by budget.
convergeN :: StepSelector -> Int -> Neighborhood -> SearchState -> SearchState
convergeN sel n nbhd = go n
  where
    go 0 ss = ss
    go k ss = case nbhd ss of
        [] -> ss           -- local minimum
        xs -> go (k-1) (sel xs)

-- Greedy carry-forward sweep: scan the candidate list with foldl', updating
-- the working state immediately whenever an improvement is found.
-- A single sweep can chain many dependent improvements (swap A changes the
-- ordering so swap B now becomes valid and improving — they are found in one
-- pass).  This replicates the old trySwaps behavior that reached la01=666h.
-- Yoneda still handles candidate *generation* (liftYoneda + fmap, O(1));
-- lowerYoneda collapses those fmaps; foldl' drives carry-forward evaluation.
greedySweep :: [TaskReq] -> Map.Map Int TaskReq -> Neighborhood
greedySweep tasks taskMap ss0 =
    let graph0  = buildSolutionGraph tasks (ssOrder ss0)
        slack0  = graphBasedSlack tasks graph0 (ssMS ss0)
        critSet = Set.fromList [tid | (tid, s) <- Map.toList slack0, s == 0]
        -- Candidate descriptors (mId, newSeq) — generated from the *initial*
        -- critical set, but evaluated greedily against the evolving state
        cands   = lowerYoneda $ fmap id $ liftYoneda
                    [ (mId, swapAdjacent t1 t2 tl)
                    | (mId, tl) <- Map.toList (ssOrder ss0)
                    , (t1, t2)  <- zip tl (drop 1 tl)
                    , Set.member t1 critSet || Set.member t2 critSet
                    ]
        -- foldl': carry state forward, applying every improvement found
        ss' = foldl (\cur cand -> case evalCandidate tasks taskMap cur cand of
                        Just better -> better    -- improvement: update state
                        Nothing     -> cur       -- no improvement: keep going
                    ) ss0 cands
    in if ssMS ss' < ssMS ss0 then [ss'] else []

-- Iterate greedy sweeps to convergence
convergeGreedy :: Int -> [TaskReq] -> Map.Map Int TaskReq -> SearchState -> SearchState
convergeGreedy n tasks taskMap = go n
  where
    go 0 ss = ss
    go k ss = case greedySweep tasks taskMap ss of
        []    -> ss
        (ss':_) -> go (k-1) ss'

-- N2 → N5 → N7 expressed as a left fold over (budget, Neighborhood) pairs.
-- Each neighborhood runs to convergence before the next begins — N5 can
-- escape N2 local minima, N7 can escape N5 local minima.
-- This is the Yoneda pipeline in its purest form: composing natural
-- transformations over [] via foldl, with functor laws guaranteeing fusion.
refinementPipeline :: StepSelector -> [(Int, Neighborhood)] -> SearchState -> SearchState
refinementPipeline sel stages ss0 =
    foldl (\ss (maxIter, nbhd) -> convergeN sel maxIter nbhd ss) ss0 stages

-- ─────────────────────────────────────────────────────────────────────────────
-- N2 Neighborhood  (Nowicki & Smutnicki, 1996)
-- Swap adjacent critical pairs on the same machine.
-- Yoneda: liftYoneda wraps the candidate list; fmap evalCandidate composes
-- (O(1)); lowerYoneda traverses once; mapMaybe id filters lazily.
-- ─────────────────────────────────────────────────────────────────────────────

n2Neighborhood :: [TaskReq] -> Map.Map Int TaskReq -> Neighborhood
n2Neighborhood tasks taskMap ss =
    let graph0  = buildSolutionGraph tasks (ssOrder ss)
        slack0  = graphBasedSlack tasks graph0 (ssMS ss)
        critSet = Set.fromList [tid | (tid, s) <- Map.toList slack0, s == 0]
        rawCands = liftYoneda
                    [ (mId, swapAdjacent t1 t2 tl)
                    | (mId, tl) <- Map.toList (ssOrder ss)
                    , (t1, t2)  <- zip tl (drop 1 tl)
                    , Set.member t1 critSet || Set.member t2 critSet
                    ]
    in mapMaybe id . lowerYoneda $ fmap (evalCandidate tasks taskMap ss) rawCands

-- ─────────────────────────────────────────────────────────────────────────────
-- Shared helpers (reinsert / swap utilities used by N5 and N7)
-- ─────────────────────────────────────────────────────────────────────────────

-- Remove first occurrence of x from a list
removeElem :: Eq a => a -> [a] -> [a]
removeElem _ []                 = []
removeElem x (y:ys) | x == y   = ys
                    | otherwise = y : removeElem x ys

-- Insert `new` immediately after `anchor`; append if anchor not found
insertAfterElem :: Eq a => a -> a -> [a] -> [a]
insertAfterElem _ new []     = [new]
insertAfterElem anchor new (x:xs)
    | x == anchor = x : new : xs
    | otherwise   = x : insertAfterElem anchor new xs

-- Insert `new` immediately before `anchor`; prepend if anchor not found
insertBeforeElem :: Eq a => a -> a -> [a] -> [a]
insertBeforeElem _ new []     = [new]
insertBeforeElem anchor new (x:xs)
    | x == anchor = new : x : xs
    | otherwise   = x : insertBeforeElem anchor new xs

-- Recompute makespan from EST map (shared helper across passes)
makespanFromESTs :: Map.Map Int Int -> Map.Map Int TaskReq -> Int
makespanFromESTs ests taskMap =
    maximum (0 : [ est + duration (taskMap Map.! tid) | (tid, est) <- Map.toList ests ])

-- ─────────────────────────────────────────────────────────────────────────────
-- N5: Critical-Block Endpoint Rotation  (Nowicki & Smutnicki, 1996)
--
-- For every maximal run B = [b1, b2, ..., bk] (k ≥ 2) of tasks that are
-- ALL on the critical path AND all on the same machine:
--   • Rotate-front : move b1 to after  bk  → [b2, ..., bk, b1]
--   • Rotate-back  : move bk to before b1  → [bk, b1, ..., bk-1]
--
-- This tests whether the "bottleneck" at the front or back of the block can
-- be relieved by moving one endpoint through the algebraic arc reversal.
-- ─────────────────────────────────────────────────────────────────────────────

-- Maximal runs of ≥2 consecutive critical tasks on each machine
findCriticalBlocks :: Set.Set Int -> MachineOrder -> [(Int, [Int])]
findCriticalBlocks critSet machOrder =
    [ (mId, block)
    | (mId, taskList) <- Map.toList machOrder
    , block <- critRuns taskList
    , length block >= 2
    ]
  where
    critRuns [] = []
    critRuns xs =
        let prelude     = dropWhile (not . (`Set.member` critSet)) xs
            (run, rest) = span     (`Set.member` critSet) prelude
        in if null run then [] else run : critRuns rest

-- N5 Neighborhood: two Yoneda fmaps fused — descriptor → sequence → SearchState.
-- Step B (sequence construction) and Step C (evaluation) each add an O(1) fmap
-- to the continuation chain; lowerYoneda executes B∘C in a single traversal
-- of the raw descriptor list, never materialising an intermediate [(Int,[Int])].
n5Neighborhood :: [TaskReq] -> Map.Map Int TaskReq -> Neighborhood
n5Neighborhood tasks taskMap ss =
    let graph0  = buildSolutionGraph tasks (ssOrder ss)
        slack0  = graphBasedSlack tasks graph0 (ssMS ss)
        critSet = Set.fromList [tid | (tid, s) <- Map.toList slack0, s == 0]
        -- Step A: raw endpoint descriptors (mId, b1, bk, rotate-front?)
        rawCands = liftYoneda
            [ (mId, b1, bk, front)
            | (mId, block)  <- findCriticalBlocks critSet (ssOrder ss)
            -- findCriticalBlocks guarantees length ≥ 2; uncons is always Just here
            , Just (b1, _)  <- [List.uncons block]
            , Just (bk, _)  <- [List.uncons (reverse block)]
            , front <- [True, False]
            ]
        -- Step B (fmap, O(1)): build new machine sequence from descriptor
        seqCands = fmap (\(mId, b1, bk, front) ->
                       let fullSeq = ssOrder ss Map.! mId
                       in (mId, if front
                                then insertAfterElem  bk b1 (removeElem b1 fullSeq)
                                else insertBeforeElem b1 bk (removeElem bk fullSeq))
                   ) rawCands
        -- Step C (fmap, O(1)): evaluate; lowerYoneda applies B∘C in one pass
        evaluated = fmap (evalCandidate tasks taskMap ss) seqCands
    in mapMaybe id (lowerYoneda evaluated)

-- ─────────────────────────────────────────────────────────────────────────────
-- N7: Critical-Task Reinsertion
--
-- For every task t that lies on the critical path, on machine m with sequence S,
-- try inserting t at every other position in S.
-- This is the largest of the three neighbourhoods:
--   |candidates| = Σ_{m} |crit_m| × (|S_m| - 1)
-- where crit_m = critical tasks on machine m, |S_m| = machine queue length.
-- ─────────────────────────────────────────────────────────────────────────────

-- N7 Neighborhood: three-step Yoneda pipeline — descriptor → sequence → SearchState.
-- Steps B and C each add an O(1) fmap to the chain; lowerYoneda executes the full
-- B∘C composition in one traversal, never materialising an intermediate [(Int,[Int])].
-- Hard-bounded (≤500 candidates) to prevent O(n²) blowup on large instances (ta71).
n7Neighborhood :: [TaskReq] -> Map.Map Int TaskReq -> Neighborhood
n7Neighborhood tasks taskMap ss =
    let graph0   = buildSolutionGraph tasks (ssOrder ss)
        slacks0  = graphBasedSlack tasks graph0 (ssMS ss)
        critSet  = Set.fromList [tid | (tid, s) <- Map.toList slacks0, s == 0]
        queueLen = maximum (1 : map length (Map.elems (ssOrder ss)))
        maxCrit  = max 3 (20 `div` queueLen + 3)
        -- Step A: (mId, task, target-position) — bounded, lazy
        rawCands = liftYoneda $ take 500
            [ (mId, t, pos)
            | (mId, taskList) <- Map.toList (ssOrder ss)
            , let critOnMach = take maxCrit
                             $ List.sortBy (comparing (\t -> Map.findWithDefault 0 t slacks0))
                             $ filter (`Set.member` critSet) taskList
            , t <- critOnMach
            , let withoutT = removeElem t taskList
                  currPos  = length (takeWhile (/= t) taskList)
            , pos <- [0 .. length withoutT]
            , pos /= currPos
            ]
        -- Step B (fmap, O(1)): compute new sequence from reinsertion descriptor
        seqCands  = fmap (\(mId, t, pos) ->
                        let withoutT = removeElem t (ssOrder ss Map.! mId)
                        in (mId, take pos withoutT ++ [t] ++ drop pos withoutT)
                    ) rawCands
        -- Step C (fmap, O(1)): evaluate; lowerYoneda applies B∘C in one pass
        evaluated = fmap (evalCandidate tasks taskMap ss) seqCands
    in mapMaybe id (lowerYoneda evaluated)

-- ─────────────────────────────────────────────────────────────────────────────
-- Shifting Bottleneck Procedure  (Adams, Balas & Zawack 1988)
--
-- Decomposes JSSP into |M| single-machine subproblems 1|r_j|max(C_j + q_j).
-- Each subproblem is solved optimally with Carlier's branch-and-bound.
-- The SBP yields a significantly better initial solution than MWR+SPT,
-- giving the N2/N5/N7 pipeline a shorter distance to travel.
--
-- Single-machine model (per unscheduled machine M_k):
--   r_j = earliest start from the partial disjunctive graph (forward pass)
--   p_j = task duration
--   q_j = tail: longest path from end of j to the horizon (backward pass)
--   Objective: min max_j(C_j + q_j)  ≡  estimated JSSP makespan contribution
--
-- Carlier branching rule:
--   j* = bottleneck job  (argmax C_j + q_j in current Schrage schedule)
--   B  = critical block  (jobs scheduled during [r_{j*}, C_{j*}])
--   LB = r_{j*} + Σ_{k∈B} p_k + q_{j*}
--   For each k ∈ B \ {j*}: branch  r_{j*} ← max(r_{j*}, r_k + p_k)
--   (forcing k before j* eliminates the deadlock inside the block)
-- ─────────────────────────────────────────────────────────────────────────────

-- Job descriptor for 1|r_j|max(C_j+q_j) single-machine subproblems
data SMJob = SMJob
    { smjId :: Int
    , smjR  :: Int   -- release date
    , smjP  :: Int   -- processing time
    , smjQ  :: Int   -- tail (remaining work past completion)
    } deriving (Show, Eq)

-- Schrage (1984) greedy: among released jobs pick the one with the largest
-- tail q_j (break ties by id).  Complexity O(n log n).
-- Used both as the initial heuristic solution and as the subroutine that
-- computes the upper bound and branching info inside Carlier B&B.
schrageSM :: [SMJob] -> ([Int], Int)
schrageSM [] = ([], 0)
schrageSM jobs =
    let byRel = List.sortBy (comparing smjR) jobs
        jMap  = Map.fromList [(smjId j, j) | j <- jobs]
        -- Priority queue: key (−q_j, id) → Map.findMin extracts max-q job
        go t pend avail acc =
            let (rel, pend') = span (\j -> smjR j <= t) pend
                avail' = foldl (\m j -> Map.insert (negate (smjQ j), smjId j) j m)
                               avail rel
            in if Map.null avail'
               then case pend' of
                       []    -> reverse acc
                       (x:_) -> go (smjR x) pend' avail' acc
               else let ((_, _), j) = Map.findMin avail'
                        avail''     = Map.deleteMin avail'
                    in go (t + smjP j) pend' avail'' (smjId j : acc)
        order = go 0 byRel Map.empty []
        -- Recompute max(C_j + q_j) respecting release dates
        cmax = fst $ foldl (\(best, t) jid ->
                   let j  = jMap Map.! jid
                       st = max t (smjR j)
                       ct = st + smjP j
                   in (max best (ct + smjQ j), ct)) (0, 0) order
    in (order, cmax)

-- Actual start times for a scheduled sequence (machine free at t = 0)
smStarts :: [SMJob] -> [Int] -> Map.Map Int Int
smStarts jobs order =
    let jMap = Map.fromList [(smjId j, j) | j <- jobs]
    in snd $ foldl (\(t, m) jid ->
           let j  = jMap Map.! jid
               st = max t (smjR j)
           in (st + smjP j, Map.insert jid st m)) (0, Map.empty) order

-- Carlier B&B: exact solver for 1|r_j|max(C_j+q_j) with a node budget.
-- Returns the best schedule found within `maxNodes` B&B evaluations.
-- Using a budget (not a depth limit) is essential: the branching factor
-- varies with the critical-block size, so a fixed depth can explore
-- anywhere from 1 to n^depth nodes depending on tie structure.
-- Budget = 500 gives tight deterministic runtime; typical JSSP subproblems
-- are solved to optimality in << 500 nodes due to the Jackson LB being tight.
-- Falls back gracefully to Schrage when the budget runs out.
carlierBnB :: Int -> [SMJob] -> ([Int], Int)
carlierBnB _        [] = ([], 0)
carlierBnB maxNodes js = fst $ go maxNodes js ord0 ub0
  where
    (ord0, ub0) = schrageSM js

    -- Returns ((bestOrder, bestCmax), remainingBudget)
    go :: Int -> [SMJob] -> [Int] -> Int -> (([Int], Int), Int)
    go 0     _   bestOrd bestUB = ((bestOrd, bestUB), 0)
    go budget cur bestOrd bestUB =
        let jMap      = Map.fromList [(smjId j, j) | j <- cur]
            (ord, ub) = schrageSM cur
            starts    = smStarts cur ord
            jstar     = fst $ List.maximumBy (comparing snd)
                             [ let j  = jMap Map.! jid
                                   st = Map.findWithDefault 0 jid starts
                               in (jid, st + smjP j + smjQ j)
                             | jid <- ord ]
            jstarJ    = jMap Map.! jstar
            rStar     = smjR  jstarJ
            cStar     = Map.findWithDefault 0 jstar starts + smjP jstarJ
            block     = filter (\jid ->
                            let st = Map.findWithDefault 0 jid starts
                            in st >= rStar && st < cStar) ord
            lb        = rStar + sum [smjP (jMap Map.! k) | k <- block] + smjQ jstarJ
            (best', ub') = if ub < bestUB then (ord, ub) else (bestOrd, bestUB)
        in if lb >= ub'
           then ((best', ub'), budget)   -- LB ≥ UB: entire subtree provably no better
           else
               let branches  = [ map (\j -> if smjId j == jstar
                                             then j { smjR = max (smjR j)
                                                                (smjR (jMap Map.! k)
                                                                 + smjP (jMap Map.! k)) }
                                             else j) cur
                                | k <- filter (/= jstar) block ]
                   -- Thread the budget through all branches: each branch spends
                   -- from the remaining pool.  If budget runs to 0, subsequent
                   -- branches are skipped (budget=0 → immediate return).
                   ((finalOrd, finalUB), finalBudget) =
                       foldl (\((bo, bu), rem) bJs ->
                                  if rem <= 0 then ((bo, bu), 0)
                                  else go rem bJs bo bu)
                             ((best', ub'), budget - 1) branches
               in ((finalOrd, finalUB), finalBudget)

-- Forward pass on the partial schedule (all machines except `excl`).
-- Returns the release date r_j for every task in the JSSP.
releasesExcluding :: [TaskReq] -> MachineOrder -> Int -> Map.Map Int Int
releasesExcluding tasks machOrder excl =
    forwardPass tasks (buildSolutionGraph tasks (Map.delete excl machOrder))

-- Backward pass on the partial schedule (all machines except `excl`).
-- Returns tail q_j = longest path from the end of j to the horizon.
-- Computed via reverse topological order: q_j = max over successors s of
-- (duration_s + q_s), with q = 0 at every leaf (no outgoing arcs).
tailsExcluding :: [TaskReq] -> MachineOrder -> Int -> Map.Map Int Int
tailsExcluding tasks machOrder excl =
    let g       = buildSolutionGraph tasks (Map.delete excl machOrder)
        taskMap = Map.fromList [(id_t t, t) | t <- tasks]
        succMap = AM.adjacencyMap g
    in case Algo.topSort g of
         Left  _ -> Map.empty
         Right topoOrder ->
             foldl (\acc tid ->
                 let succs = maybe [] Set.toList (Map.lookup tid succMap)
                     q     = maximum (0 : [ duration (taskMap Map.! s)
                                           + Map.findWithDefault 0 s acc
                                          | s <- succs ])
                 in Map.insert tid q acc
             ) Map.empty (reverse topoOrder)

-- Solve the single-machine subproblem for machine `mId` given the current
-- partial schedule.  Returns (optimal ordering, Cmax estimate).
-- Uses pure Schrage (budget=0) — confirmed to already find locally-optimal
-- solutions for standard JSSP subproblems (the Jackson LB equals the Schrage
-- UB on the first node, so B&B produces no improvement but adds runtime).
-- Quality improvement comes from the SBP convergence loop, not B&B depth.
sbpOneMachine :: [TaskReq] -> MachineOrder -> Int -> ([Int], Int)
sbpOneMachine tasks machOrder mId =
    let rels   = releasesExcluding tasks machOrder mId
        tls    = tailsExcluding    tasks machOrder mId
        smJobs = [ SMJob (id_t t)
                         (Map.findWithDefault 0 (id_t t) rels)
                         (duration t)
                         (Map.findWithDefault 0 (id_t t) tls)
                 | t <- tasks, machine_id t == mId ]
    in carlierBnB 0 smJobs

-- Shifting Bottleneck main loop.
-- At each iteration: solve all unscheduled machines, pick the bottleneck
-- (highest Cmax estimate), fix its ordering, then do a SINGLE re-optimisation
-- pass over all previously scheduled machines under the new constraints.
--
-- Note on convergence: the textbook SBP (Adams et al. 1988) iterates the
-- re-opt pass until no sequence changes (fixed point).  We do NOT do that
-- here because each SBP call rebuilds the full algebraic-graphs disjunctive
-- graph (O((V+E) log V)); for a 20-machine instance that's O(2400) graph
-- builds over 6 convergence rounds, which is too expensive.  Single-pass is
-- fast and already delivers la01=666 (optimal) and strong seeds for N2/N5/N7.
shiftingBottleneck :: [TaskReq] -> MachineOrder
shiftingBottleneck tasks = go [] (List.nub [machine_id t | t <- tasks]) Map.empty
  where
    go _         []          machOrder = machOrder
    go scheduled unscheduled machOrder =
        let cands = [(m, sbpOneMachine tasks machOrder m) | m <- unscheduled]
            (bottleneck, (bSeq, _)) =
                List.maximumBy (comparing (snd . snd)) cands
            mo1 = Map.insert bottleneck bSeq machOrder
            -- Single re-optimisation pass over previously scheduled machines
            mo2 = foldl (\mo m ->
                      let (seq', _) = sbpOneMachine tasks mo m
                      in Map.insert m seq' mo) mo1 scheduled
        in go (bottleneck : scheduled)
              (filter (/= bottleneck) unscheduled)
              mo2

-- ─────────────────────────────────────────────────────────────────────────────
-- N2 → N5 → N7 as a foldl over the Neighborhood pipeline
refineBottlenecks :: [TaskReq] -> Map.Map Int Int -> Int -> (Map.Map Int Int, Int)
refineBottlenecks tasks initialStarts initialMakespan =
    let taskMap = Map.fromList [(id_t t, t) | t <- tasks]
        n       = length tasks
        iter2   = max 5 (100 `div` max 1 (n `div` 100))
        iter5   = max 5 (100 `div` max 1 (n `div` 100))
        iter7   = max 3 ( 30 `div` max 1 (n `div` 100))
        sel     = if n > 500 then firstImprovementSel else steepestDescent
        ss0     = initSearchState tasks initialStarts initialMakespan
        -- N2: greedy carry-forward for small/medium, first-improvement for large
        -- This restores the old trySwaps behavior that found la01=666 (optimal):
        -- dependent swaps (A must happen before B becomes valid) are found in
        -- one sweep because the state is updated immediately after each improvement.
        ss2     = if n > 500
                  then convergeN firstImprovementSel iter2 (n2Neighborhood tasks taskMap) ss0
                  else convergeGreedy iter2 tasks taskMap ss0
        -- N5 and N7: convergeN with the appropriate selector
        ss      = refinementPipeline sel
                    [ (iter5, n5Neighborhood tasks taskMap)
                    , (iter7, n7Neighborhood tasks taskMap)
                    ] ss2
    in (ssESTs ss, ssMS ss)

-- Heurística completa com análise e refinamento
-- Returns: (hints, mwrMakespan, sbpMakespan, refinedMakespan, slacks, criticalPath)
solveWithRefinement :: [TaskReq] -> (Map.Map Int Int, Int, Int, Int, Map.Map Int Int, [Int])
solveWithRefinement tasks =
    let taskMap' = Map.fromList [(id_t t, t) | t <- tasks]

        -- Phase 1a: MWR+SPT — fast baseline, reported as makespan_heuristic
        (mwrStarts, mwrMakespan) = solveHeuristic tasks

        -- Phase 1b: Shifting Bottleneck — exact single-machine decomposition;
        -- converts machine orderings to start times via forward pass
        sbpOrder = shiftingBottleneck tasks
        sbpESTs  = forwardPass tasks (buildSolutionGraph tasks sbpOrder)
        sbpMS    = makespanFromESTs sbpESTs taskMap'

        -- Start Phase 2 from whichever Phase 1 result is better
        (startStarts, startMS) =
            if sbpMS < mwrMakespan then (sbpESTs, sbpMS) else (mwrStarts, mwrMakespan)

        -- Phase 2: N2/N5/N7 neighbourhood refinement on the disjunctive graph
        (refinedStarts, refinedMakespan) = refineBottlenecks tasks startStarts startMS

        -- Phase 3: bottleneck analysis on the refined solution
        machOrder    = machineOrderFromStarts tasks refinedStarts
        graph        = buildSolutionGraph tasks machOrder
        slacks       = graphBasedSlack tasks graph refinedMakespan
        criticalPath = [tid | (tid, s) <- Map.toList slacks, s == 0]

    in (refinedStarts, mwrMakespan, sbpMS, refinedMakespan, slacks, criticalPath)

main :: IO ()
main = scotty 3000 $ do
    post "/validate" $ do
        tasks <- jsonData :: ActionM [TaskReq]
        let adjMap = AM.stars [ (id_t t, maybe [] (\n -> [n]) (next_t t)) | t <- tasks ]
        
        if Algo.isAcyclic adjMap
            then do
                let (hints, hMakespan, sbpMakespan, refinedMakespan, slacks, criticalPath) = solveWithRefinement tasks
                    machineUtil = analyzeMachineUtilization tasks hints refinedMakespan
                    criticalMachines = Map.keys $ Map.filter (> 0.85) machineUtil

                json $ object [ "status" .= ("ok" :: String)
                              , "valid"  .= True
                              , "hints"  .= hints
                              , "makespan_heuristic" .= hMakespan
                              , "makespan_sbp"        .= sbpMakespan
                              , "makespan_refined"   .= refinedMakespan
                              , "slacks" .= slacks
                              , "critical_path" .= criticalPath
                              , "critical_machines" .= criticalMachines
                              , "machine_utilization" .= machineUtil
                              ]
            else json $ object [ "status" .= ("erro" :: String)
                               , "valid"  .= False
                               , "msg"    .= ("Ciclo detectado!" :: String) ]
