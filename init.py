import subprocess
import time
import signal
import psutil
import sys
import threading
import logging
import yaml
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def load_ngrok_token():
    with open('config/ngrok.yml', 'r') as file:
        config = yaml.safe_load(file)
    return config['ngrok']['auth_token']

def run_command(command):
    logger.debug(f"Running command: {command}")
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process

def run_command_with_output(command):
    logger.debug(f"Running command with output: {command}")
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    for line in process.stderr:
        sys.stderr.write(line)
        sys.stderr.flush()
    process.wait()
    return process.returncode

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
    except subprocess.CalledProcessError:
        return False

def start_docker():
    logger.info("Starting Docker Desktop...")
    docker_desktop_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
    subprocess.Popen([docker_desktop_path], shell=True)
    time.sleep(30)

def is_docker_desktop_running():
    for process in psutil.process_iter(['name']):
        if process.info['name'] == 'Docker Desktop.exe':
            return True
    return False

def update_progress_bar():
    while True:
        time.sleep(1)

def fetch_ngrok_url():
    try:
        response = requests.get('http://localhost:4040/api/tunnels')
        tunnels = response.json()['tunnels']
        for tunnel in tunnels:
            if tunnel['proto'] == 'https':
                return tunnel['public_url']
    except Exception as e:
        logger.error(f"Failed to fetch ngrok URL: {e}")
    return None

def main():
    if not is_docker_running():
        if not is_docker_desktop_running():
            start_docker()
            if not is_docker_running():
                logger.error("Failed to start Docker. Please start Docker manually.")
                return

    try:
        logger.info("Building Docker containers...")
        build_rc = run_command_dynamic_output("docker-compose build")
        if build_rc != 0:
            logger.error("Docker build failed.")
            stop_containers()
            sys.exit(1)

        logger.info("Starting Docker containers...")
        up_process = run_command("docker-compose up -d")
        up_process.wait()

        logger.info("Fetching ngrok URL...")
        time.sleep(10)  # Wait for ngrok to initialize
        ngrok_url = fetch_ngrok_url()
        if ngrok_url:
            logger.info(f"\nNgrok URL: {ngrok_url}/frontend\n")
        else:
            logger.error("Failed to retrieve ngrok URL.")

        progress_thread = threading.Thread(target=update_progress_bar)
        progress_thread.start()

        logger.info("Application is running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        stop_containers()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    main()