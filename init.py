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

# Configuration
CONFIG = {
    'build': False,
    'ssh': {
        'port': 2222,
        'user': 'bilbo',
        'password': 'bilbo123',
        'container_name': 'bioinfo-container',
        'local_port': 8000
    },
    'network': {
        'test_hosts': ['8.8.8.8', '1.1.1.1'],
        'test_port': 80,
        'excluded_ip_patterns': [r'^127\.', r'^169\.254\.', r'^0\.0\.0\.0$'],
        'timeout': 10
    },
    'ip_patterns': {
        'windows': [
            r'(?:IPv4.*?|Endereço IPv4.*?|Dirección IPv4.*?|Adresse IPv4.*?):\s*(\d+\.\d+\.\d+\.\d+)',
            r'IP.*?Address.*?:\s*(\d+\.\d+\.\d+\.\d+)',
            r'(?:Wi-Fi|Ethernet|WiFi).*?(\d+\.\d+\.\d+\.\d+)'
        ],
        'linux': [
            r'src\s+(\d+\.\d+\.\d+\.\d+)',
            r'inet\s+(\d+\.\d+\.\d+\.\d+)',
            r'inet addr:(\d+\.\d+\.\d+\.\d+)'
        ]
    },
    'commands': {
        'windows': ['ipconfig'],
        'linux': [['ip', 'route', 'get'], ['ifconfig']],
        'darwin': [['ip', 'route', 'get'], ['ifconfig']]
    }
}

def load_config():
    """Carrega configuração de arquivo externo se existir"""
    config_files = ['bilbo_config.json', 'config.json', 'bilbo_config.yaml', 'config.yaml']
    
    for config_file in config_files:
        if os.path.exists(config_file):
            try:
                logger.debug(f"Carregando configuração de {config_file}")
                with open(config_file, 'r', encoding='utf-8') as f:
                    if config_file.endswith('.json'):
                        external_config = json.load(f)
                    else:  # yaml
                        external_config = yaml.safe_load(f)
                
                # Merge configurations (external overrides default)
                def deep_merge(default, external):
                    for key, value in external.items():
                        if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                            deep_merge(default[key], value)
                        else:
                            default[key] = value
                
                deep_merge(CONFIG, external_config)
                logger.info(f"✅ Configuração carregada de {config_file}")
                return
            except Exception as e:
                logger.warning(f"⚠️ Erro ao carregar {config_file}: {e}")
    
    logger.debug("Usando configuração padrão")

# Carregar configuração no início
load_config()

BUILD = CONFIG['build']

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
    """Detecta IP do servidor local de forma universal e configurável"""
    import re
    
    def is_valid_ip(ip):
        """Valida se o IP é válido e não está na lista de exclusões"""
        if not ip or not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip):
            return False
        
        for pattern in CONFIG['network']['excluded_ip_patterns']:
            if re.match(pattern, ip):
                return False
        return True
    
    def extract_ip_from_text(text, patterns):
        """Extrai IP usando padrões configuráveis"""
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                ip = match if isinstance(match, str) else match[0]
                if is_valid_ip(ip):
                    return ip
        return None
    
    def try_network_commands(os_type):
        """Tenta comandos de rede específicos do OS"""
        commands = CONFIG['commands'].get(os_type, [])
        patterns = CONFIG['ip_patterns'].get(os_type, CONFIG['ip_patterns']['linux'])
        
        for cmd in commands:
            try:
                if os_type == 'windows':
                    result = subprocess.run(cmd, capture_output=True, text=True, 
                                          timeout=CONFIG['network']['timeout'])
                else:
                    # Para Linux/macOS, adicionar host de teste se necessário
                    full_cmd = cmd + [CONFIG['network']['test_hosts'][0]] if len(cmd) > 1 else cmd
                    result = subprocess.run(full_cmd, capture_output=True, text=True, 
                                          timeout=CONFIG['network']['timeout'])
                
                if result.returncode == 0:
                    ip = extract_ip_from_text(result.stdout, patterns)
                    if ip:
                        logger.debug(f"IP encontrado via {' '.join(cmd)}: {ip}")
                        return ip
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                logger.debug(f"Comando {cmd} falhou: {e}")
                continue
        return None
    
    def try_socket_method():
        """Método universal usando socket"""
        for host in CONFIG['network']['test_hosts']:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(CONFIG['network']['timeout'])
                s.connect((host, CONFIG['network']['test_port']))
                ip = s.getsockname()[0]
                s.close()
                if is_valid_ip(ip):
                    logger.debug(f"IP encontrado via socket ({host}): {ip}")
                    return ip
            except Exception as e:
                logger.debug(f"Socket para {host} falhou: {e}")
                continue
        return None
    
    # Tentar método específico do OS
    os_type = platform.system().lower()
    ip = try_network_commands(os_type)
    if ip:
        return ip
    
    # Fallback para método socket universal
    ip = try_socket_method()
    if ip:
        return ip
    
    # Fallback final
    return "localhost"
        
def wait_for_ssh_ready(timeout=None):
    """Aguarda SSH container estar pronto"""
    if timeout is None:
        timeout = CONFIG['network']['timeout'] * 3  # 30 segundos por padrão
    
    logger.info("🔑 Waiting for SSH server...")
    start = time.time()
    ssh_port = CONFIG['ssh']['port']
    
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('localhost', ssh_port))
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
    ssh_config = CONFIG['ssh']
    
    print("\n" + "=" * 90)
    print("🔧 SSH CONNECTION READY 🔧")
    print("=" * 90)
    print(f"🌐 Server IP    : {server_ip}")
    print(f"🔌 SSH Port     : {ssh_config['port']}")
    print(f"👤 User         : {ssh_config['user']}")
    print(f"🔐 Password     : {ssh_config['password']}")
    print(f"⏰ Started at   : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)
    print()
    print("📋 CONNECTION COMMAND:")
    print("─" * 90)
    print(f"ssh -L {ssh_config['local_port']}:{ssh_config['container_name']}:{ssh_config['local_port']} {ssh_config['user']}@{server_ip} -p {ssh_config['port']}")
    print("─" * 90)
    print()
    print("🌍 ACCESS URL:")
    print("─" * 90)
    print(f"http://localhost:{ssh_config['local_port']}/frontend")
    print("─" * 90)
    print()
    print("📝 NOTES:")
    print("• Multiple users can use the same command simultaneously")
    print("• Each user will have their own isolated session")
    print("• Keep this terminal open while using the application")
    print()
    print("🚀 Application is ready! Press Ctrl+C to stop.")
    print("=" * 90)

def wait_for_backend_ready(url=None, timeout=None):
    if url is None:
        url = f"http://localhost:{CONFIG['ssh']['local_port']}/docs"
    if timeout is None:
        timeout = CONFIG['network']['timeout'] * 6  # 60 segundos por padrão
    
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