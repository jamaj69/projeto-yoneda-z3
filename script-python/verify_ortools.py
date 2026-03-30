#!/usr/bin/env python3
"""
Verify OR-Tools internal solution respects all constraints.
"""

import sys
from instance_loader import parse_jssp_file
from solve_ortools import solve_jssp_ortools

instance_path = sys.argv[1] if len(sys.argv) > 1 else "instances/Taillard1993/ta71js.txt"
time_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 60

print(f"Solving {instance_path}...")
success, makespan, schedule = solve_jssp_ortools(instance_path, time_limit, verbose=False)

if not success:
    print("No solution found")
    sys.exit(1)

print(f"\n✅ OR-Tools reported makespan: {makespan}")

# Check precedence in OR-Tools internal solution
print("\n🔍 Checking precedence constraints in OR-Tools solution...")
prec_violations = []

for job_id, tasks in schedule.items():
    sorted_tasks = sorted(tasks, key=lambda t: t['task_idx'])
    
    for i in range(len(sorted_tasks) - 1):
        curr = sorted_tasks[i]
        next_task = sorted_tasks[i + 1]
        
        # Next task should start after current ends
        if next_task['start'] < curr['end']:
            prec_violations.append(
                f"Job {job_id + 1}: task {curr['task_idx']} (m{curr['machine']}) ends at {curr['end']}, "
                f"but task {next_task['task_idx']} (m{next_task['machine']}) starts at {next_task['start']}"
            )

if prec_violations:
    print(f"❌ Found {len(prec_violations)} precedence violations in OR-Tools solution:")
    for v in prec_violations[:10]:
        print(f"   - {v}")
else:
    print("✅ No precedence violations in OR-Tools solution!")

# Check machine overlaps
print("\n🔍 Checking machine non-overlap constraints...")
machine_tasks = {}
for job_id, tasks in schedule.items():
    for task in tasks:
        m = task['machine']
        if m not in machine_tasks:
            machine_tasks[m] = []
        machine_tasks[m].append((task['start'], task['end'], job_id, task['task_idx']))

overlap_violations = []
for machine, tasks in machine_tasks.items():
    sorted_tasks = sorted(tasks)
    for i in range(len(sorted_tasks) - 1):
        curr = sorted_tasks[i]
        next_task = sorted_tasks[i + 1]
        if next_task[0] < curr[1]:  # next starts before curr ends
            overlap_violations.append(
                f"Machine {machine}: job {curr[2] + 1} task {curr[3]} ends at {curr[1]}, "
                f"but job {next_task[2] + 1} task {next_task[3]} starts at {next_task[0]}"
            )

if overlap_violations:
    print(f"❌ Found {len(overlap_violations)} machine overlap violations:")
    for v in overlap_violations[:10]:
        print(f"   - {v}")
else:
    print("✅ No machine overlaps!")

print(f"\n📊 OR-Tools solution is {'VALID' if not prec_violations and not overlap_violations else 'INVALID'}!")
