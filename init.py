import subprocess
import time
import signal
import psutil
import sys
import threading
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_command(command):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process

def run_command_with_output(command):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()
    logger.info(stdout)
    logger.error(stderr)
    return process.returncode

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
    # Caminho para o executável do Docker Desktop
    docker_desktop_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
    subprocess.Popen([docker_desktop_path], shell=True)
    # Espera um tempo para o Docker iniciar
    time.sleep(30)

def is_docker_desktop_running():
    for process in psutil.process_iter(['name']):
        if process.info['name'] == 'Docker Desktop.exe':
            return True
    return False

def update_progress_bar():
    while True:
        # Logic to update the progress bar
        time.sleep(1)

def main():

    if not is_docker_running():
        if not is_docker_desktop_running():
            start_docker()
            # Verifica novamente se o Docker está rodando após tentar iniciar
            if not is_docker_running():
                logger.error("Failed to start Docker. Please start Docker manually.")
                return

    try:
        # Build and start the Docker containers
        logger.info("Building Docker containers...")
        build_rc = run_command_with_output("docker-compose build")
        if build_rc != 0:
            logger.error("Docker build failed.")
            stop_containers()
            sys.exit(1)

        logger.info("Starting Docker containers...")
        up_process = run_command("docker-compose up -d")
        up_process.wait()

        # Run the printURL.sh script to get the ngrok URL
        logger.info("Fetching ngrok URL...")
        url_process = run_command("docker-compose run --rm ngrok-updater")
        url_process.wait()

        # Print the output of the URL process
        stdout, stderr = url_process.communicate()
        logger.info(stdout.decode())

        # Start a thread to update the progress bar
        progress_thread = threading.Thread(target=update_progress_bar)
        progress_thread.start()

        # Keep the script running
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