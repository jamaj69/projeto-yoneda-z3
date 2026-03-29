"""
Debug script to understand why Z3 returns different results
"""
import requests
from instance_loader import load_instance
from z3 import *

instance = load_instance("../instances/AdamsBalasZawack1988/abz5.txt")

# Get Haskell hints
response = requests.post("http://localhost:3000/validate", json=instance['tasks'], timeout=30)
result = response.json()
h_makespan = result['makespan_heuristic']
hints = result['hints']

print(f"Haskell makespan: {h_makespan}h")
print(f"Número de hints: {len(hints)}")

# Configure Z3
print("\n=== Configuração Z3 ===")
opt = Optimize()
print(f"Tipo de solver: {type(opt)}")

starts = {t["id_t"]: Int(f"s_{t['id_t']}") for t in instance['tasks']}
makespan = Int('makespan')

# Basic constraints
num_prec_constraints = 0
for t in instance['tasks']:
    tid, dur = t["id_t"], t["duration"]
    opt.add(starts[tid] >= 0)
    
    if t["next_t"]:
        opt.add(starts[t["next_t"]] >= starts[tid] + dur)
        num_prec_constraints += 1
    
    opt.add(makespan >= starts[tid] + dur)

print(f"Constraints de precedência: {num_prec_constraints}")

# Machine constraints
machines = {}
for t in instance['tasks']:
    m = t['machine_id']
    if m not in machines:
        machines[m] = []
    machines[m].append(t)

setup_time = 0
num_machine_constraints = 0
for m_tasks in machines.values():
    for i in range(len(m_tasks)):
        for j in range(i + 1, len(m_tasks)):
            t1, t2 = m_tasks[i], m_tasks[j]
            opt.add(Or(
                starts[t2["id_t"]] >= starts[t1["id_t"]] + t1["duration"] + setup_time,
                starts[t1["id_t"]] >= starts[t2["id_t"]] + t2["duration"] + setup_time
            ))
            num_machine_constraints += 1

print(f"Constraints de máquina: {num_machine_constraints}")
print(f"Setup time: {setup_time}")

# Check if setup_time is actually being used
print(f"\n=== Verificação de setup_time ===")
print(f"setup_time valor: {setup_time}")
print(f"setup_time == 0: {setup_time == 0}")

# Minimize
h = opt.minimize(makespan)

print(f"\n=== Otimizando ===")
result = opt.check()

if result == sat:
    m = opt.model()
    z3_makespan = m[makespan].as_long()
    
    lower = opt.lower(h)
    upper = opt.upper(h)
    
    print(f"\n=== Resultados ===")
    print(f"Status: {result}")
    print(f"Makespan: {z3_makespan}h")
    print(f"Lower bound: {lower}")
    print(f"Upper bound: {upper}")
    print(f"Ótimo conhecido: 1234h")
    print(f"Gap: {z3_makespan - 1234}h")
    
    # Verificar se constraints estão satisfeitas
    print(f"\n=== Verificação ===")
    all_start_times = {tid: m[starts[tid]].as_long() for tid in starts}
    print(f"Exemplo de start times (primeiras 5 tarefas):")
    for i, (tid, start) in enumerate(list(all_start_times.items())[:5]):
        task = next(t for t in instance['tasks'] if t['id_t'] == tid)
        print(f"  Task {tid}: start={start}, duration={task['duration']}, end={start + task['duration']}")
else:
    print(f"Z3 failed: {result}")
