import requests
from z3 import *
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# 1. DEFINIÇÃO DO PROBLEMA REALISTA (3 Jobs x 3 Máquinas)
tarefas_jsp = [
    {"id_t": 1, "job_id": 1, "machine_id": 1, "duration": 3, "next_t": 2, "prev_t": None},
    {"id_t": 2, "job_id": 1, "machine_id": 2, "duration": 2, "next_t": 3, "prev_t": 1},
    {"id_t": 3, "job_id": 1, "machine_id": 3, "duration": 2, "next_t": None, "prev_t": 2},
    {"id_t": 4, "job_id": 2, "machine_id": 2, "duration": 4, "next_t": 5, "prev_t": None},
    {"id_t": 5, "job_id": 2, "machine_id": 1, "duration": 8, "next_t": 6, "prev_t": 4},
    {"id_t": 6, "job_id": 2, "machine_id": 3, "duration": 1, "next_t": None, "prev_t": 5},
    {"id_t": 7, "job_id": 3, "machine_id": 3, "duration": 1, "next_t": 8, "prev_t": None},
    {"id_t": 8, "job_id": 3, "machine_id": 2, "duration": 2, "next_t": 9, "prev_t": 7},
    {"id_t": 9, "job_id": 3, "machine_id": 1, "duration": 3, "next_t": None, "prev_t": 8},
    {"id_t": 10, "job_id": 4, "machine_id": 2, "duration": 5, "next_t": 11, "prev_t": None},
    {"id_t": 11, "job_id": 4, "machine_id": 1, "duration": 2, "next_t": 12, "prev_t": 10},
    {"id_t": 12, "job_id": 4, "machine_id": 3, "duration": 4, "next_t": None, "prev_t": 11},
]

SETUP_TIME = 0  # Deve ser igual ao definido no Haskell

def plotar_gantt(resultado, makespan_z3, makespan_h):
    fig, ax = plt.subplots(figsize=(12, 6))
    cores = {1: 'skyblue', 2: 'salmon', 3: 'lightgreen', 4:'orange'}
    
    for t in resultado:
        ax.broken_barh([(t['start'], t['duration'])], (t['machine']-0.4, 0.8), 
                       facecolors=cores[t['job']], edgecolor='black', alpha=0.9)
        ax.text(t['start'] + t['duration']/2, t['machine'], f"J{t['job']}\n{t['duration']}h", 
                ha='center', va='center', fontweight='bold', fontsize=9)

    ax.set_xlabel('Tempo (Horas)')
    ax.set_ylabel('Máquinas')
    ax.set_yticks([1, 2, 3])
    ax.set_yticklabels(['Máquina 1', 'Máquina 2', 'Máquina 3'])
    ax.set_title(f'Job-Shop: Haskell ({makespan_h}h) vs Z3 ({makespan_z3}h) | Setup: {SETUP_TIME}h')
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)
    
    legend_patches = [mpatches.Patch(color=cores[j], label=f'Job {j}') for j in cores]
    plt.legend(handles=legend_patches, title="Jobs")
    plt.tight_layout()
    plt.show()

def executar_otimizacao_hibrida():
    # --- PASSO 1: CONSULTA AO HASKELL ---
    print("--- Consultando Pré-Otimizador Haskell ---")
    try:
        response = requests.post("http://localhost:3000/validate", json=tarefas_jsp)
        res = response.json()
    except:
        return print("ERRO: O servidor Haskell (stack run) não responde na porta 3000.")

    if not res.get("valid"):
        return print(f"Haskell invalidou o grafo: {res.get('msg')}")

    h_makespan = res.get("makespan_heuristic")
    hints = res.get("hints")
    print(f"MAKESPAN HASKELL (Heurística + Setup): {h_makespan}h")

    # --- PASSO 2: CONFIGURAÇÃO DO Z3 ---
    opt = Optimize()
    starts = {t["id_t"]: Int(f"s_{t['id_t']}") for t in tarefas_jsp}
    makespan = Int('makespan')

    for t in tarefas_jsp:
        tid, dur = t["id_t"], t["duration"]
        opt.add(starts[tid] >= 0)
        
        # PISTA (HINT): O Z3 tenta seguir a sugestão do Haskell
        opt.add_soft(starts[tid] == hints[str(tid)], weight=1)
        
        if t["next_t"]:
            opt.add(starts[t["next_t"]] >= starts[tid] + dur)
        opt.add(makespan >= starts[tid] + dur)

    # Restrições de Máquina com SETUP_TIME
    maquinas = {m: [t for t in tarefas_jsp if t["machine_id"] == m] for m in [1, 2, 3]}
    for m_tasks in maquinas.values():
        for i in range(len(m_tasks)):
            for j in range(i + 1, len(m_tasks)):
                t1, t2 = m_tasks[i], m_tasks[j]
                # Se t2 após t1, soma setup. Se t1 após t2, soma setup.
                opt.add(Or(
                    starts[t2["id_t"]] >= starts[t1["id_t"]] + t1["duration"] + SETUP_TIME,
                    starts[t1["id_t"]] >= starts[t2["id_t"]] + t2["duration"] + SETUP_TIME
                ))

    # --- PASSO 3: RESULTADO ---
    opt.minimize(makespan)
    if opt.check() == sat:
        m = opt.model()
        z3_makespan = m[makespan].as_long()
        print(f"MAKESPAN Z3 (Ótimo Global): {z3_makespan}h")
        
        if z3_makespan < h_makespan:
            print(f"Sucesso: O Z3 melhorou a heurística em {h_makespan - z3_makespan}h!")

        resultado_final = []
        for t in tarefas_jsp:
            resultado_final.append({
                'job': t['job_id'], 'machine': t['machine_id'],
                'start': m[starts[t["id_t"]]].as_long(), 'duration': t['duration']
            })
        
        plotar_gantt(resultado_final, z3_makespan, h_makespan)
    else:
        print("Z3 não encontrou solução.")

if __name__ == "__main__":
    executar_otimizacao_hibrida()
