# 🎬 Noctiluca Render Batch

Sistema de render distribuido para Blender. Permite renderizar proyectos en múltiples computadores (nodos) de forma simultánea, coordinados por un manager central.

---

## 📖 GUÍA PARA IA / DESARROLLADORES

> **IMPORTANTE:** Lee esta sección completa antes de modificar cualquier código. El sistema ya está funcionando correctamente. Cualquier cambio debe respetar la arquitectura y el flujo de estados establecido.

---

## 🏗️ ARQUITECTURA DEL SISTEMA

El sistema consta de **3 componentes principales** que se comunican por HTTP:

```
┌─────────────────────┐
│   BLENDER + ADDON   │  ← El usuario trabaja aquí
│  (noctiluca_render_ │
│   manager.py)       │
└──────────┬──────────┘
           │ HTTP POST /set_job
           ▼
┌─────────────────────┐
│      MANAGER        │  ← Servidor central (1 instancia)
│   (manager.py)      │
│   Puerto: 8000      │
│   + index.html      │
└──────────┬──────────┘
           │ HTTP GET /job, /heartbeat
           ▼
┌─────────────────────┐
│      WORKERS        │  ← Nodos de render (N instancias)
│    (worker.py)      │
│  Cada PC es un nodo │
└─────────────────────┘
```

---

## 📁 ESTRUCTURA DE ARCHIVOS

```
noctiluca-render-batch/
│
├── addon/
│   └── noctiluca_render_manager.py   # Addon de Blender (se instala en Blender)
│
├── manager/
│   ├── manager.py                     # Servidor HTTP + lógica de coordinación
│   ├── manager_launcher.py            # Launcher con auto-update (se compila a .exe)
│   ├── job_history.json               # Historial de jobs completados
│   └── managerico.ico                 # Icono del ejecutable
│
├── worker/
│   ├── worker.py                      # Cliente que renderiza
│   ├── worker_launcher.py             # Launcher con auto-update (se compila a .exe)
│   ├── worker_config.xml              # Configuración (IP manager, nombre, ruta Blender)
│   └── workerico.ico                  # Icono del ejecutable
│
├── index.html                         # Dashboard web (UI del manager)
└── README.md                          # Esta documentación
```

---

## 🧩 COMPONENTE 1: ADDON DE BLENDER

**Archivo:** `addon/noctiluca_render_manager.py`

### Función
- Se instala en Blender como addon
- Proporciona un panel en el sidebar (tecla N) para enviar trabajos de render
- Envía la información del proyecto al Manager via HTTP POST

### Qué envía al Manager
```python
{
    "blend_file": "D:/Projects/scene.blend",  # Ruta al archivo .blend
    "output_path": "D:/Renders/output_",      # Ruta de salida
    "start_frame": 1,                          # Frame inicial
    "end_frame": 250,                          # Frame final
    "render_engine": "CYCLES"                  # Motor de render
}
```

### Endpoint que usa
- `POST http://{manager_ip}:8000/set_job` → Envía el job a la cola

### NO MODIFICAR
- La estructura del JSON que envía (el manager y workers dependen de ella)
- El endpoint `/set_job`

---

## 🧩 COMPONENTE 2: MANAGER

**Archivo:** `manager/manager.py`

### Función
- Servidor HTTP en puerto 8000
- Coordina todos los workers
- Mantiene la cola de jobs (Queue List)
- Sirve el dashboard web (index.html)
- Guarda historial de jobs completados

### Variables Globales Importantes
```python
VERSION = "1.1"                    # Versión actual - ACTUALIZAR en cada release
HOST = "0.0.0.0"                   # Escucha en todas las interfaces
PORT = 8000                        # Puerto del servidor
WORKER_TIMEOUT = 10                # Segundos para considerar worker offline
workers = {}                       # Diccionario de workers conectados
current_job = None                 # Job actualmente en proceso
queue_list = deque()               # Cola de jobs pendientes
manager_state = "free"             # Estado actual del manager
```

### SISTEMA DE ESTADOS DEL MANAGER

```
┌────────────────────────────────────────────────────────────────┐
│                    CICLO DE ESTADOS DEL MANAGER                │
└────────────────────────────────────────────────────────────────┘

    ┌─────────┐
    │  FREE   │ ◄─────────────────────────────────────┐
    └────┬────┘                                        │
         │                                             │
         │ ¿Hay jobs en cola Y todos workers READY?    │
         │                                             │
         ▼ SÍ                                          │
    ┌─────────┐                                        │
    │ WORKING │ ── Workers renderizan ──┐              │
    └─────────┘                          │              │
                                         │              │
         ┌───────────────────────────────┘              │
         │ Todos workers terminaron (DONE)             │
         ▼                                             │
    ┌─────────┐                                        │
    │ CONFIG  │ ── Guarda historial, limpia job ──────┘
    └─────────┘
```

| Estado | Qué hace | Cuándo cambia |
|--------|----------|---------------|
| `FREE` | Espera. Verifica si hay jobs en cola Y si TODOS los workers están en READY | Pasa a WORKING cuando hay job y workers listos |
| `WORKING` | Job activo. Workers toman frames y renderizan | Pasa a CONFIG cuando TODOS los workers están en DONE |
| `CONFIG` | Guarda el job en historial, limpia current_job | Pasa a FREE inmediatamente |

### Endpoints del Manager

| Método | Endpoint | Función |
|--------|----------|---------|
| GET | `/` | Sirve index.html (dashboard) |
| GET | `/job` | Workers consultan si hay trabajo |
| GET | `/status` | Estado completo del sistema (JSON) |
| GET | `/workers` | Lista de workers conectados |
| GET | `/history` | Historial de jobs completados |
| GET | `/queue` | Cola de jobs pendientes |
| GET | `/logs` | Logs de actividad |
| POST | `/set_job` | Addon envía un nuevo job |
| POST | `/heartbeat` | Workers envían su estado |
| POST | `/clear_history` | Limpia el historial |
| POST | `/cancel_job` | Cancela el job actual |
| POST | `/remove_from_queue` | Elimina job de la cola |

### Lógica Crítica: `manager_loop()`

```python
def manager_loop():
    """Loop principal que corre en un thread separado"""
    while True:
        if manager_state == "free":
            # Verificar que TODOS los workers estén READY antes de tomar nuevo job
            all_ready = all(w["state"] == "ready" for w in workers.values())
            if queue_list and all_ready:
                # Tomar job de la cola
                current_job = queue_list.popleft()
                manager_state = "working"
        
        elif manager_state == "working":
            # Verificar si TODOS los workers terminaron
            if all(w["state"] == "done" for w in workers.values()):
                manager_state = "config"
        
        elif manager_state == "config":
            # Guardar en historial y limpiar
            save_to_history(current_job)
            current_job = None
            manager_state = "free"  # Workers se resetean a READY automáticamente
```

### NO MODIFICAR
- El flujo de estados (FREE → WORKING → CONFIG → FREE)
- La condición de esperar que TODOS los workers estén READY
- La condición de esperar que TODOS los workers estén DONE
- Los endpoints existentes (el addon y workers dependen de ellos)

---

## 🧩 COMPONENTE 3: WORKER

**Archivo:** `worker/worker.py`

### Función
- Se conecta al Manager via HTTP
- Envía heartbeat cada 2 segundos con su estado
- Consulta si hay trabajo disponible
- Ejecuta Blender en modo background para renderizar
- Reporta progreso y finalización

### Configuración (`worker_config.xml`)
```xml
<config>
    <manager>
        <ip>192.168.1.100</ip>    <!-- IP del PC con el Manager -->
        <port>8000</port>
    </manager>
    <identity>
        <name>NODO-01</name>      <!-- Nombre único de este worker -->
    </identity>
    <blender>
        <path>C:\Program Files\Blender Foundation\Blender 4.5\blender.exe</path>
    </blender>
</config>
```

### Variables Globales
```python
VERSION = "1.1"              # Versión actual - ACTUALIZAR en cada release
state = "ready"              # Estado actual del worker
current_job_id = None        # ID del job que está procesando
```

### SISTEMA DE ESTADOS DEL WORKER

```
┌────────────────────────────────────────────────────────────────┐
│                    CICLO DE ESTADOS DEL WORKER                 │
└────────────────────────────────────────────────────────────────┘

    ┌─────────┐
    │  READY  │ ◄─────────────────────────────────────┐
    └────┬────┘                                        │
         │                                             │
         │ Manager en WORKING y hay frames disponibles │
         │                                             │
         ▼                                             │
    ┌───────────┐                                      │
    │ RENDERING │ ── Blender renderizando ──┐          │
    └───────────┘                            │          │
                                             │          │
         ┌───────────────────────────────────┘          │
         │ Render completado                           │
         ▼                                             │
    ┌─────────┐                                        │
    │  DONE   │ ── Espera que Manager pase a CONFIG ──┘
    └─────────┘     (cuando TODOS los workers están DONE)
```

| Estado | Qué hace | Cuándo cambia |
|--------|----------|---------------|
| `READY` | Consulta `/job` buscando trabajo | Pasa a RENDERING cuando recibe un frame |
| `RENDERING` | Ejecuta Blender, renderiza el frame | Pasa a DONE cuando Blender termina |
| `DONE` | Espera. Sigue enviando heartbeat | Pasa a READY cuando Manager vuelve a FREE |

### Threads del Worker
```python
# Thread 1: Heartbeat (siempre activo)
def heartbeat_loop():
    """Envía estado al manager cada 2 segundos"""
    while True:
        send_heartbeat()  # POST /heartbeat con {name, state, job_id}
        time.sleep(2)

# Thread 2: Main loop
def main_loop():
    """Lógica principal de estados"""
    while True:
        if state == "ready":
            check_for_job()      # GET /job
        elif state == "rendering":
            # Ya hay un proceso de Blender corriendo
            wait_for_render()
        elif state == "done":
            check_if_reset()     # Espera señal del manager
```

### NO MODIFICAR
- El flujo de estados (READY → RENDERING → DONE → READY)
- El intervalo de heartbeat (2 segundos)
- La lógica de reset a READY (depende del manager)

---

## 🖥️ COMPONENTE 4: DASHBOARD (index.html)

**Archivo:** `index.html`

### Función
- Interfaz web para monitorear el sistema
- Se sirve desde el Manager en `http://localhost:8000`
- Actualiza datos cada 2 segundos via JavaScript

### Secciones del Dashboard

| Tab | Qué muestra |
|-----|-------------|
| **Overview** | Estado del manager, job actual, cola de trabajos, workers activos |
| **Workers** | Tabla detallada de cada worker (nombre, estado, último heartbeat, métricas) |
| **History** | Jobs completados con fecha, duración, frames renderizados |
| **Logs** | Actividad del sistema en tiempo real |

### Endpoints que consume (JavaScript)
```javascript
// Cada 2 segundos:
fetch('/status')   // Estado general
fetch('/workers')  // Lista de workers
fetch('/history')  // Historial
fetch('/logs')     // Logs
fetch('/queue')    // Cola de jobs
```

### NO MODIFICAR
- Los nombres de los endpoints (el JS depende de ellos)
- La estructura del JSON que devuelve cada endpoint

---

## 🔄 SISTEMA DE AUTO-ACTUALIZACIÓN

### Cómo funciona

Los ejecutables (`.exe`) son "launchers" que:
1. Conectan a GitHub al iniciar
2. Descargan la última versión de los archivos `.py` e `index.html`
3. Ejecutan el código descargado

```
┌──────────────────┐     ┌─────────────┐     ┌──────────────┐
│ NoctilucaWorker  │────▶│   GitHub    │────▶│  worker.py   │
│     .exe         │     │ (raw files) │     │  (ejecuta)   │
└──────────────────┘     └─────────────┘     └──────────────┘
```

### URLs de GitHub que usan los launchers
```python
# En worker_launcher.py:
GITHUB_RAW_URL = "https://raw.githubusercontent.com/rzamoraa/noctiluca-render-batch/main/worker/worker.py"

# En manager_launcher.py:
GITHUB_RAW_URL = "https://raw.githubusercontent.com/rzamoraa/noctiluca-render-batch/main/manager/manager.py"
GITHUB_INDEX_URL = "https://raw.githubusercontent.com/rzamoraa/noctiluca-render-batch/main/index.html"
```

### ¿Qué se actualiza automáticamente?

| Archivo | Auto-update | Necesita recompilar .exe |
|---------|-------------|--------------------------|
| `worker.py` | ✅ SÍ | ❌ NO |
| `manager.py` | ✅ SÍ | ❌ NO |
| `index.html` | ✅ SÍ | ❌ NO |
| `worker_launcher.py` | ❌ NO | ✅ SÍ |
| `manager_launcher.py` | ❌ NO | ✅ SÍ |
| Iconos (.ico) | ❌ NO | ✅ SÍ |
| `worker_config.xml` | ❌ NO (local) | ❌ NO |

---

## 🚀 FLUJO DE DESARROLLO

### Para hacer cambios en el sistema:

```bash
# 1. Edita el archivo (worker.py, manager.py, o index.html)

# 2. IMPORTANTE: Actualiza la versión si es un cambio significativo
#    En worker.py:   VERSION = "1.2"
#    En manager.py:  VERSION = "1.2"

# 3. Sube a GitHub
git add -A
git commit -m "Descripción del cambio"
git push

# 4. Para probar: reinicia el .exe en el PC correspondiente
#    El launcher descargará automáticamente la nueva versión
```

### ⚠️ IMPORTANTE PARA PRUEBAS

1. **NO necesitas recompilar los .exe** para probar cambios en:
   - `worker.py`
   - `manager.py`
   - `index.html`

2. **Siempre actualiza la versión** (`VERSION = "X.X"`) cuando hagas cambios
   - Esto ayuda a identificar qué versión está corriendo cada nodo
   - La versión se muestra en el título de la consola

3. **El usuario (Rodolfo) probará** reiniciando los .exe después de que hagas push

---

## 🔧 COMANDOS PARA RECOMPILAR (Solo si cambias los launchers)

```bash
# Worker
cd worker
py -m PyInstaller --onefile --name "NoctilucaWorker" --console --icon="workerico.ico" --hidden-import=xml --hidden-import=xml.etree --hidden-import=xml.etree.ElementTree --hidden-import=ctypes worker_launcher.py

# Manager  
cd manager
py -m PyInstaller --onefile --name "NoctilucaManager" --console --icon="managerico.ico" --hidden-import=xml --hidden-import=xml.etree --hidden-import=xml.etree.ElementTree --hidden-import=ctypes --hidden-import=http.server --hidden-import=webbrowser manager_launcher.py
```

---

## ⚠️ REGLAS PARA MODIFICAR CÓDIGO

### ✅ PUEDES modificar:
- Agregar nuevas funciones que no afecten el flujo de estados
- Mejorar la UI del dashboard (index.html)
- Agregar más información a los logs
- Agregar nuevos endpoints (sin modificar los existentes)
- Mejorar mensajes de error
- Agregar métricas adicionales

### ❌ NO DEBES modificar:
- El flujo de estados del Manager (FREE → WORKING → CONFIG)
- El flujo de estados del Worker (READY → RENDERING → DONE)
- Las condiciones de transición entre estados
- Los endpoints existentes (cambiar nombres o estructura de respuesta)
- El intervalo de heartbeat (2 segundos)
- El puerto del servidor (8000)
- La estructura del JSON que envía el addon

### ⚠️ SI NECESITAS modificar algo de la lista "NO DEBES":
1. Explica claramente por qué es necesario
2. Asegúrate de actualizar TODOS los componentes afectados
3. Prueba exhaustivamente antes de hacer push

---

## 🧪 VERIFICACIÓN DESPUÉS DE CAMBIOS

Después de hacer cambios, verifica:

1. **Manager inicia correctamente**
   - Dashboard se abre en `http://localhost:8000`
   - Muestra estado "FREE"

2. **Workers conectan**
   - Aparecen en el dashboard
   - Estado "READY"
   - Heartbeat actualiza cada 2 segundos

3. **Job se procesa correctamente**
   - Manager pasa a "WORKING" cuando hay job y workers ready
   - Workers pasan a "RENDERING"
   - Al terminar pasan a "DONE"
   - Manager pasa a "CONFIG" y luego "FREE"
   - Workers vuelven a "READY"

4. **Cola funciona**
   - Múltiples jobs se encolan
   - Se procesan en orden FIFO
   - Manager espera workers READY entre jobs

---

## 📊 VERSIONES ACTUALES

| Componente | Versión | Archivo |
|------------|---------|---------|
| Worker | 1.1 | `worker.py` línea 13 |
| Manager | 1.1 | `manager.py` línea 14 |
| Launcher Worker | 1.0 pre-release | `worker_launcher.py` línea 14 |
| Launcher Manager | 1.0 pre-release | `manager_launcher.py` línea 13 |

---

## 📄 Licencia

MIT License

## 👤 Autor

Rodolfo Zamora (rzamoraa)

---

## 📞 Contacto / Repositorio

- **GitHub:** https://github.com/rzamoraa/noctiluca-render-batch
- **Ejecutables compilados:** Ver carpetas `manager/dist/` y `worker/dist/`
