import urllib.request
import json
import time
import subprocess
import threading
import os
import sys
import xml.etree.ElementTree as ET
import socket
import ctypes

# ============ VERSION ============
VERSION = "1.0 pre-release"
# =================================

# Establecer título de la consola
if sys.platform == "win32":
    ctypes.windll.kernel32.SetConsoleTitleW(f"Noctiluca Worker v{VERSION}")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("⚠️ psutil no disponible")

def load_config():
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    tree = ET.parse(os.path.join(base, "worker_config.xml"))
    root = tree.getroot()
    return (
        f"http://{root.findtext('manager/ip')}:{root.findtext('manager/port')}",
        root.findtext("identity/name"),
        root.findtext("blender/path")
    )

MANAGER_URL, WORKER_NAME, BLENDER_PATH = load_config()

# ============ ESTADOS DEL WORKER ============
# ready     = Listo para recibir una task
# rendering = Procesando una task (blender corriendo)
# done      = Task completada, esperando que todos terminen
# ============================================

state = "ready"
running = True
current_job_id = None  # El job_id que estamos procesando actualmente
metrics = {
    "frames_rendered": 0,
    "jobs_completed": 0,
    "errors": 0
}

def get_system_info():
    if not HAS_PSUTIL:
        return {}
    try:
        return {
            "cpu_percent": round(psutil.cpu_percent(interval=0.1), 2),
            "memory_percent": round(psutil.virtual_memory().percent, 2),
        }
    except:
        return {}

def get_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except:
        return "unknown"

def post(path, data):
    req = urllib.request.Request(
        MANAGER_URL + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}
    )
    return urllib.request.urlopen(req, timeout=5)

def get_job():
    """Consulta al manager si hay un job activo"""
    try:
        with urllib.request.urlopen(MANAGER_URL + "/job", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return None

def report_error(error_msg, frame=None):
    try:
        post("/report_error", {
            "worker": WORKER_NAME,
            "error": error_msg,
            "frame": frame
        })
        metrics["errors"] += 1
    except:
        pass

def run_blender(blend_file):
    """Ejecuta Blender para renderizar el archivo"""
    try:
        print(f"[BLENDER] Iniciando render: {blend_file}")
        subprocess.run([BLENDER_PATH, "-b", blend_file, "-a"], check=True)
        print(f"[BLENDER] Render completado exitosamente")
        return True
    except subprocess.CalledProcessError as e:
        report_error(f"Blender error code: {e.returncode}")
        return False
    except Exception as e:
        report_error(f"Error: {str(e)}")
        return False

def heartbeat_loop():
    """
    Loop de heartbeat - SIEMPRE activo independiente del estado.
    Envía señales de vida constantes al manager con el estado actual.
    """
    global state, current_job_id
    
    while running:
        try:
            # Enviar heartbeat con el estado actual
            resp_data = {
                "name": WORKER_NAME,
                "status": state,
                "job_id": current_job_id,
                "system_info": get_system_info(),
                "ip": get_ip(),
                "frames_rendered": metrics["frames_rendered"],
                "jobs_completed": metrics["jobs_completed"],
                "errors": metrics["errors"]
            }
            
            with post("/heartbeat", resp_data) as resp:
                data = json.loads(resp.read().decode())
                manager_state = data.get("manager_state", "free")
                
                # Si el manager está en FREE o CONFIG, y nosotros estamos en DONE,
                # significa que el ciclo terminó y debemos resetear a READY
                if manager_state in ["free", "config"] and state == "done":
                    print(f"[HEARTBEAT] Manager en {manager_state}, reseteando a READY")
                    state = "ready"
                    current_job_id = None
                    
        except Exception as e:
            pass  # Silenciar errores de conexión
        
        time.sleep(2)  # Heartbeat cada 2 segundos

def main_loop():
    """
    Loop principal del worker.
    - En READY: consulta si hay task disponible
    - En RENDERING: está ocupado (no debería llegar aquí)
    - En DONE: espera a que el manager resetee
    """
    global state, current_job_id
    
    while running:
        try:
            # ============ ESTADO: READY ============
            # Listo para recibir una task
            if state == "ready":
                job = get_job()
                
                # Si hay un job activo en el manager
                if job and job.get("blend_file"):
                    server_job_id = job.get("job_id")
                    
                    # Verificar que no sea un job que ya procesamos
                    if server_job_id != current_job_id:
                        # Nueva task! Aceptarla
                        current_job_id = server_job_id
                        state = "rendering"
                        print(f"[TASK] Nueva task recibida (job_id: {current_job_id})")
                        print(f"[TASK] Archivo: {job['blend_file']}")
                        
                        # Ejecutar Blender (bloqueante)
                        success = run_blender(job["blend_file"])
                        
                        if success:
                            state = "done"
                            metrics["jobs_completed"] += 1
                            print(f"[DONE] ✓ Task completada - Esperando a otros workers")
                        else:
                            # Error en render, volver a ready para reintentar
                            state = "ready"
                            current_job_id = None
                            print(f"[ERROR] ✗ Error en render - Volviendo a READY")
                    else:
                        # Es el mismo job que ya procesamos, esperar
                        time.sleep(2)
                else:
                    # No hay job activo, seguir en ready
                    time.sleep(2)
            
            # ============ ESTADO: DONE ============
            # Task completada, esperando que todos terminen
            elif state == "done":
                # En este estado solo esperamos
                # El heartbeat se encarga de detectar cuando el manager
                # pasa a FREE/CONFIG y nos resetea a READY
                time.sleep(2)
            
            # ============ ESTADO: RENDERING ============
            # No deberíamos llegar aquí porque run_blender es bloqueante
            elif state == "rendering":
                time.sleep(1)
            
            else:
                # Estado desconocido, resetear a ready
                state = "ready"
                time.sleep(2)
                
        except Exception as e:
            print(f"[ERROR] Error en main loop: {e}")
            time.sleep(2)

# ============ INICIO DEL WORKER ============
print(f"=" * 50)
print(f"  NOCTILUCA WORKER v{VERSION}")
print(f"=" * 50)
print(f"Worker: {WORKER_NAME}")
print(f"Manager: {MANAGER_URL}")
print(f"Blender: {BLENDER_PATH}")
print(f"Estado inicial: {state}")
print(f"=" * 50)

# Iniciar thread de heartbeat (siempre activo)
heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
heartbeat_thread.start()
print(f"[HEARTBEAT] Thread de heartbeat iniciado")

# Iniciar loop principal
print(f"[READY] Worker listo para recibir tasks")
main_loop()

