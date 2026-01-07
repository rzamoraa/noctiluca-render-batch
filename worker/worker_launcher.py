"""
Noctiluca Worker Launcher - Auto-updater
Descarga automáticamente la última versión del worker desde GitHub
"""
import urllib.request
import os
import sys
import subprocess
import time
import hashlib

# ============ CONFIGURACIÓN ============
GITHUB_RAW_URL = "https://raw.githubusercontent.com/rzamoraa/noctiluca-render-batch/main/worker/worker.py"
GITHUB_CONFIG_URL = "https://raw.githubusercontent.com/rzamoraa/noctiluca-render-batch/main/worker/worker_config.xml"
LOCAL_WORKER = "worker.py"
LOCAL_CONFIG = "worker_config.xml"
VERSION_FILE = ".worker_version"
# =======================================

def get_base_path():
    """Obtiene la ruta base del ejecutable o script"""
    if getattr(sys, 'frozen', False):
        # Ejecutando como .exe (PyInstaller)
        return os.path.dirname(sys.executable)
    else:
        # Ejecutando como script .py
        return os.path.dirname(os.path.abspath(__file__))

def download_file(url, local_path):
    """Descarga un archivo desde URL"""
    try:
        print(f"📥 Descargando: {url}")
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read()
            with open(local_path, 'wb') as f:
                f.write(content)
            return content
    except Exception as e:
        print(f"❌ Error descargando {url}: {e}")
        return None

def get_file_hash(filepath):
    """Calcula hash MD5 de un archivo"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def check_for_updates(base_path):
    """Verifica si hay actualizaciones disponibles"""
    worker_path = os.path.join(base_path, LOCAL_WORKER)
    
    # Obtener hash actual
    current_hash = get_file_hash(worker_path)
    
    # Descargar nueva versión a memoria para comparar
    try:
        print("🔍 Verificando actualizaciones...")
        with urllib.request.urlopen(GITHUB_RAW_URL, timeout=30) as response:
            new_content = response.read()
            new_hash = hashlib.md5(new_content).hexdigest()
            
            if current_hash != new_hash:
                print("✨ Nueva versión disponible!")
                # Guardar nueva versión
                with open(worker_path, 'wb') as f:
                    f.write(new_content)
                print("✅ Worker actualizado!")
                return True
            else:
                print("✅ Worker está actualizado")
                return False
    except Exception as e:
        print(f"⚠️ No se pudo verificar actualizaciones: {e}")
        return False

def ensure_config_exists(base_path):
    """Asegura que existe el archivo de configuración"""
    config_path = os.path.join(base_path, LOCAL_CONFIG)
    
    if not os.path.exists(config_path):
        print("📝 Creando configuración inicial...")
        # Intentar descargar config de ejemplo desde GitHub
        download_file(GITHUB_CONFIG_URL, config_path)
        
        if not os.path.exists(config_path):
            # Crear config por defecto
            default_config = """<?xml version="1.0" encoding="UTF-8"?>
<config>
    <manager>
        <ip>192.168.1.100</ip>
        <port>8000</port>
    </manager>
    <identity>
        <name>WORKER-01</name>
    </identity>
    <blender>
        <path>C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe</path>
    </blender>
</config>"""
            with open(config_path, 'w') as f:
                f.write(default_config)
            print("⚠️ IMPORTANTE: Edita worker_config.xml con la IP del manager!")
            input("Presiona ENTER cuando hayas configurado el archivo...")

def run_worker(base_path):
    """Ejecuta el worker"""
    worker_path = os.path.join(base_path, LOCAL_WORKER)
    
    if not os.path.exists(worker_path):
        print("❌ No se encontró worker.py")
        return False
    
    print("\n" + "="*50)
    print("🚀 Iniciando Noctiluca Worker...")
    print("="*50 + "\n")
    
    # Ejecutar worker.py
    try:
        # Cambiar al directorio del worker
        os.chdir(base_path)
        
        # Leer y ejecutar el código del worker
        with open(worker_path, 'r', encoding='utf-8') as f:
            worker_code = f.read()
        
        # Ejecutar el worker en el contexto actual
        exec(worker_code, {'__name__': '__main__', '__file__': worker_path})
        
    except KeyboardInterrupt:
        print("\n⏹️ Worker detenido por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando worker: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    print("""
    ╔══════════════════════════════════════════════════╗
    ║      🌙 NOCTILUCA RENDER - WORKER LAUNCHER       ║
    ║              Auto-Update System                  ║
    ╚══════════════════════════════════════════════════╝
    """)
    
    base_path = get_base_path()
    print(f"📂 Directorio: {base_path}\n")
    
    # Asegurar que existe la configuración
    ensure_config_exists(base_path)
    
    # Verificar actualizaciones
    check_for_updates(base_path)
    
    # Ejecutar worker
    run_worker(base_path)

if __name__ == "__main__":
    main()
