"""
Exemplo de uso do Instance Loader com o sistema híbrido Haskell + Z3
"""

import requests
from instance_loader import load_instance, list_instances_by_benchmark
from z3 import *


def solve_instance_with_hybrid_system(instance_filepath: str, setup_time: int = 2):
    """
    Resolve uma instância JSSP usando o sistema híbrido Haskell + Z3.
    
    Args:
        instance_filepath: Caminho para o arquivo da instância
        setup_time: Tempo de setup entre jobs diferentes na mesma máquina
    """
    print(f"\n{'='*70}")
    print(f"Resolvendo instância: {instance_filepath}")
    print(f"{'='*70}")
    
    # 1. Carregar instância
    instance = load_instance(instance_filepath)
    print(f"\n📋 Instância: {instance['name']} ({instance['benchmark']})")
    print(f"   Jobs: {instance['num_jobs']} | Máquinas: {instance['num_machines']} | Tarefas: {len(instance['tasks'])}")
    
    # 2. Consultar Haskell
    print(f"\n🔍 Consultando pré-otimizador Haskell...")
    try:
        response = requests.post("http://localhost:3000/validate", json=instance['tasks'], timeout=30)
        res = response.json()
    except requests.exceptions.ConnectionError:
        print("❌ ERRO: Servidor Haskell não está rodando. Execute 'stack run' primeiro.")
        return
    except requests.exceptions.Timeout:
        print("⏱️ TIMEOUT: Instância muito grande para o Haskell processar rapidamente.")
        return
    
    if not res.get("valid"):
        print(f"❌ Haskell invalidou: {res.get('msg')}")
        return
    
    h_makespan = res.get("makespan_heuristic")
    hints = res.get("hints")
    print(f"✅ Makespan Haskell (heurística): {h_makespan}h")
    
    # 3. Resolver com Z3
    print(f"\n🧮 Resolvendo com Z3 Theorem Prover...")
    opt = Optimize()
    starts = {t["id_t"]: Int(f"s_{t['id_t']}") for t in instance['tasks']}
    makespan = Int('makespan')
    
    # Restrições básicas
    for t in instance['tasks']:
        tid, dur = t["id_t"], t["duration"]
        opt.add(starts[tid] >= 0)
        
        # Hint do Haskell como soft constraint
        if str(tid) in hints:
            opt.add_soft(starts[tid] == hints[str(tid)], weight=1)
        
        # Precedência dentro do job
        if t["next_t"]:
            opt.add(starts[t["next_t"]] >= starts[tid] + dur)
        
        # Makespan
        opt.add(makespan >= starts[tid] + dur)
    
    # Restrições de máquina com setup time
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
    
    # Minimizar makespan
    opt.minimize(makespan)
    
    print("⏳ Otimizando... (pode levar alguns segundos)")
    if opt.check() == sat:
        m = opt.model()
        z3_makespan = m[makespan].as_long()
        print(f"✅ Makespan Z3 (ótimo): {z3_makespan}h")
        
        improvement = h_makespan - z3_makespan
        if improvement > 0:
            print(f"🎉 Z3 melhorou a heurística em {improvement}h ({improvement/h_makespan*100:.1f}%)")
        elif improvement == 0:
            print(f"✨ Heurística do Haskell já encontrou o ótimo!")
        else:
            print(f"⚠️ AVISO: Z3 reportou makespan pior que heurística (erro?)")
        
        return {
            "instance": instance['name'],
            "haskell_makespan": h_makespan,
            "z3_makespan": z3_makespan,
            "improvement": improvement,
            "solution": {t["id_t"]: m[starts[t["id_t"]]].as_long() for t in instance['tasks']}
        }
    else:
        print("❌ Z3 não encontrou solução")
        return None


def benchmark_multiple_instances(benchmark_name: str, max_instances: int = 5):
    """
    Testa múltiplas instâncias de um benchmark específico.
    
    Args:
        benchmark_name: Nome do benchmark (ex: 'FisherThompson1963')
        max_instances: Número máximo de instâncias para testar
    """
    benchmarks = list_instances_by_benchmark("../instances")
    
    if benchmark_name not in benchmarks:
        print(f"❌ Benchmark '{benchmark_name}' não encontrado.")
        print(f"Disponíveis: {', '.join(benchmarks.keys())}")
        return
    
    instances = benchmarks[benchmark_name][:max_instances]
    results = []
    
    print(f"\n{'='*70}")
    print(f"BENCHMARK: {benchmark_name}")
    print(f"Testando {len(instances)} instâncias")
    print(f"{'='*70}")
    
    for instance_file in instances:
        result = solve_instance_with_hybrid_system(instance_file)
        if result:
            results.append(result)
    
    # Resumo
    if results:
        print(f"\n{'='*70}")
        print(f"RESUMO - {benchmark_name}")
        print(f"{'='*70}")
        print(f"{'Instância':<15} {'Haskell':<10} {'Z3':<10} {'Melhoria':<10}")
        print(f"{'-'*70}")
        for r in results:
            print(f"{r['instance']:<15} {r['haskell_makespan']:<10} "
                  f"{r['z3_makespan']:<10} {r['improvement']:<10}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Resolver instância específica
        instance_file = sys.argv[1]
        solve_instance_with_hybrid_system(instance_file)
    else:
        # Exemplos de uso
        print("\n" + "="*70)
        print("EXEMPLOS DE USO DO INSTANCE LOADER")
        print("="*70)
        
        print("\n1️⃣  Resolver uma instância específica:")
        print("   python example_usage.py ../instances/FisherThompson1963/ft06.txt")
        
        print("\n2️⃣  Testar benchmark completo (no código):")
        print("   benchmark_multiple_instances('FisherThompson1963', max_instances=3)")
        
        # Exemplo prático: resolve uma instância pequena
        print("\n" + "="*70)
        print("EXECUTANDO EXEMPLO: ft06")
        print("="*70)
        solve_instance_with_hybrid_system("../instances/FisherThompson1963/ft06.txt")
