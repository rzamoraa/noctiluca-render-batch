from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time
import threading
from collections import deque
from datetime import datetime
import webbrowser
import os
import xml.etree.ElementTree as ET

HOST = "0.0.0.0"
PORT = 8000
WORKER_TIMEOUT = 10
HISTORY_FILE = "job_history.json"
IMAGE_EXTENSIONS = ('.png', '.exr', '.jpg', '.jpeg', '.tiff', '.bmp')

# Funciones de persistencia
def load_history():
    """Carga el historial desde archivo"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
                return deque(data[-50:], maxlen=50)
        except:
            return deque(maxlen=50)
    return deque(maxlen=50)

def save_history(history):
    """Guarda el historial en archivo"""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(list(history), f, indent=2)
    except Exception as e:
        print(f"Error guardando historial: {str(e)}")

def get_render_dir(output_path):
    """Resuelve la ruta correcta de la carpeta de renders"""
    if not output_path:
        return None
    
    if "render" in output_path.lower():
        if output_path.lower().endswith('.blend'):
            blend_dir = os.path.dirname(output_path)
            return os.path.join(blend_dir, "render")
        else:
            return output_path if os.path.exists(output_path) else os.path.dirname(output_path)
    else:
        blend_dir = os.path.dirname(output_path)
        return os.path.join(blend_dir, "render")

def load_worker_config():
    """Carga la configuración del worker desde XML"""
    try:
        worker_config_file = os.path.join(os.path.dirname(__file__), "..", "worker", "worker_config.xml")
        if os.path.exists(worker_config_file):
            tree = ET.parse(worker_config_file)
            root = tree.getroot()
            
            config = {
                "manager_ip": root.find("manager/ip").text or "localhost",
                "manager_port": int(root.find("manager/port").text or "8000"),
                "worker_name": root.find("identity/name").text or "WORKER",
                "blender_path": root.find("blender/path").text or "blender"
            }
            return config
    except Exception as e:
        log_activity(f"Error cargando worker config: {e}", "warning")
    
    return {
        "manager_ip": "localhost",
        "manager_port": 8000,
        "worker_name": "WORKER",
        "blender_path": "blender"
    }

# Estado del sistema
workers = {}
manager_state = "free"
job_completion_time = None
job = {
    "blend_file": None,
    "output_path": None,
    "total_frames": 0,
    "completed_frames": 0,
    "frame_range": {"start": 0, "end": 0},
    "resolution": {"x": 1920, "y": 1080},
    "render_engine": "CYCLES",
    "start_time": None
}
job_id = 0

# Historial y estadísticas
job_history = load_history()
error_log = deque(maxlen=100)
activity_log = deque(maxlen=200)
alerts = deque(maxlen=20)
job_queue = deque()
performance_metrics = {
    "total_jobs_completed": 0,
    "total_render_time": 0,
    "peak_workers": 0,
    "queue_size": 0
}

def log_activity(message, level="info"):
    """Registra actividad en el sistema"""
    activity_log.append({
        "timestamp": time.time(),
        "message": message,
        "level": level,
        "datetime": datetime.now().isoformat()
    })
    print(f"[{level.upper()}] {message}")

def add_alert(message, alert_type="warning"):
    """Agrega una alerta al sistema"""
    alerts.append({
        "timestamp": time.time(),
        "message": message,
        "type": alert_type,
        "datetime": datetime.now().isoformat()
    })

def count_rendered_frames(output_path, total_frames):
    """Cuenta los frames reales renderizados en la carpeta de output"""
    if not output_path:
        return 0
    
    render_dir = get_render_dir(output_path)
    if not render_dir or not os.path.exists(render_dir):
        return 0
    
    try:
        rendered_count = sum(1 for f in os.listdir(render_dir) if f.lower().endswith(IMAGE_EXTENSIONS))
        return rendered_count
    except Exception as e:
        log_activity(f"Error contando frames: {str(e)}", "error")
        return 0

def calculate_job_progress():
    """Calcula el progreso del job actual"""
    if not job["blend_file"] or job["total_frames"] == 0:
        return None
    
    # Contar frames reales del output
    if job["output_path"]:
        actual_frames = count_rendered_frames(job["output_path"], job["total_frames"])
        job["completed_frames"] = actual_frames
    
    progress_percent = (job["completed_frames"] / job["total_frames"]) * 100
    elapsed_time = time.time() - job["start_time"] if job["start_time"] else 0
    
    if job["completed_frames"] > 0:
        avg_time = elapsed_time / job["completed_frames"]
        remaining = avg_time * (job["total_frames"] - job["completed_frames"])
    else:
        avg_time = 0
        remaining = 0
    
    return {
        "progress_percent": round(progress_percent, 2),
        "completed_frames": job["completed_frames"],
        "total_frames": job["total_frames"],
        "elapsed_time": elapsed_time,
        "estimated_remaining": remaining,
        "avg_time_per_frame": avg_time
    }

def manager_loop():
    """
    Loop principal del manager con máquina de estados:
    FREE -> WORKING -> CONFIG -> FREE
    
    FREE:    Esperando tasks en la cola, verificando que workers estén READY
    WORKING: Procesando un job, enviando task a workers READY
    CONFIG:  Todos los workers terminaron, reseteando para siguiente job
    """
    global manager_state, job_id, performance_metrics, job_completion_time
    
    while True:
        now = time.time()
        
        # ============ LIMPIEZA: Eliminar workers caídos ============
        for name in list(workers.keys()):
            if now - workers[name]["last_seen"] > WORKER_TIMEOUT:
                log_activity(f"Worker offline: {name}", "warning")
                add_alert(f"Worker {name} desconectado", "error")
                del workers[name]
        
        # Actualizar métricas
        if len(workers) > performance_metrics["peak_workers"]:
            performance_metrics["peak_workers"] = len(workers)
        performance_metrics["queue_size"] = len(job_queue)
        
        # ============ ESTADO: FREE ============
        # Manager está libre, buscando tasks en la cola
        # IMPORTANTE: Solo tomar un nuevo job si todos los workers están READY
        if manager_state == "free":
            if job_queue:
                # Verificar que todos los workers estén en READY antes de asignar nuevo job
                # Esto garantiza que los workers se resetearon después del job anterior
                if workers:
                    ready_count = sum(1 for w in workers.values() if w["status"] == "ready")
                    done_count = sum(1 for w in workers.values() if w["status"] == "done")
                    
                    # Si todavía hay workers en DONE, esperar a que se reseteen
                    if done_count > 0:
                        if int(now) % 5 == 0:  # Log cada 5 segundos
                            log_activity(f"Esperando que workers se reseteen ({done_count} aún en DONE)", "info")
                        time.sleep(1)
                        continue
                    
                    # Si no hay workers READY, esperar
                    if ready_count == 0:
                        time.sleep(1)
                        continue
                
                # Todos los workers están READY (o no hay workers), tomar el siguiente job
                next_job = job_queue.popleft()
                
                # Configurar el nuevo job
                job["blend_file"] = next_job["blend_file"]
                job["output_path"] = next_job.get("output_path", "")
                job["total_frames"] = next_job.get("total_frames", 0)
                job["completed_frames"] = 0
                job["frame_range"] = next_job.get("frame_range", {"start": 1, "end": 250})
                job["resolution"] = next_job.get("resolution", {"x": 1920, "y": 1080})
                job["render_engine"] = next_job.get("render_engine", "CYCLES")
                job["start_time"] = time.time()
                
                # Cambiar a WORKING
                manager_state = "working"
                job_completion_time = None
                
                log_activity(f"Job {job_id} iniciado: {job['blend_file']} ({len(job_queue)} en cola)", "info")
                add_alert(f"Iniciando: {next_job['blend_file']}", "info")
        
        # ============ ESTADO: WORKING ============
        # Manager está procesando un job activo
        elif manager_state == "working" and job["blend_file"]:
            # Contar workers por estado
            ready_count = sum(1 for w in workers.values() if w["status"] == "ready")
            rendering_count = sum(1 for w in workers.values() if w["status"] == "rendering")
            done_count = sum(1 for w in workers.values() if w["status"] == "done")
            
            # Log periódico (cada 10 segundos)
            if int(now) % 10 == 0:
                log_activity(f"Workers: {ready_count} ready, {rendering_count} rendering, {done_count} done", "info")
            
            # Los workers en READY consultarán /job y tomarán la task automáticamente
            # El manager solo necesita verificar cuando todos terminan
            
            # Verificar si todos los workers están DONE
            # IMPORTANTE: Solo pasar a CONFIG si:
            # 1. Hay al menos un worker
            # 2. TODOS están en DONE (ninguno en ready o rendering)
            # 3. Al menos uno está en DONE (para evitar transición inmediata)
            if workers and done_count == len(workers) and done_count > 0 and rendering_count == 0 and ready_count == 0:
                log_activity(f"Todos los workers ({done_count}) completaron el job {job_id}", "success")
                manager_state = "config"
                job_completion_time = time.time()
        
        # ============ ESTADO: CONFIG ============
        # Todos los workers terminaron, guardar historial y resetear
        elif manager_state == "config":
            log_activity(f"Estado CONFIG: Finalizando job {job_id}", "info")
            
            # Guardar job en historial
            if job["blend_file"]:
                elapsed_time = time.time() - job["start_time"] if job["start_time"] else 0
                job["completed_frames"] = count_rendered_frames(job["output_path"], job["total_frames"])
                
                job_history.append({
                    "job_id": job_id,
                    "blend_file": job["blend_file"],
                    "output_path": job["output_path"],
                    "total_frames": job["total_frames"],
                    "completed_frames": job["completed_frames"],
                    "duration": elapsed_time,
                    "workers_used": len(workers),
                    "completed_at": time.time(),
                    "datetime": datetime.now().isoformat()
                })
                
                save_history(job_history)
                
                performance_metrics["total_jobs_completed"] += 1
                performance_metrics["total_render_time"] += elapsed_time
                
                log_activity(f"Job {job_id} guardado en historial: {job['blend_file']}", "success")
                add_alert(f"Job completado: {job['blend_file']}", "success")
            
            # Limpiar job actual
            job["blend_file"] = None
            job["output_path"] = None
            job["start_time"] = None
            job["completed_frames"] = 0
            
            # Incrementar job_id para el siguiente job
            job_id += 1
            
            # Los workers se resetearán a READY cuando vean que el manager está en FREE
            # y no hay job activo (blend_file = None)
            
            # Cambiar a FREE
            manager_state = "free"
            log_activity(f"Manager listo para siguiente job (esperando workers READY)", "info")
        
        time.sleep(1)

class Handler(BaseHTTPRequestHandler):
    def _set_headers(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_OPTIONS(self):
        self._set_headers()
    
    def _json(self, data, code=200):
        self._set_headers(code)
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        pass  # Silenciar logs HTTP
    
    def do_GET(self):
        try:
            self._handle_GET()
        except ConnectionAbortedError:
            pass  # Client disconnected, ignore silently
        except Exception as e:
            try:
                log_activity(f"GET error: {e}", "error")
                self.send_error(500)
            except:
                pass
    
    def _handle_GET(self):
        if self.path == "/" or self.path == "/dashboard":
            # Intentar servir el HTML si es una solicitud del navegador
            if "text/html" in self.headers.get("Accept", ""):
                try:
                    html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "index.html"))
                    with open(html_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(html_content.encode('utf-8'))
                    return
                except Exception as e:
                    log_activity(f"Error sirviendo HTML: {e}", "error")
            
            # Si no es HTML, retornar JSON (para API)
            self._json({
                "manager_state": manager_state,
                "job_id": job_id,
                "job": job,
                "workers": list(workers.values()),
                "job_progress": calculate_job_progress(),
                "performance_metrics": performance_metrics,
                "timestamp": time.time()
            })
        elif self.path == "/job":
            if manager_state == "working" and job["blend_file"]:
                self._json({
                    "job_id": job_id,
                    "blend_file": job["blend_file"],
                    "total_frames": job["total_frames"],
                    "frame_range": job["frame_range"],
                    "resolution": job["resolution"],
                    "render_engine": job["render_engine"]
                })
            else:
                self._json({"job_id": job_id, "blend_file": None})
        elif self.path == "/history":
            self._json({"jobs": list(job_history)})
        elif self.path == "/logs":
            self._json({
                "activity": list(activity_log),
                "errors": list(error_log)
            })
        elif self.path == "/alerts":
            self._json({"alerts": list(alerts)})
        elif self.path == "/queue":
            self._json({"queue": list(job_queue), "size": len(job_queue)})
        elif self.path == "/preview_history":
            history_with_frames = []
            for hist_job in job_history:
                render_dir = get_render_dir(hist_job.get("output_path", ""))
                job_frames = sorted([f for f in os.listdir(render_dir) if f.lower().endswith(IMAGE_EXTENSIONS)]) if render_dir and os.path.exists(render_dir) else []
                history_with_frames.append({
                    "job_id": hist_job["job_id"],
                    "blend_file": hist_job["blend_file"],
                    "output_path": hist_job["output_path"],
                    "total_frames": hist_job["total_frames"],
                    "completed_frames": hist_job["completed_frames"],
                    "duration": hist_job["duration"],
                    "datetime": hist_job["datetime"],
                    "preview_frames": job_frames
                })
            self._json({"history": history_with_frames, "count": len(history_with_frames)})
        elif self.path.startswith("/preview"):
            try:
                render_dir = get_render_dir(job["output_path"])
                if not render_dir or not os.path.exists(render_dir):
                    self._json({"images": [], "count": 0})
                    return
                
                images = sorted([f for f in os.listdir(render_dir) if f.lower().endswith(IMAGE_EXTENSIONS)])
                
                if self.path == "/preview":
                    self._json({"images": images, "count": len(images)})
                    return
                
                # Solicitud de imagen específica
                filename = self.path.split("/preview/")[1]
                if ".." in filename or "/" in filename:
                    self.send_error(403)
                    return
                
                filepath = None
                for search_dir in [render_dir] + [get_render_dir(h.get("output_path", "")) for h in job_history]:
                    search_dir = search_dir or ""
                    if not search_dir or not os.path.exists(search_dir):
                        continue
                    test_path = os.path.join(search_dir, filename)
                    if os.path.exists(test_path):
                        filepath = test_path
                        break
                
                if not filepath:
                    self.send_error(404)
                    return
                
                ext = os.path.splitext(filename)[1].lower()
                mime_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', 
                             '.exr': 'application/octet-stream', '.tiff': 'image/tiff', '.bmp': 'image/bmp'}
                
                self.send_response(200)
                self.send_header('Content-type', mime_types.get(ext, 'application/octet-stream'))
                self.end_headers()
                with open(filepath, 'rb') as f:
                    self.wfile.write(f.read())
            except ConnectionAbortedError:
                pass  # Conexión cerrada por cliente, ignorar silenciosamente
            except Exception as e:
                try:
                    log_activity(f"Error sirviendo preview: {e}", "error")
                    self.send_error(500)
                except:
                    pass  # Ignorar si la conexión ya fue cerrada
        elif self.path == "/worker_config":
            worker_config = load_worker_config()
            self._json(worker_config)
        else:
            try:
                self.send_error(404)
            except:
                pass
    
    def do_POST(self):
        try:
            self._handle_POST()
        except ConnectionAbortedError:
            pass  # Client disconnected, ignore silently
        except Exception as e:
            try:
                log_activity(f"POST error: {e}", "error")
                self.send_error(500)
            except:
                pass
    
    def _handle_POST(self):
        global manager_state, job_id, job_completion_time, job
        
        content_length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(content_length).decode())
        
        if self.path == "/heartbeat":
            name = data["name"]
            
            # Registrar nuevo worker
            if name not in workers:
                workers[name] = {
                    "name": name,
                    "status": "ready",
                    "job_id": None,
                    "connected_at": time.time(),
                    "jobs_completed": 0,
                    "frames_rendered": 0,
                    "success_rate": 100.0,
                    "ip": data.get("ip", "unknown")
                }
                log_activity(f"Worker conectado: {name}", "info")
                add_alert(f"Worker {name} conectado", "info")
            
            # Actualizar información del worker
            workers[name]["status"] = data["status"]
            workers[name]["last_seen"] = time.time()
            workers[name]["job_id"] = data.get("job_id")
            workers[name]["ip"] = data.get("ip", "unknown")
            workers[name]["frames_rendered"] = data.get("frames_rendered", 0)
            workers[name]["jobs_completed"] = data.get("jobs_completed", 0)
            
            # Guardar system_info si viene
            if "system_info" in data:
                workers[name]["system_info"] = data["system_info"]
            
            # Responder con el estado del manager para que el worker sepa qué hacer
            self._json({
                "ok": True, 
                "manager_state": manager_state, 
                "job_id": job_id
            })
        
        elif self.path == "/set_job":
            job_data = {
                "blend_file": data["blend_file"],
                "output_path": data.get("output_path", ""),
                "total_frames": data.get("total_frames", 0),
                "frame_range": data.get("frame_range", {"start": 1, "end": 250}),
                "resolution": data.get("resolution", {"x": 1920, "y": 1080}),
                "render_engine": data.get("render_engine", "CYCLES")
            }
            
            # TODAS las solicitudes van a la cola
            job_queue.append(job_data)
            log_activity(f"Job en cola: {job_data['blend_file']} (posición {len(job_queue)})", "info")
            add_alert(f"Job en cola: {job_data['blend_file']}", "warning")
            
            self._json({"ok": True, "queued": True, "position": len(job_queue)})
        
        elif self.path == "/report_error":
            error_log.append({
                "timestamp": time.time(),
                "worker": data.get("worker"),
                "error": data.get("error"),
                "frame": data.get("frame"),
                "datetime": datetime.now().isoformat()
            })
            log_activity(f"Error: {data.get('error')}", "error")
            add_alert(f"Error: {data.get('error')}", "error")
            self._json({"ok": True})
        
        elif self.path == "/open-browser":
            webbrowser.open(f"http://localhost:{PORT}/")
            self._json({"ok": True})
        
        else:
            self.send_error(404)

print(f"[START] Render Manager iniciado en http://localhost:{PORT}")
log_activity("Manager iniciado", "success")

threading.Thread(target=manager_loop, daemon=True).start()

# Abrir dashboard automáticamente en thread separado
def open_browser_thread():
    time.sleep(1)
    webbrowser.open(f"http://localhost:{PORT}/")

threading.Thread(target=open_browser_thread, daemon=True).start()

HTTPServer((HOST, PORT), Handler).serve_forever()
