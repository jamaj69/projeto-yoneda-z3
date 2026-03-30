#!/usr/bin/env python3
"""
Solve JSSP using Google OR-Tools CP-SAT solver.
"""

import sys
import time
from typing import Dict, List, Tuple
from ortools.sat.python import cp_model
from instance_loader import parse_jssp_file


class SolutionPrinter(cp_model.CpSolverSolutionCallback):
    """Print intermediate solutions during search."""
    
    def __init__(self, makespan_var):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self._makespan = makespan_var
        self._solution_count = 0
        self._start_time = time.time()
    
    def on_solution_callback(self):
        current_time = time.time() - self._start_time
        self._solution_count += 1
        makespan = self.Value(self._makespan)
        print(f"   Solution {self._solution_count}: makespan = {makespan}h (time: {current_time:.2f}s)")


def solve_jssp_ortools(
    instance_path: str,
    time_limit_seconds: int = 300,
    verbose: bool = True
) -> Tuple[bool, int, Dict]:
    """
    Solve JSSP using OR-Tools CP-SAT.
    
    Returns:
        (success, makespan, solution_dict)
    """
    # Parse instance
    num_jobs, num_machines, jobs = parse_jssp_file(instance_path)
    
    if verbose:
        print(f"📋 Instance: {num_jobs} jobs × {num_machines} machines")
        print(f"⏱️  Time limit: {time_limit_seconds}s")
        print()
    
    # Create model
    model = cp_model.CpModel()
    
    # Compute horizon (upper bound on makespan)
    horizon = sum(duration for job in jobs for _, duration in job)
    if verbose:
        print(f"🔢 Horizon (sum of all durations): {horizon}")
    
    # Variables
    # task_starts[job_id][task_idx] = start time
    task_starts = {}
    task_ends = {}
    task_intervals = {}
    
    for job_id, job in enumerate(jobs):
        task_starts[job_id] = []
        task_ends[job_id] = []
        task_intervals[job_id] = []
        
        for task_idx, (machine, duration) in enumerate(job):
            suffix = f'_j{job_id}_t{task_idx}'
            
            start_var = model.NewIntVar(0, horizon, 'start' + suffix)
            end_var = model.NewIntVar(0, horizon, 'end' + suffix)
            interval_var = model.NewIntervalVar(start_var, duration, end_var, 'interval' + suffix)
            
            task_starts[job_id].append(start_var)
            task_ends[job_id].append(end_var)
            task_intervals[job_id].append((machine, interval_var))
    
    # Precedence constraints: tasks within a job must be sequential
    if verbose:
        print(f"📐 Adding precedence constraints...")
    
    for job_id, job in enumerate(jobs):
        for task_idx in range(len(job) - 1):
            model.Add(task_starts[job_id][task_idx + 1] >= task_ends[job_id][task_idx])
    
    # Machine constraints: no two tasks on same machine can overlap
    if verbose:
        print(f"🏭 Adding machine no-overlap constraints...")
    
    machine_to_intervals = {}
    for job_id in range(num_jobs):
        for machine, interval in task_intervals[job_id]:
            if machine not in machine_to_intervals:
                machine_to_intervals[machine] = []
            machine_to_intervals[machine].append(interval)
    
    for machine, intervals in machine_to_intervals.items():
        model.AddNoOverlap(intervals)
    
    # Objective: minimize makespan
    makespan = model.NewIntVar(0, horizon, 'makespan')
    model.AddMaxEquality(makespan, [
        task_ends[job_id][-1] 
        for job_id in range(num_jobs)
    ])
    model.Minimize(makespan)
    
    if verbose:
        print(f"🎯 Objective: minimize makespan")
        print()
        print(f"🔍 Solving with OR-Tools CP-SAT...")
    
    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.log_search_progress = verbose
    
    solution_printer = SolutionPrinter(makespan) if verbose else None
    
    start_time = time.time()
    status = solver.Solve(model, solution_printer)
    solve_time = time.time() - start_time
    
    # Process results
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solution_makespan = solver.Value(makespan)
        
        # Extract schedule
        schedule = {}
        for job_id in range(num_jobs):
            schedule[job_id] = []
            for task_idx, (machine, duration) in enumerate(jobs[job_id]):
                start = solver.Value(task_starts[job_id][task_idx])
                end = solver.Value(task_ends[job_id][task_idx])
                schedule[job_id].append({
                    'task_idx': task_idx,
                    'machine': machine,
                    'duration': duration,
                    'start': start,
                    'end': end
                })
        
        if verbose:
            print()
            print(f"{'='*60}")
            if status == cp_model.OPTIMAL:
                print(f"✅ OPTIMAL SOLUTION FOUND")
            else:
                print(f"✅ FEASIBLE SOLUTION FOUND")
            print(f"{'='*60}")
            print(f"📊 Makespan: {solution_makespan}h")
            print(f"⏱️  Solve time: {solve_time:.2f}s")
            print(f"🔢 Branches: {solver.NumBranches()}")
            print(f"⚡ Conflicts: {solver.NumConflicts()}")
            print()
        
        return True, solution_makespan, schedule
    
    elif status == cp_model.INFEASIBLE:
        if verbose:
            print()
            print(f"❌ INFEASIBLE - No solution exists")
        return False, 0, {}
    
    else:  # UNKNOWN
        if verbose:
            print()
            print(f"⏱️  TIME LIMIT REACHED")
            print(f"⏱️  Solve time: {solve_time:.2f}s")
            if solver.BestObjectiveBound() < float('inf'):
                print(f"🔢 Best bound found: {solver.BestObjectiveBound()}")
        return False, 0, {}


def write_solution_file(
    instance_name: str,
    num_jobs: int,
    num_machines: int,
    makespan: int,
    schedule: Dict,
    output_path: str
):
    """Write solution to enhanced .sol file format with start times."""
    
    # For each machine, collect tasks with start times
    machine_tasks = [[] for _ in range(num_machines)]
    for job_id, tasks in schedule.items():
        for task in tasks:
            machine_tasks[task['machine']].append({
                'job_id': job_id,
                'task_idx': task['task_idx'],
                'start': task['start'],
                'duration': task['duration'],
                'end': task['end']
            })
    
    # Sort by start time
    for machine in range(num_machines):
        machine_tasks[machine].sort(key=lambda t: t['start'])
    
    # Write file (convert to 1-indexed jobs for solution format)
    with open(output_path, 'w') as f:
        f.write(f"Problem: {instance_name}\n")
        f.write(f"Number of jobs: {num_jobs}\n")
        f.write(f"Number of machines: {num_machines}\n")
        f.write(f"Makespan: {makespan}\n\n")
        
        # Write detailed schedule with start times
        f.write(f"Schedule (Job Task Machine Start Duration End):\n")
        all_tasks = []
        for job_id, tasks in schedule.items():
            for task in tasks:
                all_tasks.append({
                    'job_id': job_id,
                    'task_idx': task['task_idx'],
                    'machine': task['machine'],
                    'start': task['start'],
                    'duration': task['duration'],
                    'end': task['end']
                })
        all_tasks.sort(key=lambda t: (t['start'], t['machine']))
        
        for task in all_tasks:
            f.write(f"{task['job_id'] + 1} {task['task_idx']} {task['machine']} "
                   f"{task['start']} {task['duration']} {task['end']}\n")
        
        f.write(f"\n")
        f.write(f"Machine sequences (for reference):\n")
        for machine_id, tasks in enumerate(machine_tasks):
            job_seq = [t['job_id'] + 1 for t in tasks]
            f.write(f"Machine {machine_id}: {' '.join(map(str, job_seq))}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python solve_ortools.py <instance.txt> [time_limit_seconds] [output.sol]")
        sys.exit(1)
    
    instance_path = sys.argv[1]
    time_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    output_path = sys.argv[3] if len(sys.argv) > 3 else None
    
    import os
    instance_name = os.path.basename(instance_path).replace('.txt', '')
    
    print(f"{'='*60}")
    print(f"OR-Tools CP-SAT Solver for JSSP")
    print(f"{'='*60}")
    print(f"Instance: {instance_path}")
    print()
    
    success, makespan, schedule = solve_jssp_ortools(
        instance_path,
        time_limit_seconds=time_limit,
        verbose=True
    )
    
    if success and output_path:
        num_jobs, num_machines, _ = parse_jssp_file(instance_path)
        write_solution_file(
            instance_name,
            num_jobs,
            num_machines,
            makespan,
            schedule,
            output_path
        )
        print(f"💾 Solution saved to: {output_path}")
        print()
        print(f"To validate: python script-python/validate_solution.py {instance_path} {output_path}")
