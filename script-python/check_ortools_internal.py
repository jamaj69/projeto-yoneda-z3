#!/usr/bin/env python3
"""
Check if OR-Tools solution is internally consistent.
"""

import sys
from instance_loader import parse_jssp_file
from solve_ortools import solve_jssp_ortools

if len(sys.argv) < 2:
    print("Usage: python check_ortools_internal.py <instance.txt> [time_limit]")
    sys.exit(1)

instance_path = sys.argv[1]
time_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 60

num_jobs, num_machines, jobs = parse_jssp_file(instance_path)

print(f"Solving {instance_path}...")
success, makespan, schedule = solve_jssp_ortools(instance_path, time_limit, verbose=False)

if not success:
    print("No solution found")
    sys.exit(1)

print(f"\nORTools reported makespan: {makespan}")

# Check precedence in the extracted schedule
print("\nChecking precedence constraints in OR-Tools schedule...")
precedence_violations = []

for job_id, tasks in schedule.items():
    # Sort by task index
    sorted_tasks = sorted(tasks, key=lambda t: t['task_idx'])
    
    for i in range(len(sorted_tasks) - 1):
        curr = sorted_tasks[i]
        next_task = sorted_tasks[i + 1]
        
        # Next task should start after current ends
        if next_task['start'] < curr['end']:
            precedence_violations.append(
                f"Job {job_id}: task {curr['task_idx']} ends at {curr['end']}, "
                f"but task {next_task['task_idx']} starts at {next_task['start']}"
            )

if precedence_violations:
    print(f"❌ Found {len(precedence_violations)} precedence violations:")
    for violation in precedence_violations[:10]:
        print(f"   - {violation}")
else:
    print(f"✅ No precedence violations in OR-Tools internal schedule!")

# Calculate actual makespan
actual_makespan = max(task['end'] for tasks in schedule.values() for task in tasks)
print(f"\nCalculated makespan from schedule: {actual_makespan}")

if actual_makespan == makespan:
    print("✅  Makespan matches OR-Tools report")
else:
    print(f"❌ Makespan mismatch: OR-Tools says {makespan}, calculated {actual_makespan}")
