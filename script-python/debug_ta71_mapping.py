#!/usr/bin/env python3
"""
Debug ta71.sol to understand task-to-machine mapping.
Check if jobs can visit the same machine multiple times.
"""

from instance_loader import parse_jssp_file

# Parse instance
num_jobs, num_machines, jobs = parse_jssp_file("instances/Taillard1993/ta71js.txt")

print(f"Instance: {num_jobs} jobs × {num_machines} machines")
print()

# Check if any job visits the same machine multiple times
jobs_with_repeats = []

for job_id in range(min(5, num_jobs)):  # Check first 5 jobs
    print(f"Job {job_id}:")
    machines_visited = []
    for task_idx, (machine, duration) in enumerate(jobs[job_id]):
        machines_visited.append(machine)
        print(f"  Task {task_idx}: machine {machine}, duration {duration}")
    
    # Check for duplicates
    if len(machines_visited) != len(set(machines_visited)):
        print(f"  ⚠️  Job {job_id} visits some machines multiple times!")
        from collections import Counter
        counts = Counter(machines_visited)
        for machine, count in counts.items():
            if count > 1:
                print(f"     Machine {machine} visited {count} times")
        jobs_with_repeats.append(job_id)
    print()

if jobs_with_repeats:
    print(f"⚠️  {len(jobs_with_repeats)} job(s) visit machines multiple times")
    print("This means the validator CANNOT simply match 'job X on machine Y' uniquely!")
else:
    print("✅ No job visits any machine more than once")
