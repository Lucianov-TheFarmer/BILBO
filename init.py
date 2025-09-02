import subprocess
import time
import signal
import psutil
import sys
import threading
import logging
import yaml
import requests
import platform
import socket
import json
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

BUILD = False

def run_command(command):
    logger.debug(f"Running command: {command}")
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process

def run_command_dynamic_output(command):
    logger.debug(f"Running command with dynamic output: {command}")
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            sys.stdout.write("\r" + output.strip())
            sys.stdout.flush()
    rc = process.poll()
    return rc

def stop_containers():
    logger.info("Stopping Docker containers...")
    down_process = run_command("docker-compose down")
    down_process.wait()

def signal_handler(sig, frame):
    logger.info("\nInterrupt received, stopping containers...")
    stop_containers()
    sys.exit(0)

def is_docker_running():
    try:
        subprocess.run(["docker", "info"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def start_docker():
    os_type = platform.system()
    logger.info(f"🐳 Starting Docker on {os_type}...")
    if os_type == "Windows":
        docker_desktop_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
        subprocess.Popen([docker_desktop_path], shell=True)
    elif os_type == "Linux":
        run_command("sudo systemctl start docker")
    else:
        logger.warning(f"Unsupported OS: {os_type}. Docker may need to be started manually.")
    time.sleep(30)

def is_docker_desktop_running():
    os_type = platform.system()
    if os_type == "Windows":
        for process in psutil.process_iter(['name']):
            if process.info['name'] == 'Docker Desktop.exe':
                return True
        return False
    elif os_type == "Linux":
        try:
            result = subprocess.run(["systemctl", "is-active", "docker"], capture_output=True, text=True)
            return result.stdout.strip() == "active"
        except FileNotFoundError:
            return False # systemctl não encontrado
    return False

def get_server_ip():
    """Detecta IP do servidor (público se possível, senão local)"""
    try:
        # Tentar obter IP público a partir do container SSH
        result = subprocess.run([
            "docker", "exec", "ssh-container", 
            "curl", "-s", "https://ipinfo.io/ip"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        logger.debug(f"Failed to get IP from SSH container: {e}")
    
    try:
        # Fallback: IP público do host
        response = requests.get('https://ipinfo.io/ip', timeout=5)
        return response.text.strip()
    except:
        # Fallback final: IP local
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "localhost"
        
def wait_for_ssh_ready(timeout=30):
    """Aguarda SSH container estar pronto"""
    logger.info("🔑 Waiting for SSH server...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            # Verificar se a porta 2222 está respondendo
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('localhost', 2222))
            sock.close()
            if result == 0:
                return True
        except:
            pass
        time.sleep(2)
    return False

def display_startup_banner():
    """Mostra banner de inicialização"""
    print("\n" + "=" * 90)
    print()
    print(" " * 28 + "██████╗ ██╗██╗     ██████╗  ██████╗ ")
    print(" " * 28 + "██╔══██╗██║██║     ██╔══██╗██╔═══██╗")
    print(" " * 28 + "██████╔╝██║██║     ██████╔╝██║   ██║")
    print(" " * 28 + "██╔══██╗██║██║     ██╔══██╗██║   ██║")
    print(" " * 28 + "██████╔╝██║███████╗██████╔╝╚██████╔╝")
    print(" " * 28 + "╚═════╝ ╚═╝╚══════╝╚═════╝  ╚═════╝ ")
    print()
    print(" " * 3 + "Bioinformatics Integration for Large-scale Biological Operations in RNA-seq Analysis")
    print()
    print(" " * 31 + "Universidade Federal de Lavras")
    print(" " * 3 + "Silva, V.L.C.; Alvarenga, J.V.R.; Linhares-Neto, M.V.; Noman, M.; Chalfun-Junior, A.")
    print()
    print("=" * 90)
    print()

def display_ssh_connection_info():
    """Mostra informações de conexão SSH em formato elegante"""
    server_ip = get_server_ip()
    
    print("\n" + "=" * 90)
    print("🔧 SSH CONNECTION READY 🔧")
    print("=" * 90)
    print(f"🌐 Server IP    : {server_ip}")
    print(f"🔌 SSH Port     : 2222")
    print(f"👤 User         : bilbo")
    print(f"🔐 Password     : bilbo123")
    print(f"⏰ Started at   : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)
    print()
    print("📋 CONNECTION COMMAND:")
    print("─" * 90)
    print(f"ssh -L 8000:bioinfo-container:8000 bilbo@{server_ip} -p 2222")
    print("─" * 90)
    print()
    print("🌍 ACCESS URL:")
    print("─" * 90)
    print("http://localhost:8000/frontend")
    print("─" * 90)
    print()
    print("📝 NOTES:")
    print("• Multiple users can use the same command simultaneously")
    print("• Each user will have their own isolated session")
    print("• Keep this terminal open while using the application")
    print()
    print("🚀 Application is ready! Press Ctrl+C to stop.")
    print("=" * 90)

def wait_for_backend_ready(url="http://localhost:8000/docs", timeout=60):
    logger.info("⚙️  Starting FastAPI backend...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url)
            if r.status_code == 200:
                logger.info("✅ FastAPI backend is ready!")
                return True
        except Exception:
            pass
        time.sleep(1)
    logger.error("❌ Timeout waiting for the FastAPI backend.")
    return False

def main():
    # Mostrar banner de inicialização
    display_startup_banner()
    
    if not is_docker_running():
        if not is_docker_desktop_running():
            start_docker()
            if not is_docker_running():
                logger.error("❌ Failed to start Docker. Please start Docker manually.")
                return

    try:
        if BUILD:
            logger.info("\n🔨 Building Docker containers...\n")
            build_rc = run_command_dynamic_output("docker-compose build")
            if build_rc != 0:
                logger.error("❌ Docker build failed.")
                stop_containers()
                sys.exit(1)

        logger.info("🚀 Starting Docker containers...")
        up_process = run_command("docker-compose up -d")
        up_process.wait()
        logger.info("✅ Docker containers started!")

        # Wait for the backend to be ready
        if not wait_for_backend_ready():
            return

        # Wait for SSH server to be ready
        if wait_for_ssh_ready():
            logger.info("✅ SSH server is ready!")
            
            # Mostrar informações de conexão
            display_ssh_connection_info()
            
            # Aguardar indefinidamente
            while True:
                time.sleep(1)
        else:
            logger.error("❌ SSH server failed to start")

    except Exception as e:
        logger.error(f"❌ An error occurred: {e}")
        stop_containers()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    main()