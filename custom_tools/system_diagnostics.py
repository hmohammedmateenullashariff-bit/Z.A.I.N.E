import os
import gc
import psutil

def system_diagnostics(action: str = "list_heavy", target: str = "") -> str:
    """
    Advanced system telemetry and resource management:
    - 'list_heavy': Displays top 5 processes by CPU and RAM consumption.
    - 'kill_process': Terminates a hung or rogue process by name or PID (protected from killing system essentials).
    - 'free_ram': Runs aggressive garbage collection to release working set memory.
    """
    act = action.strip().lower()
    
    if act == "free_ram":
        before = psutil.virtual_memory().percent
        gc.collect()
        after = psutil.virtual_memory().percent
        return f"Garbage collection executed. Memory load: {before}% -> {after}%."
        
    elif act == "kill_process":
        if not target:
            return "Error: Please specify a process name or PID to terminate."
        
        protected = ["system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "explorer.exe"]
        killed = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                pname = p.info["name"].lower()
                pid = str(p.info["pid"])
                if (target.lower() in pname or target == pid) and pname not in protected:
                    p.terminate()
                    killed.append(f"{p.info['name']} (PID: {pid})")
            except Exception:
                pass
        if killed:
            return f"Successfully terminated: {', '.join(killed)}"
        return f"No non-essential process matching '{target}' found."

    else:
        # Default: list_heavy
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                mem = p.info.get("memory_percent") or 0.0
                cpu = p.info.get("cpu_percent") or 0.0
                procs.append((p.info["name"], p.info["pid"], cpu, mem))
            except Exception:
                pass
        
        # Sort by memory percent descending
        procs.sort(key=lambda x: x[3], reverse=True)
        top5 = procs[:5]
        
        lines = ["Top Resource Consuming Processes:"]
        for name, pid, cpu, mem in top5:
            lines.append(f"- {name} (PID {pid}): RAM {mem:.1f}% | CPU {cpu:.1f}%")
        return "\n".join(lines)
