"""
Test Z3 optimization WITHOUT Haskell hints to check if they're limiting the solution
"""

import requests
from instance_loader import load_instance
from z3 import *

def solve_without_hints(instance_filepath: str, setup_time: int = 0):
    """Solve JSSP using Z3 alone, without Haskell hints."""
    
    print(f"\n{'='*70}")
    print(f"Z3-ONLY (sem hints): {instance_filepath}")
    print(f"{'='*70}")
    
    # Load instance
    instance = load_instance(instance_filepath)
    print(f"\n📋 {instance['name']}: {instance['num_jobs']} jobs × {instance['num_machines']} máquinas = {len(instance['tasks'])} tarefas")
    
    # Z3 Setup
    print(f"\n🧮 Otimizando com Z3 (SEM hints do Haskell)...")
    opt = Optimize()
    starts = {t["id_t"]: Int(f"s_{t['id_t']}") for t in instance['tasks']}
    makespan = Int('makespan')
    
    # Basic constraints
    for t in instance['tasks']:
        tid, dur = t["id_t"], t["duration"]
        opt.add(starts[tid] >= 0)
        
        # ❌ NO HINTS - let Z3 search freely
        
        # Precedence within job
        if t["next_t"]:
            opt.add(starts[t["next_t"]] >= starts[tid] + dur)
        
        # Makespan
        opt.add(makespan >= starts[tid] + dur)
    
    # Machine constraints
    machines = {}
    for t in instance['tasks']:
        m = t['machine_id']
        if m not in machines:
            machines[m] = []
        machines[m].append(t)
    
    for m_tasks in machines.values():
        for i in range(len(m_tasks)):
            for j in range(i + 1, len(m_tasks)):
                t1, t2 = m_tasks[i], m_tasks[j]
                opt.add(Or(
                    starts[t2["id_t"]] >= starts[t1["id_t"]] + t1["duration"] + setup_time,
                    starts[t1["id_t"]] >= starts[t2["id_t"]] + t2["duration"] + setup_time
                ))
    
    # Minimize
    opt.minimize(makespan)
    
    print("⏳ Otimizando... (pode demorar mais sem hints)")
    
    # Set timeout to avoid infinite wait
    opt.set("timeout", 120000)  # 2 minutes
    
    result = opt.check()
    if result == sat:
        m = opt.model()
        z3_makespan = m[makespan].as_long()
        print(f"✅ Makespan Z3 (sem hints): {z3_makespan}h")
        return z3_makespan
    else:
        print(f"❌ Z3 não encontrou solução (ou timeout): {result}")
        return None

if __name__ == "__main__":
    # Compare with and without hints
    import sys
    
    filepath = sys.argv[1] if len(sys.argv) > 1 else "instances/AdamsBalasZawack1988/abz5.txt"
    
    # First: with hints (original method)
    print("\n" + "="*70)
    print("MÉTODO 1: COM HINTS DO HASKELL")
    print("="*70)
    
    instance = load_instance(filepath)
    response = requests.post("http://localhost:3000/validate", json=instance['tasks'], timeout=30)
    result = response.json()
    print(f"✅ Makespan Haskell (heurística): {result['makespan_heuristic']}h")
    
    # Second: without hints
    print("\n" + "="*70)
    print("MÉTODO 2: Z3 PURO (SEM HINTS)")
    print("="*70)
    solve_without_hints(filepath, setup_time=0)
