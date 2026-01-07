"""
Noctiluca Manager Launcher - Auto-updater
Descarga automáticamente la última versión del manager desde GitHub
"""
import urllib.request
import os
import sys
import time
import hashlib
import ctypes

# ============ CONFIGURACIÓN ============
LAUNCHER_VERSION = "1.0 pre-release"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/rzamoraa/noctiluca-render-batch/main/manager/manager.py"
GITHUB_INDEX_URL = "https://raw.githubusercontent.com/rzamoraa/noctiluca-render-batch/main/index.html"
LOCAL_MANAGER = "manager.py"
LOCAL_INDEX = "index.html"
# =======================================

# Establecer título de la consola
if sys.platform == "win32":
    ctypes.windll.kernel32.SetConsoleTitleW(f"Noctiluca Manager v{LAUNCHER_VERSION}")

def get_base_path():
    """Obtiene la ruta base del ejecutable o script"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def get_file_hash(filepath):
    """Calcula hash MD5 de un archivo"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def check_for_updates(base_path):
    """Verifica si hay actualizaciones disponibles"""
    manager_path = os.path.join(base_path, LOCAL_MANAGER)
    index_path = os.path.join(base_path, LOCAL_INDEX)
    
    print("")
    print("=" * 50)
    print("🔍 VERIFICANDO ACTUALIZACIONES...")
    print("=" * 50)
    
    # ---- Actualizar manager.py ----
    current_hash = get_file_hash(manager_path)
    
    if current_hash:
        print(f"📄 {LOCAL_MANAGER}: {current_hash[:16]}...")
    else:
        print(f"📄 {LOCAL_MANAGER}: NO EXISTE")
    
    try:
        print(f"🌐 Conectando a GitHub...")
        with urllib.request.urlopen(GITHUB_RAW_URL, timeout=30) as response:
            new_content = response.read()
            new_hash = hashlib.md5(new_content).hexdigest()
            
            if current_hash != new_hash:
                with open(manager_path, 'wb') as f:
                    f.write(new_content)
                print(f"✅ {LOCAL_MANAGER} actualizado! ({len(new_content)} bytes)")
            else:
                print(f"✅ {LOCAL_MANAGER} está actualizado")
    except Exception as e:
        print(f"⚠️ No se pudo actualizar {LOCAL_MANAGER}: {e}")
    
    # ---- Actualizar index.html ----
    current_index_hash = get_file_hash(index_path)
    
    if current_index_hash:
        print(f"📄 {LOCAL_INDEX}: {current_index_hash[:16]}...")
    else:
        print(f"📄 {LOCAL_INDEX}: NO EXISTE")
    
    try:
        with urllib.request.urlopen(GITHUB_INDEX_URL, timeout=30) as response:
            new_index_content = response.read()
            new_index_hash = hashlib.md5(new_index_content).hexdigest()
            
            if current_index_hash != new_index_hash:
                with open(index_path, 'wb') as f:
                    f.write(new_index_content)
                print(f"✅ {LOCAL_INDEX} actualizado! ({len(new_index_content)} bytes)")
            else:
                print(f"✅ {LOCAL_INDEX} está actualizado")
    except Exception as e:
        print(f"⚠️ No se pudo actualizar {LOCAL_INDEX}: {e}")
    
    print("")
    print("╔══════════════════════════════════════════════════╗")
    print("║     ✅ VERIFICACIÓN COMPLETADA                   ║")
    print("╚══════════════════════════════════════════════════╝")
    print("")
    time.sleep(1)

def run_manager(base_path):
    """Ejecuta el manager"""
    manager_path = os.path.join(base_path, LOCAL_MANAGER)
    
    if not os.path.exists(manager_path):
        print("❌ No se encontró manager.py")
        return False
    
    print("\n" + "="*50)
    print("🚀 Iniciando Noctiluca Manager...")
    print("="*50 + "\n")
    
    try:
        os.chdir(base_path)
        
        with open(manager_path, 'r', encoding='utf-8') as f:
            manager_code = f.read()
        
        exec(manager_code, {'__name__': '__main__', '__file__': manager_path})
        
    except KeyboardInterrupt:
        print("\n⏹️ Manager detenido por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando manager: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    print(f"""
    ╔══════════════════════════════════════════════════╗
    ║      🌙 NOCTILUCA RENDER - MANAGER LAUNCHER      ║
    ║              v{LAUNCHER_VERSION}                         ║
    ╚══════════════════════════════════════════════════╝
    """)
    
    base_path = get_base_path()
    print(f"📂 Directorio: {base_path}\n")
    
    # Verificar actualizaciones
    check_for_updates(base_path)
    
    # Ejecutar manager
    run_manager(base_path)

if __name__ == "__main__":
    main()
