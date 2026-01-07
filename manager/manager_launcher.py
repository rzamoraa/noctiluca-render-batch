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
LOCAL_MANAGER = "manager.py"
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
    
    # Obtener hash actual
    current_hash = get_file_hash(manager_path)
    
    print("")
    print("=" * 50)
    print("🔍 VERIFICANDO ACTUALIZACIONES...")
    print("=" * 50)
    
    if current_hash:
        print(f"📄 Archivo local: {LOCAL_MANAGER}")
        print(f"🔑 Hash local:    {current_hash[:16]}...")
    else:
        print(f"📄 Archivo local: NO EXISTE (primera ejecución)")
    
    # Descargar nueva versión a memoria para comparar
    try:
        print(f"\n🌐 Conectando a GitHub...")
        with urllib.request.urlopen(GITHUB_RAW_URL, timeout=30) as response:
            new_content = response.read()
            new_hash = hashlib.md5(new_content).hexdigest()
            
            print(f"🔑 Hash remoto:   {new_hash[:16]}...")
            
            if current_hash != new_hash:
                print("")
                print("╔══════════════════════════════════════════════════╗")
                print("║     ✨ ¡NUEVA VERSIÓN DISPONIBLE! ✨              ║")
                print("╚══════════════════════════════════════════════════╝")
                print(f"📥 Descargando actualización...")
                
                # Guardar nueva versión
                with open(manager_path, 'wb') as f:
                    f.write(new_content)
                
                print(f"✅ Manager actualizado correctamente!")
                print(f"📦 Tamaño: {len(new_content)} bytes")
                print("")
                time.sleep(2)
                return True
            else:
                print("")
                print("╔══════════════════════════════════════════════════╗")
                print("║     ✅ MANAGER YA ESTÁ ACTUALIZADO               ║")
                print("╚══════════════════════════════════════════════════╝")
                print("")
                time.sleep(1)
                return False
    except Exception as e:
        print("")
        print("╔══════════════════════════════════════════════════╗")
        print("║     ⚠️  NO SE PUDO VERIFICAR ACTUALIZACIONES     ║")
        print("╚══════════════════════════════════════════════════╝")
        print(f"Error: {e}")
        print("Continuando con versión local...")
        print("")
        time.sleep(2)
        return False

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
