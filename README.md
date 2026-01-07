# 🎬 Noctiluca Render Batch

Sistema de render distribuido para Blender. Permite renderizar proyectos en múltiples computadores (nodos) de forma simultánea, coordinados por un manager central.

## 📋 Arquitectura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     BLENDER     │     │     MANAGER     │     │     WORKERS     │
│     (Addon)     │────▶│   (PC Main)     │────▶│   (PC Nodos)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
   Envía tasks            Coordina y               Renderizan
   a la cola              distribuye               los frames
```

## 🔄 Estados del Sistema

### Manager (PC Principal)
| Estado | Descripción |
|--------|-------------|
| `FREE` | Esperando tasks en la cola. Verifica que todos los workers estén READY antes de tomar un nuevo job |
| `WORKING` | Procesando un job activo. Los workers en READY toman la task automáticamente |
| `CONFIG` | Todos los workers terminaron. Guarda historial y prepara el siguiente job |

### Workers (PCs Nodos)
| Estado | Descripción |
|--------|-------------|
| `READY` | Listo para recibir una task |
| `RENDERING` | Ejecutando Blender (renderizando) |
| `DONE` | Task completada, esperando que todos los nodos terminen |

## 🔁 Flujo de Trabajo

```
1. Addon envía task ──▶ Queue List (cola de espera)
2. Manager (FREE) consulta cola ──▶ Si hay task, pasa a WORKING
3. Manager (WORKING) ──▶ Workers (READY) consultan /job y toman la task
4. Workers renderizan ──▶ Al terminar pasan a DONE
5. Cuando TODOS los workers están DONE ──▶ Manager pasa a CONFIG
6. Manager (CONFIG) ──▶ Guarda historial, limpia job
7. Manager pasa a FREE ──▶ Workers se resetean a READY
8. Si hay más tasks en cola ──▶ Vuelve al paso 2
```

## 📁 Estructura del Proyecto

```
noctiluca-render-batch/
├── addon/
│   └── noctiluca_render_manager.py   # Addon para Blender
├── manager/
│   ├── manager.py                     # Servidor principal
│   └── job_history.json               # Historial de jobs
├── worker/
│   ├── worker.py                      # Cliente de renderizado
│   └── worker_config.xml              # Configuración del worker
├── index.html                         # Dashboard web
└── README.md
```

## 🚀 Instalación

### Manager (PC Principal)

1. Ejecutar el manager:
```bash
cd manager
python manager.py
```

2. El dashboard se abrirá automáticamente en `http://localhost:8000`

### Workers (PCs Nodos)

1. Configurar `worker/worker_config.xml`:
```xml
<config>
    <manager>
        <ip>192.168.1.100</ip>  <!-- IP del PC con el manager -->
        <port>8000</port>
    </manager>
    <identity>
        <name>NODO-01</name>  <!-- Nombre único del worker -->
    </identity>
    <blender>
        <path>C:\Program Files\Blender Foundation\Blender 4.0\blender.exe</path>
    </blender>
</config>
```

2. Ejecutar el worker:
```bash
cd worker
python worker.py
```

### Addon de Blender

1. En Blender: `Edit > Preferences > Add-ons > Install`
2. Seleccionar `addon/noctiluca_render_manager.py`
3. Activar el addon "Noctiluca Render Manager"
4. Configurar la IP del manager en las preferencias del addon

## 💻 Dashboard

El dashboard web muestra:
- **Vista General**: Estado del manager, job actual, cola de trabajos, workers activos
- **Workers**: Detalles de cada nodo conectado
- **Historial**: Jobs completados
- **Logs**: Actividad del sistema y errores

## ⚙️ Configuración

### Timeouts
En `manager.py`:
```python
WORKER_TIMEOUT = 10  # Segundos sin heartbeat para considerar worker offline
```

### Heartbeat
En `worker.py`:
```python
time.sleep(2)  # Intervalo de heartbeat en segundos
```

## 🔧 Requisitos

- Python 3.8+
- Blender 2.80+ (en cada nodo worker)
- Red local entre todos los equipos

### Dependencias Python (opcionales)
```bash
pip install psutil  # Para métricas de CPU/RAM en workers
```

## 📝 Notas Importantes

1. **Todos los nodos deben tener acceso al archivo .blend** - Usar rutas de red compartidas
2. **El manager debe estar ejecutándose antes que los workers**
3. **Los workers nuevos pueden unirse en cualquier momento** - Tomarán automáticamente el job activo
4. **La cola de trabajos persiste** - Los jobs esperan hasta que haya workers disponibles

## 🐛 Troubleshooting

### Worker no conecta
- Verificar IP del manager en `worker_config.xml`
- Verificar que el firewall permita el puerto 8000
- Verificar que el manager esté ejecutándose

### Render no inicia
- Verificar ruta de Blender en `worker_config.xml`
- Verificar que el archivo .blend sea accesible desde el worker

### Job se marca como completado inmediatamente
- Verificar que todos los workers se resetearon a READY antes del nuevo job
- El manager espera que todos estén READY antes de asignar un nuevo job

## 📄 Licencia

MIT License

## 👤 Autor

Rodolfo Zamora (rzamoraa)

---

## 🔄 Sistema de Auto-Actualización

Los ejecutables (`.exe`) descargan automáticamente la última versión desde GitHub al iniciar.

### ¿Qué se actualiza automáticamente?

| Archivo | Se actualiza solo | Necesita recompilar .exe |
|---------|-------------------|--------------------------|
| `worker.py` | ✅ Sí | ❌ No |
| `manager.py` | ✅ Sí | ❌ No |
| `index.html` | ✅ Sí | ❌ No |
| `worker_launcher.py` | ❌ No | ✅ Sí |
| `manager_launcher.py` | ❌ No | ✅ Sí |
| Iconos (.ico) | ❌ No | ✅ Sí |

### Flujo de desarrollo

```
1. Modificas worker.py, manager.py o index.html en VS Code
2. git add -A && git commit -m "mensaje" && git push
3. Los ejecutables descargan la nueva versión al reiniciar
```

### Archivos en cada PC

**PC Manager:**
```
📁 Manager/
   NoctilucaManager.exe    ← Solo este se distribuye una vez
   manager.py              ← Se descarga automáticamente
   index.html              ← Se descarga automáticamente
```

**PC Workers (nodos):**
```
📁 Worker/
   NoctilucaWorker.exe     ← Solo este se distribuye una vez
   worker_config.xml       ← Configurar manualmente (IP, nombre, Blender)
   worker.py               ← Se descarga automáticamente
```

### Recompilar ejecutables (solo si cambias los launchers)

```bash
# Worker
cd worker
py -m PyInstaller --onefile --name "NoctilucaWorker" --console --icon="workerico.ico" --hidden-import=xml --hidden-import=xml.etree --hidden-import=xml.etree.ElementTree --hidden-import=ctypes worker_launcher.py

# Manager  
cd manager
py -m PyInstaller --onefile --name "NoctilucaManager" --console --icon="managerico.ico" --hidden-import=xml --hidden-import=xml.etree --hidden-import=xml.etree.ElementTree --hidden-import=ctypes --hidden-import=http.server --hidden-import=webbrowser manager_launcher.py
```

### Versión actual
- **Worker:** v1.1
- **Manager:** v1.1
- **Launcher:** v1.0 pre-release
