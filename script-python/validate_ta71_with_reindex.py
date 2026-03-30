#!/usr/bin/env python3
"""
Test if ta71.sol is valid if we adjust for 0-indexed vs 1-indexed job IDs.
"""

import sys
from typing import Dict, List, Tuple
from instance_loader import parse_jssp_file


def validate_solution_0indexed(instance_path: str, sol_path: str):
    """Validate ta71.sol assuming job IDs are 0-indexed (0-99)."""
    
    # Parse instance
    num_jobs, num_machines, jobs = parse_jssp_file(instance_path)
    
    # Parse solution file manually
    with open(sol_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    claimed_makespan = None
    machine_sequences = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        if line.startswith('Makespan:'):
            claimed_makespan = int(line.split(':')[1].strip())
        
        elif line == 'Solution sequence:':
            # Read all machine sequences
            i += 1
            while i < len(lines):
                jobs_on_machine = list(map(int, lines[i].split()))
                machine_sequences.append(jobs_on_machine)
                i += 1
            break
        
        i += 1
    
    print(f"📊 Claimed makespan: {claimed_makespan}")
    print(f"📊 Num machines: {len(machine_sequences)}")
    print(f"📊 Num jobs in instance: {num_jobs}")
    print()
    
    # Check if job IDs are 0-indexed (0-99) or 1-indexed (1-100)
    all_job_ids = set()
    for seq in machine_sequences:
        all_job_ids.update(seq)
    
    min_id = min(all_job_ids)
    max_id = max(all_job_ids)
    
    print(f"📊 Job IDs in solution: {min_id} to {max_id}")
    print(f"📊 Expected range: 0 to {num_jobs - 1} (0-indexed) OR 1 to {num_jobs} (1-indexed)")
    print()
    
    # Treat as 0-indexed
    errors = []
    
    # Build job task info: job_id -> [(machine, duration, task_idx), ...]
    job_tasks: Dict[int, List[Tuple[int, int, int]]] = {}
    for job_id, job in enumerate(jobs):
        tasks = []
        for task_idx, (machine, duration) in enumerate(job):
            tasks.append((machine, duration, task_idx))
        job_tasks[job_id] = tasks
    
    # Build machine sequences mapping
    machine_task_order = {}  # machine -> [(job_id, task_idx, duration)]
    
    for machine_id, job_sequence in enumerate(machine_sequences):
        machine_task_order[machine_id] = []
        for job_id_in_file in job_sequence:
            # TREAT AS 0-INDEXED (no conversion)
            job_id = job_id_in_file
            
            if job_id < 0 or job_id >= num_jobs:
                errors.append(f"Invalid job ID {job_id_in_file} on machine {machine_id} (expected 0-{num_jobs-1})")
                continue
            
            # Find which task of this job uses this machine
            job_task_list = job_tasks[job_id]
            matching_task = None
            for idx, (task_machine, duration, task_idx_orig) in enumerate(job_task_list):
                if task_machine == machine_id:
                    matching_task = (task_idx_orig, duration)
                    break
            
            if matching_task is None:
                errors.append(f"Job {job_id} has no task on machine {machine_id}")
                continue
            
            task_idx, duration = matching_task
            machine_task_order[machine_id].append((job_id, task_idx, duration))
    
    # Schedule tasks
    task_start_times = {}
    task_end_times = {}
    machine_current_time = {m: 0 for m in range(num_machines)}
    
    for machine_id, task_list in machine_task_order.items():
        for job_id, task_idx, duration in task_list:
            machine_available = machine_current_time[machine_id]
            
            precedence_available = 0
            if task_idx > 0:
                prev_key = (job_id, task_idx - 1)
                if prev_key in task_end_times:
                    precedence_available = task_end_times[prev_key]
            
            start_time = max(machine_available, precedence_available)
            end_time = start_time + duration
            
            task_start_times[(job_id, task_idx)] = start_time
            task_end_times[(job_id, task_idx)] = end_time
            machine_current_time[machine_id] = end_time
    
    # Validate precedence constraints
    for job_id in range(num_jobs):
        for task_idx in range(len(jobs[job_id]) - 1):
            curr_key = (job_id, task_idx)
            next_key = (job_id, task_idx + 1)
            
            if curr_key in task_end_times and next_key in task_start_times:
                if task_start_times[next_key] < task_end_times[curr_key]:
                    errors.append(
                        f"Job {job_id}: task {task_idx + 1} starts at {task_start_times[next_key]} "
                        f"before task {task_idx} ends at {task_end_times[curr_key]}"
                    )
    
    # Calculate makespan
    actual_makespan = max(task_end_times.values()) if task_end_times else 0
    
    print(f"✅ Validation results:")
    print(f"   Actual makespan: {actual_makespan}")
    print(f"   Claimed makespan: {claimed_makespan}")
    print(f"   Difference: {actual_makespan - claimed_makespan if claimed_makespan else 'N/A'}")
    print()
    
    if errors:
        print(f"❌ Found {len(errors)} errors:")
        for i, error in enumerate(errors[:20], 1):
            print(f"   {i}. {error}")
        if len(errors) > 20:
            print(f"   ... and {len(errors) - 20} more errors")
    else:
        print("✅ No constraint violations found!")
    
    return len(errors) == 0, actual_makespan


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python validate_ta71_with_reindex.py <instance_file> <solution_file>")
        sys.exit(1)
    
    is_valid, makespan = validate_solution_0indexed(sys.argv[1], sys.argv[2])
    
    if is_valid:
        print("\n🎉 Solution is VALID with makespan", makespan)
        sys.exit(0)
    else:
        print("\n❌ Solution is INVALID")
        sys.exit(1)
