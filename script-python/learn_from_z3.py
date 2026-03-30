"""
Sistema de Aprendizado por Feedback - Z3 → Haskell

Envia solução ótima do Z3 de volta ao Haskell para análise comparativa
e geração de insights sobre como melhorar a heurística.
"""

import requests
import time
from typing import Dict, List, Any, Tuple, Optional
from z3 import *
from instance_loader import load_instance


def solve_with_z3(tasks: List[Dict], setup_time: int = 0) -> Tuple[Dict[int, int], int, float]:
    """
    Resolve instância com Z3 e retorna solução + tempo de execução.
    
    Returns:
        (solution_dict, makespan, solver_time)
    """
    print("🧮 Resolvendo com Z3...")
    opt = Optimize()
    starts = {t["id_t"]: Int(f"s_{t['id_t']}") for t in tasks}
    makespan = Int('makespan')
    
    # Constraints básicas
    for t in tasks:
        tid, dur = t["id_t"], t["duration"]
        opt.add(starts[tid] >= 0)
        
        # Precedência
        if t["next_t"]:
            opt.add(starts[t["next_t"]] >= starts[tid] + dur)
        
        # Makespan
        opt.add(makespan >= starts[tid] + dur)
    
    # Máquinas (não-overlap)
    machines = {}
    for t in tasks:
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
    
    opt.minimize(makespan)
    
    start_time = time.time()
    if opt.check() == sat:
        solver_time = time.time() - start_time
        m = opt.model()
        z3_makespan = m[makespan].as_long()
        z3_solution = {tid: m[starts[tid]].as_long() for tid in starts}
        
        return z3_solution, z3_makespan, solver_time
    else:
        raise Exception("Z3 não encontrou solução!")


def send_learning_feedback(
    tasks: List[Dict],
    z3_solution: Dict[int, int],
    z3_makespan: int,
    z3_time: float,
    haskell_url: str = "http://localhost:3000"
) -> Optional[Dict[str, Any]]:
    """
    Envia solução ótima do Z3 para o Haskell aprender com as diferenças.
    
    Nota: Este endpoint ainda não está implementado no Haskell v0.3.0.
          Este script serve como DEMONSTRAÇÃO da arquitetura proposta.
    """
    optimal_sol = {
        "optimal_starts": z3_solution,
        "optimal_makespan": z3_makespan,
        "z3_solver_time": z3_time
    }
    
    payload = {
        "optimal_solution": optimal_sol,
        "tasks": tasks
    }
    
    try:
        response = requests.post(
            f"{haskell_url}/learn",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.ConnectionError:
        print("⚠️  Endpoint /learn ainda não implementado no Haskell.")
        print("📖 Leia docs/FEEDBACK_LEARNING.md para implementar.")
        return None
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao enviar feedback: {e}")
        return None


def print_learning_report(insights: Dict[str, Any]):
    """Imprime relatório de aprendizado em formato legível"""
    
    if not insights or not insights.get("learned"):
        print("❌ Aprendizado não disponível")
        return
    
    data = insights["insights"]
    
    print("\n" + "="*70)
    print("📚 RELATÓRIO DE APRENDIZADO - Haskell ↔ Z3")
    print("="*70)
    
    # Gap
    print(f"\n🎯 Desempenho:")
    print(f"   Heurística: {data['heuristic_makespan']}h")
    print(f"   Ótimo (Z3): {data['optimal_makespan']}h")
    print(f"   Gap: {data['gap_hours']}h ({data['gap_percentage']:.1f}%)")
    
    # Detecção de gargalos
    if 'bottleneck_accuracy' in data:
        acc = data['bottleneck_accuracy']
        print(f"\n🎯 Detecção de Gargalos:")
        print(f"   Acurácia: {acc['accuracy_score']*100:.1f}%")
        print(f"   ✅ Corretos: {acc['correctly_identified']}")
        print(f"   ⚠️  Falsos Positivos: {acc['false_positives']}")
        print(f"   ❌ Falsos Negativos: {acc['false_negatives']}")
    
    # Máquinas com ordenação diferente
    if 'mismatched_machines' in data:
        print(f"\n🔄 Máquinas com Ordenação Diferente:")
        for mc in data['mismatched_machines'][:5]:  # top 5
            print(f"   Máquina {mc['machine_id']}:")
            print(f"      Heurística: {mc['heuristic_order']}")
            print(f"      Ótimo:      {mc['optimal_order']}")
            if mc['swap_pairs']:
                print(f"      Swaps necessários: {len(mc['swap_pairs'])} (impacto: ~{mc['impact_hours']}h)")
    
    # Sugestões de ajuste
    if 'heuristic_adjustments' in data:
        print(f"\n💡 Sugestões de Ajuste:")
        for adj in data['heuristic_adjustments']:
            print(f"   [{adj['adjustment_type']}] {adj['description']}")
            print(f"      Ajuste de peso: {adj['weight_change']:+.1%}")
    
    print("\n" + "="*70 + "\n")


def manual_analysis(
    tasks: List[Dict],
    h_starts: Dict[int, int],
    h_makespan: int,
    z3_starts: Dict[int, int],
    z3_makespan: int
) -> Dict[str, Any]:
    """
    Análise manual (Python-side) enquanto endpoint /learn não existe.
    
    Implementa algumas das análises propostas em FEEDBACK_LEARNING.md
    """
    gap = h_makespan - z3_makespan
    gap_pct = (gap / z3_makespan) * 100.0 if z3_makespan > 0 else 0.0
    
    # Agrupa tarefas por máquina
    machines = {}
    for t in tasks:
        m = t['machine_id']
        if m not in machines:
            machines[m] = []
        machines[m].append(t)
    
    # Compara ordenação em cada máquina
    mismatched = []
    for mid, m_tasks in machines.items():
        # Ordena por tempo de início (heurística)
        h_order = sorted(m_tasks, key=lambda t: h_starts.get(t['id_t'], 0))
        h_ids = [t['id_t'] for t in h_order]
        
        # Ordena por tempo de início (ótimo)
        z3_order = sorted(m_tasks, key=lambda t: z3_starts.get(t['id_t'], 0))
        z3_ids = [t['id_t'] for t in z3_order]
        
        if h_ids != z3_ids:
            # Encontra pares que deveriam ter sido trocados
            swaps = []
            for i in range(len(h_ids)):
                for j in range(i+1, len(h_ids)):
                    h_i_idx = h_ids.index(h_ids[i])
                    h_j_idx = h_ids.index(h_ids[j])
                    
                    try:
                        z3_i_idx = z3_ids.index(h_ids[i])
                        z3_j_idx = z3_ids.index(h_ids[j])
                        
                        # Invertidos?
                        if (h_i_idx < h_j_idx) and (z3_i_idx > z3_j_idx):
                            swaps.append((h_ids[i], h_ids[j]))
                    except ValueError:
                        pass  # tarefa não está na lista
            
            mismatched.append({
                'machine_id': mid,
                'heuristic_order': h_ids,
                'optimal_order': z3_ids,
                'swap_pairs': swaps,
                'impact_hours': gap // max(1, len(machines))  # estimativa grosseira
            })
    
    # Gera sugestões simples
    adjustments = []
    if gap_pct > 15.0 and len(mismatched) > 2:
        adjustments.append({
            'adjustment_type': 'IncreaseSPTWeight',
            'description': 'Muitas trocas de ordem detectadas. Priorize tarefas mais curtas.',
            'weight_change': 0.3
        })
    
    if gap_pct > 20.0:
        adjustments.append({
            'adjustment_type': 'IncreaseMWRWeight',
            'description': 'Gap muito grande. Foque mais em jobs com trabalho restante.',
            'weight_change': 0.2
        })
    
    return {
        'heuristic_makespan': h_makespan,
        'optimal_makespan': z3_makespan,
        'gap_hours': gap,
        'gap_percentage': gap_pct,
        'mismatched_machines': mismatched,
        'heuristic_adjustments': adjustments
    }


def solve_and_learn(instance_file: str, setup_time: int = 0):
    """
    Fluxo completo: carregar → heurística → Z3 → feedback → aprendizado
    """
    print(f"\n{'='*70}")
    print(f"🔬 SISTEMA DE APRENDIZADO POR FEEDBACK")
    print(f"{'='*70}")
    print(f"Instância: {instance_file}")
    print(f"Setup time: {setup_time}h")
    
    # 1. Carregar instância
    instance = load_instance(instance_file)
    tasks = instance['tasks']
    print(f"\n📋 {instance['name']} ({instance['benchmark']})")
    print(f"   {instance['num_jobs']} jobs × {instance['num_machines']} máquinas = {len(tasks)} tarefas")
    
    # 2. Obter heurística do Haskell
    print(f"\n🔍 Consultando Haskell (heurística MWR+SPT)...")
    try:
        resp = requests.post("http://localhost:3000/validate", json=tasks, timeout=30)
        heuristic = resp.json()
    except requests.exceptions.ConnectionError:
        print("❌ ERRO: Servidor Haskell não está rodando.")
        print("   Execute: stack run")
        return
    
    if not heuristic.get('valid'):
        print(f"❌ Haskell invalidou: {heuristic.get('msg')}")
        return
    
    h_makespan = heuristic['makespan_heuristic']
    h_starts = heuristic['hints']
    print(f"✅ Makespan heurística: {h_makespan}h")
    
    # 3. Resolver com Z3
    z3_starts, z3_makespan, z3_time = solve_with_z3(tasks, setup_time)
    print(f"✅ Makespan Z3 (ótimo): {z3_makespan}h (tempo: {z3_time:.2f}s)")
    
    gap = h_makespan - z3_makespan
    if gap > 0:
        print(f"🎉 Z3 melhorou em {gap}h ({gap/h_makespan*100:.1f}%)")
    elif gap == 0:
        print(f"✨ Heurística já encontrou o ótimo!")
    
    # 4. TENTATIVA de feedback ao Haskell
    print(f"\n📤 Enviando feedback para Haskell aprender...")
    insights = send_learning_feedback(tasks, z3_starts, z3_makespan, z3_time)
    
    # 5. Se /learn não implementado, fazer análise manual Python-side
    if insights is None:
        print("\n🔍 Executando análise manual (Python-side) enquanto /learn não existe...")
        manual_insights = manual_analysis(tasks, h_starts, h_makespan, z3_starts, z3_makespan)
        
        print("\n" + "="*70)
        print("📊 ANÁLISE COMPARATIVA (versão simplificada)")
        print("="*70)
        print(f"\n🎯 Desempenho:")
        print(f"   Heurística: {manual_insights['heuristic_makespan']}h")
        print(f"   Ótimo (Z3): {manual_insights['optimal_makespan']}h")
        print(f"   Gap: {manual_insights['gap_hours']}h ({manual_insights['gap_percentage']:.1f}%)")
        
        if manual_insights['mismatched_machines']:
            print(f"\n🔄 Máquinas com Ordenação Diferente:")
            for mc in manual_insights['mismatched_machines'][:5]:
                print(f"   Máquina {mc['machine_id']}:")
                print(f"      Heurística: {mc['heuristic_order']}")
                print(f"      Ótimo:      {mc['optimal_order']}")
                if mc['swap_pairs']:
                    print(f"      ⚠️  {len(mc['swap_pairs'])} swaps necessários")
        
        if manual_insights['heuristic_adjustments']:
            print(f"\n💡 Sugestões de Ajuste:")
            for adj in manual_insights['heuristic_adjustments']:
                print(f"   • {adj['description']}")
                print(f"     Tipo: {adj['adjustment_type']} ({adj['weight_change']:+.0%})")
        
        print("\n" + "="*70)
        print("📝 Para implementar análise completa no Haskell:")
        print("   1. Leia docs/FEEDBACK_LEARNING.md")
        print("   2. Implemente endpoint /learn em Main.hs")
        print("   3. Execute novamente este script")
        print("="*70 + "\n")
    
    else:
        # Se /learn existir, mostrar relatório completo
        print_learning_report(insights)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python learn_from_z3.py <instância> [setup_time]")
        print("\nExemplos:")
        print("  python learn_from_z3.py instances/FisherThompson1963/ft06.txt")
        print("  python learn_from_z3.py instances/AdamsBalasZawack1988/abz5.txt 0")
        print("  python learn_from_z3.py instances/Lawrence1984/la01.txt")
        sys.exit(1)
    
    instance_file = sys.argv[1]
    setup_time = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    
    solve_and_learn(instance_file, setup_time)
