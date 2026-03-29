"""
JSSP Instance Loader
Carrega instâncias de Job Shop Scheduling Problem de diversos benchmarks
"""

import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional


def parse_jssp_file(filepath: str) -> Tuple[int, int, List[List[Tuple[int, int]]]]:
    """
    Parse arquivo de instância JSSP no formato padrão.
    
    Formato esperado:
    - Linha 1: num_jobs num_machines
    - Linhas seguintes: para cada job, pares (machine_id, duration)
    
    Args:
        filepath: Caminho para o arquivo .txt da instância
        
    Returns:
        Tupla (num_jobs, num_machines, jobs)
        jobs[i] = [(machine_id, duration), ...] sequência de operações do job i
    """
    with open(filepath, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    # Primeira linha: dimensões do problema
    num_jobs, num_machines = map(int, lines[0].split())
    
    # Parse das operações de cada job
    jobs = []
    for i in range(1, num_jobs + 1):
        if i >= len(lines):
            break
        
        values = list(map(int, lines[i].split()))
        # Valores vêm em pares: (máquina, duração)
        operations = [(values[j], values[j+1]) for j in range(0, len(values), 2)]
        jobs.append(operations)
    
    return num_jobs, num_machines, jobs


def jssp_to_tasks(jobs: List[List[Tuple[int, int]]]) -> List[Dict]:
    """
    Converte representação JSSP para formato TaskReq esperado pelo servidor Haskell.
    
    Args:
        jobs: Lista de jobs, cada um com [(machine_id, duration), ...]
        
    Returns:
        Lista de dicionários no formato TaskReq:
        {id_t, job_id, machine_id, duration, next_t, prev_t}
    """
    tasks = []
    task_id = 1
    
    for job_id, operations in enumerate(jobs, start=1):
        task_ids_in_job = []
        
        for machine_id, duration in operations:
            tasks.append({
                "id_t": task_id,
                "job_id": job_id,
                "machine_id": machine_id,
                "duration": duration,
                "next_t": None,  # Será preenchido depois
                "prev_t": None   # Será preenchido depois
            })
            task_ids_in_job.append(task_id)
            task_id += 1
        
        # Conectar tarefas do mesmo job em sequência
        for i in range(len(task_ids_in_job)):
            idx = task_ids_in_job[i] - 1  # Índice na lista tasks
            
            if i > 0:  # Tem predecessor
                tasks[idx]["prev_t"] = task_ids_in_job[i - 1]
            
            if i < len(task_ids_in_job) - 1:  # Tem sucessor
                tasks[idx]["next_t"] = task_ids_in_job[i + 1]
    
    return tasks


def load_instance(filepath: str) -> Dict:
    """
    Carrega uma instância completa de JSSP.
    
    Args:
        filepath: Caminho para o arquivo da instância
        
    Returns:
        Dicionário com:
        - name: nome do arquivo
        - num_jobs: número de jobs
        - num_machines: número de máquinas
        - tasks: lista de tarefas no formato TaskReq
    """
    num_jobs, num_machines, jobs = parse_jssp_file(filepath)
    tasks = jssp_to_tasks(jobs)
    
    return {
        "name": Path(filepath).stem,
        "benchmark": Path(filepath).parent.name,
        "num_jobs": num_jobs,
        "num_machines": num_machines,
        "tasks": tasks
    }


def list_all_instances(instances_dir: str = "../instances") -> List[str]:
    """
    Lista todos os arquivos .txt de instâncias em todos os subdiretórios.
    
    Args:
        instances_dir: Diretório raiz contendo os benchmarks
        
    Returns:
        Lista de caminhos absolutos para arquivos .txt
    """
    instances_path = Path(instances_dir)
    
    if not instances_path.exists():
        print(f"AVISO: Diretório {instances_dir} não encontrado")
        return []
    
    # Busca recursiva por arquivos .txt
    txt_files = list(instances_path.rglob("*.txt"))
    return sorted([str(f.absolute()) for f in txt_files])


def list_instances_by_benchmark(instances_dir: str = "../instances") -> Dict[str, List[str]]:
    """
    Lista instâncias agrupadas por benchmark.
    
    Args:
        instances_dir: Diretório raiz contendo os benchmarks
        
    Returns:
        Dicionário {benchmark_name: [lista_de_arquivos]}
    """
    instances_path = Path(instances_dir)
    
    if not instances_path.exists():
        return {}
    
    benchmarks = {}
    
    # Itera pelos subdiretórios (benchmarks)
    for benchmark_dir in sorted(instances_path.iterdir()):
        if benchmark_dir.is_dir():
            txt_files = sorted(benchmark_dir.glob("*.txt"))
            if txt_files:
                benchmarks[benchmark_dir.name] = [str(f) for f in txt_files]
    
    return benchmarks


# Função auxiliar para debugging
def print_instance_summary(instance: Dict):
    """Imprime resumo de uma instância carregada."""
    print(f"\n{'='*60}")
    print(f"Instância: {instance['name']} ({instance['benchmark']})")
    print(f"Dimensões: {instance['num_jobs']} jobs × {instance['num_machines']} máquinas")
    print(f"Total de tarefas: {len(instance['tasks'])}")
    print(f"{'='*60}")
    
    # Mostra primeiras 3 tarefas
    print("\nPrimeiras 3 tarefas:")
    for task in instance['tasks'][:3]:
        print(f"  Task {task['id_t']}: Job {task['job_id']}, "
              f"Máquina {task['machine_id']}, Duração {task['duration']}h, "
              f"Prev={task['prev_t']}, Next={task['next_t']}")


if __name__ == "__main__":
    # Exemplo de uso
    print("="*60)
    print("JSSP Instance Loader - Teste")
    print("="*60)
    
    # Lista todos os benchmarks disponíveis
    benchmarks = list_instances_by_benchmark("../instances")
    
    print(f"\n📁 Benchmarks disponíveis: {len(benchmarks)}")
    for benchmark, files in benchmarks.items():
        print(f"  • {benchmark}: {len(files)} instâncias")
    
    # Testa carregamento de instâncias específicas
    test_files = [
        "../instances/FisherThompson1963/ft06.txt",
        "../instances/Lawrence1984/la01.txt"
    ]
    
    for filepath in test_files:
        if os.path.exists(filepath):
            instance = load_instance(filepath)
            print_instance_summary(instance)
