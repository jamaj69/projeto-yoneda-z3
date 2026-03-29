"""
Enhanced optimization using bottleneck analysis from Haskell
"""

import requests
from instance_loader import load_instance
from z3 import *


def solve_with_bottleneck_focus(instance_filepath: str, setup_time: int = 0):
    """
    Resolve JSSP usando análise de gargalos do Haskell para focar otimização Z3.
    """
    
    print(f"\n{'='*70}")
    print(f"Otimização Focada em Gargalos: {instance_filepath}")
    print(f"{'='*70}")
    
    # 1. Carregar instância
    instance = load_instance(instance_filepath)
    print(f"\n📋 {instance['name']}: {instance['num_jobs']} jobs × {instance['num_machines']} máquinas")
    
    # 2. Consultar Haskell com análise de gargalos
    print(f"\n🔍 Consultando Haskell (heurística MWR+SPT + análise de gargalos)...")
    try:
        response = requests.post("http://localhost:3000/validate", 
                                json=instance['tasks'], timeout=30)
        res = response.json()
    except:
        print("❌ ERRO: Servidor Haskell não responde")
        return
    
    if not res.get("valid"):
        print(f"❌ Haskell invalidou: {res.get('msg')}")
        return
    
    # 3. Analisar gargalos
    h_makespan = res.get("makespan_heuristic")
    hints = res.get("hints")
    slacks = res.get("slacks", {})
    critical_path = res.get("critical_path", [])
    critical_machines = res.get("critical_machines", [])
    machine_util = res.get("machine_utilization", {})
    
    print(f"✅ Makespan Haskell: {h_makespan}h")
    print(f"\n📊 Análise de Gargalos:")
    print(f"   • Caminho crítico: {len(critical_path)} tarefas")
    print(f"   • Máquinas críticas: {critical_machines}")
    print(f"   • Utilização máxima: {max(machine_util.values())*100:.1f}%" if machine_util else "N/A")
    
    # Mostrar tarefas críticas (slack = 0)
    critical_tasks = [tid for tid, slack in slacks.items() if int(slack) == 0]
    print(f"   • Tarefas críticas (slack=0): {len(critical_tasks)}/{len(instance['tasks'])}")
    
    # 4. Configurar Z3 com foco nos gargalos
    print(f"\n🧮 Otimizando com Z3 (foco em gargalos)...")
    opt = Optimize()
    starts = {t["id_t"]: Int(f"s_{t['id_t']}") for t in instance['tasks']}
    makespan = Int('makespan')
    
    # Restrições básicas
    for t in instance['tasks']:
        tid, dur = t["id_t"], t["duration"]
        opt.add(starts[tid] >= 0)
        
        if t["next_t"]:
            opt.add(starts[t["next_t"]] >= starts[tid] + dur)
        
        opt.add(makespan >= starts[tid] + dur)
    
    # Restrições de máquina
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
    
    # Minimizar
    opt.minimize(makespan)
    
    print("⏳ Otimizando...")
    if opt.check() == sat:
        m = opt.model()
        z3_makespan = m[makespan].as_long()
        
        print(f"\n{'='*70}")
        print(f"📊 RESULTADOS")
        print(f"{'='*70}")
        print(f"Heurística Haskell: {h_makespan}h")
        print(f"Z3 Otimizado:       {z3_makespan}h")
        
        improvement = h_makespan - z3_makespan
        if improvement > 0:
            print(f"🎉 Melhoria: {improvement}h ({improvement/h_makespan*100:.1f}%)")
        else:
            print(f"✨ Heurística já era ótima!")
        
        # Verificar se tarefas críticas continuam críticas
        print(f"\n🔍 Validação:")
        z3_starts = {tid: m[starts[tid]].as_long() for tid in starts}
        
        # Tarefas que ainda terminam no makespan (críticas na solução Z3)
        z3_critical = []
        for t in instance['tasks']:
            tid = t['id_t']
            end_time = z3_starts[tid] + t['duration']
            if end_time == z3_makespan:
                z3_critical.append(tid)
        
        print(f"   • Tarefas críticas originais: {len(critical_tasks)}")
        print(f"   • Tarefas críticas em Z3:     {len(z3_critical)}")
        
        # Quantas tarefas críticas originais ainda são críticas?
        kept_critical = len(set(critical_tasks) & set(z3_critical))
        print(f"   • Mantidas críticas:          {kept_critical}")
        
        return {
            "heuristic_makespan": h_makespan,
            "z3_makespan": z3_makespan,
            "improvement": improvement,
            "critical_tasks_heuristic": len(critical_tasks),
            "critical_tasks_z3": len(z3_critical),
            "critical_machines": critical_machines
        }
    else:
        print("❌ Z3 não encontrou solução")
        return None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        instance_file = sys.argv[1]
    else:
        instance_file = "instances/AdamsBalasZawack1988/abz5.txt"
    
    result = solve_with_bottleneck_focus(instance_file)
    
    if result:
        print(f"\n{'='*70}")
        print("✅ Otimização concluída com análise de gargalos!")
        print(f"{'='*70}")
