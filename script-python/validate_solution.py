#!/usr/bin/env python3
"""
Validate a JSSP solution file and calculate makespan.
"""

import sys
from typing import Dict, List, Tuple, Optional
from instance_loader import parse_jssp_file


def parse_solution_file(sol_path: str) -> Tuple[Optional[int], List[List[int]], Dict]:
    """Parse a .sol file. Supports both old format (sequences only) and new format (with start times).
    
    Returns:
        (claimed_makespan, machine_sequences, explicit_schedule)
        where explicit_schedule is Dict[(job_id, task_idx)] -> (start, duration, end) or empty dict
    """
    with open(sol_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    claimed_makespan = None
    machine_sequences = []
    explicit_schedule = {}  # (job_id, task_idx) -> (start, duration, end)
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        if line.startswith('Makespan:'):
            claimed_makespan = int(line.split(':')[1].strip())
        
        elif line.startswith('Schedule (Job Task Machine Start Duration End):'):
            # New format with explicit start times
            i += 1
            while i < len(lines) and not lines[i].startswith('Machine sequences'):
                parts = lines[i].split()
                if len(parts) == 6:
                    job_id = int(parts[0]) - 1  # Convert from 1-indexed to 0-indexed
                    task_idx = int(parts[1])
                    machine = int(parts[2])
                    start = int(parts[3])
                    duration = int(parts[4])
                    end = int(parts[5])
                    explicit_schedule[(job_id, task_idx)] = (start, duration, end, machine)
                i += 1
            continue
        
        elif line == 'Solution sequence:':
            # Old format: read all machine sequences
            i += 1
            while i < len(lines):
                jobs = list(map(int, lines[i].split()))
                machine_sequences.append(jobs)
                i += 1
            break
        
        elif line.startswith('Machine ') and ':' in line:
            # New format machine sequences (for reference only)
            pass
        
        i += 1
    
    return claimed_makespan, machine_sequences, explicit_schedule


def validate_explicit_schedule(
    num_jobs: int,
    num_machines: int,
    jobs: List[List[Tuple[int, int]]],
    claimed_makespan: int,
    explicit_schedule: Dict[Tuple[int, int], Tuple[int, int, int, int]],
    errors: List[str]
) -> Tuple[bool, int, List[str]]:
    """Validate a solution with explicit start times."""
    
    # Check all tasks are present
    for job_id in range(num_jobs):
        for task_idx in range(len(jobs[job_id])):
            if (job_id, task_idx) not in explicit_schedule:
                errors.append(f"Job {job_id + 1} task {task_idx} not in schedule")
    
    # Check precedence constraints
    for job_id in range(num_jobs):
        for task_idx in range(1, len(jobs[job_id])):
            curr_key = (job_id, task_idx)
            prev_key = (job_id, task_idx - 1)
            
            if curr_key not in explicit_schedule or prev_key not in explicit_schedule:
                continue
            
            curr_start, curr_dur, curr_end, curr_machine = explicit_schedule[curr_key]
            prev_start, prev_dur, prev_end, prev_machine = explicit_schedule[prev_key]
            
            if curr_start < prev_end:
                errors.append(
                    f"Job {job_id + 1}: task {task_idx} starts at {curr_start} "
                    f"before task {task_idx - 1} ends at {prev_end}"
                )
    
    # Check machine non-overlap constraints
    machine_tasks = {}
    for (job_id, task_idx), (start, duration, end, machine) in explicit_schedule.items():
        if machine not in machine_tasks:
            machine_tasks[machine] = []
        machine_tasks[machine].append((start, end, job_id, task_idx))
    
    for machine, tasks in machine_tasks.items():
        sorted_tasks = sorted(tasks)
        for i in range(len(sorted_tasks) - 1):
            curr = sorted_tasks[i]
            next_task = sorted_tasks[i + 1]
            if next_task[0] < curr[1]:  # next starts before curr ends
                errors.append(
                    f"Machine {machine}: job {curr[2] + 1} task {curr[3]} ends at {curr[1]}, "
                    f"but job {next_task[2] + 1} task {next_task[3]} starts at {next_task[0]}"
                )
    
    # Check task durations match instance
    for (job_id, task_idx), (start, duration, end, machine) in explicit_schedule.items():
        expected_machine, expected_duration = jobs[job_id][task_idx]
        
        if machine != expected_machine:
            errors.append(
                f"Job {job_id + 1} task {task_idx}: scheduled on machine {machine}, "
                f"but should be on machine {expected_machine}"
            )
        
        if duration != expected_duration:
            errors.append(
                f"Job {job_id + 1} task {task_idx}: duration {duration}, "
                f"but should be {expected_duration}"
            )
        
        if end != start + duration:
            errors.append(
                f"Job {job_id + 1} task {task_idx}: end time {end} != start {start} + duration {duration}"
            )
    
    # Calculate actual makespan
    if explicit_schedule:
        actual_makespan = max(end for _, _, end, _ in explicit_schedule.values())
    else:
        actual_makespan = 0
        errors.append("No tasks in schedule")
    
    # Compare with claimed makespan
    if claimed_makespan is not None and claimed_makespan != actual_makespan:
        errors.append(f"Claimed makespan {claimed_makespan} != actual {actual_makespan}")
    
    is_valid = len(errors) == 0
    return is_valid, actual_makespan, errors


def validate_and_calculate_makespan(
    instance_path: str,
    sol_path: str
) -> Tuple[bool, int, List[str]]:
    """
    Validate solution and calculate actual makespan.
    
    Returns:
        (is_valid, actual_makespan, error_messages)
    """
    # Parse instance
    num_jobs, num_machines, jobs = parse_jssp_file(instance_path)
    
    # Parse solution
    claimed_makespan, machine_sequences, explicit_schedule = parse_solution_file(sol_path)
    
    errors = []
    
    # If we have explicit schedule with start times, validate that directly
    if explicit_schedule:
        return validate_explicit_schedule(
            num_jobs, num_machines, jobs, claimed_makespan, explicit_schedule, errors
        )
    
    # Otherwise, fall back to sequence-based validation
    # Validation 1: Check number of machines
    if len(machine_sequences) != num_machines:
        errors.append(f"Wrong number of machines: expected {num_machines}, got {len(machine_sequences)}")
        return False, 0, errors
    
    # Build job task info: job_id -> [(machine, duration, task_idx), ...]
    job_tasks: Dict[int, List[Tuple[int, int, int]]] = {}
    for job_id, job in enumerate(jobs):
        tasks = []
        for task_idx, (machine, duration) in enumerate(job):
            tasks.append((machine, duration, task_idx))
        job_tasks[job_id] = tasks
    
    # Build list of all tasks with their machine assignments
    all_tasks = []  # [(job_id, task_idx, machine, duration)]
    for job_id, job in enumerate(jobs):
        for task_idx, (machine, duration) in enumerate(job):
            all_tasks.append((job_id, task_idx, machine, duration))
    
    # Build machine sequences mapping: (machine, position) -> (job_id, task_idx, duration)
    machine_task_order = {}  # machine -> [(job_id, task_idx, duration)]
    
    for machine_id, job_sequence in enumerate(machine_sequences):
        machine_task_order[machine_id] = []
        for job_id_in_file in job_sequence:
            job_id = job_id_in_file - 1
            
            if job_id < 0 or job_id >= num_jobs:
                errors.append(f"Invalid job ID {job_id_in_file} on machine {machine_id} (expected 1-{num_jobs})")
                continue
            
            # Find which task of this job uses this machine
            job_task_list = job_tasks[job_id]
            matching_task = None
            for task_idx, (task_machine, duration, _) in enumerate(job_task_list):
                if task_machine == machine_id:
                    matching_task = (task_idx, duration)
                    break
            
            if matching_task is None:
                errors.append(f"Job {job_id + 1} has no task on machine {machine_id}")
                continue
            
            task_idx, duration = matching_task
            machine_task_order[machine_id].append((job_id, task_idx, duration))
    
    # Schedule tasks: compute start/end times respecting machine order and precedence
    task_start_times = {}  # (job_id, task_idx) -> start_time
    task_end_times = {}    # (job_id, task_idx) -> end_time
    machine_current_time = {m: 0 for m in range(num_machines)}
    
    # Process each machine's sequence
    for machine_id, task_list in machine_task_order.items():
        for job_id, task_idx, duration in task_list:
            # Earliest start due to machine availability  
            machine_available = machine_current_time[machine_id]
            
            # Earliest start due to precedence (previous task in job)
            precedence_available = 0
            if task_idx > 0:
                prev_key = (job_id, task_idx - 1)
                if prev_key in task_end_times:
                    precedence_available = task_end_times[prev_key]
                # If predecessor not scheduled yet, we'll catch it in validation below
            
            # Actual start time
            start_time = max(machine_available, precedence_available)
            end_time = start_time + duration
            
            task_start_times[(job_id, task_idx)] = start_time
            task_end_times[(job_id, task_idx)] = end_time
            machine_current_time[machine_id] = end_time
    
    # Validate precedence constraints
    for job_id in range(num_jobs):
        for task_idx in range(1, len(job_tasks[job_id])):
            curr_key = (job_id, task_idx)
            prev_key = (job_id, task_idx - 1)
            
            if curr_key not in task_start_times:
                errors.append(f"Job {job_id + 1} task {task_idx} not scheduled")
                continue
            
            if prev_key not in task_end_times:
                errors.append(f"Job {job_id + 1} task {task_idx} scheduled but task {task_idx - 1} not scheduled")
                continue
            
            if task_start_times[curr_key] < task_end_times[prev_key]:
                errors.append(
                    f"Job {job_id + 1}: task {task_idx} starts at {task_start_times[curr_key]} "
                    f"before task {task_idx - 1} ends at {task_end_times[prev_key]}"
                )
    
    # Calculate actual makespan
    if task_end_times:
        actual_makespan = max(task_end_times.values())
    else:
        actual_makespan = 0
        errors.append("No tasks were scheduled")
    
    # Compare with claimed makespan
    if claimed_makespan is not None and claimed_makespan != actual_makespan:
        errors.append(f"Claimed makespan {claimed_makespan} != actual {actual_makespan}")
    
    is_valid = len(errors) == 0
    
    return is_valid, actual_makespan, errors


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python validate_solution.py <instance.txt> <solution.sol>")
        sys.exit(1)
    
    instance_path = sys.argv[1]
    solution_path = sys.argv[2]
    
    print(f"═════════════════════════════════════════════════════")
    print(f"Validating Solution")
    print(f"═════════════════════════════════════════════════════")
    print(f"Instance: {instance_path}")
    print(f"Solution: {solution_path}")
    print()
    
    is_valid, makespan, errors = validate_and_calculate_makespan(instance_path, solution_path)
    
    if is_valid:
        print(f"✅ VALID SOLUTION")
        print(f"📊 Makespan: {makespan}")
    else:
        print(f"❌ INVALID SOLUTION")
        print(f"📊 Calculated Makespan: {makespan}")
        print(f"\n🔍 Errors found:")
        for i, error in enumerate(errors, 1):
            print(f"   {i}. {error}")
        sys.exit(1)
