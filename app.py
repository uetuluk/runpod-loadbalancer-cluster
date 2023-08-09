import re
import subprocess
import sys
import requests
import time
import boto3
import os
import argparse

# env constants
# runpod
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")
RUNPOD_CREATION_RETRIES = int(os.environ.get("RUNPOD_CREATION_RETRIES", "3"))
RUNPOD_GPU_TYPE = os.environ.get("RUNPOD_GPU_TYPE")
RUNPOD_IMAGE_NAME = os.environ.get("RUNPOD_IMAGE_NAME")
RUNPOD_POD_NAME = os.environ.get("RUNPOD_POD_NAME")
RUNPOD_POD_COUNT = int(os.environ.get("RUNPOD_POD_COUNT"))
RUNPOD_POD_START_RETRIES = int(os.environ.get("RUNPOD_POD_START_RETRIES", "30"))
RUNPOD_POD_START_RETRY_DELAY = int(os.environ.get("RUNPOD_POD_START_RETRY_DELAY", "60"))

# caddy
CADDY_DOMAIN = os.environ.get("CADDY_DOMAIN")
CLOUDFLARE_EMAIL = os.environ.get("CLOUDFLARE_EMAIL")

# lightsail
LIGHTSAIL_INSTANCE_NAME = os.environ.get("LIGHTSAIL_INSTANCE_NAME")
LIGHTSAIL_INSTANCE_REGION = os.environ.get("LIGHTSAIL_INSTANCE_REGION")
LIGHTSAIL_INSTANCE_BUNDLE_ID = os.environ.get("LIGHTSAIL_INSTANCE_BUNDLE_ID")

# cloudflare
CLOUDFLARE_API_KEY = os.environ.get("CLOUDFLARE_API_KEY")
CLOUDFLARE_ZONE_ID = os.environ.get("CLOUDFLARE_ZONE_ID")

# program constants
RUNPOD_SD_PORT = 3000
RUNPOD_CONTAINER_DISK_SIZE = 10
RUNPOD_VOLUME_PATH = "/workspace"
RUNPOD_VOLUME_SIZE = 75

def check_env_vars():
    """
    Checks if the required environment variables are set.
    """
    print("Checking environment variables...")

    env_vars = [
        "RUNPOD_API_KEY",
        "RUNPOD_GPU_TYPE",
        "RUNPOD_IMAGE_NAME",
        "RUNPOD_POD_NAME",
        "RUNPOD_POD_COUNT",
        "CADDY_DOMAIN",
        "CLOUDFLARE_EMAIL",
        "LIGHTSAIL_INSTANCE_NAME",
        "LIGHTSAIL_INSTANCE_REGION",
        "LIGHTSAIL_INSTANCE_BUNDLE_ID",
        "CLOUDFLARE_API_KEY",
        "CLOUDFLARE_ZONE_ID"
    ]

    for var in env_vars:
        if var not in os.environ:
            print(f"Error: The {var} environment variable is not set!")
            sys.exit(1)

    print("All required environment variables are set.")

    # write the env vars to a file
    with open("env_vars.txt", "w") as file:
        file.write(f"RUNPOD_POD_NAME={RUNPOD_POD_NAME}\n")
        file.write(f"RUNPOD_POD_COUNT={RUNPOD_POD_COUNT}\n")
        file.write(f"CADDY_DOMAIN={CADDY_DOMAIN}\n")
        file.write(f"LIGHTSAIL_INSTANCE_NAME={LIGHTSAIL_INSTANCE_NAME}\n")
    
    print("Wrote environment variables to env_vars.txt.")
    
def create_runpod_config():

    cmd = ['runpodctl', 'config', f'--apiKey={RUNPOD_API_KEY}']

    try:
        subprocess.run(cmd, check=True)
        print("Created runpod config.")
    except subprocess.CalledProcessError as e:
        print(f"Error creating runpod config: {e}")
        sys.exit(1)

def run_command_and_extract_ids():
    """
    Runs the runpodctl command to create pods and extracts the pod IDs from the output.

    Returns:
    - list: List of pod IDs.
    """
    
    # Command to run
    cmd = [
        'runpodctl', 'create', 'pods', 
        '--communityCloud',
        '--containerDiskSize', f'{RUNPOD_CONTAINER_DISK_SIZE}',
        '--gpuType', RUNPOD_GPU_TYPE,
        '--imageName', RUNPOD_IMAGE_NAME,
        '--name', RUNPOD_POD_NAME,
        '--podCount', f'{RUNPOD_POD_COUNT}',
        '--ports', f'{RUNPOD_SD_PORT}/http',
        '--volumePath', RUNPOD_VOLUME_PATH,
        '--volumeSize', f'{RUNPOD_VOLUME_SIZE}'
    ]

    for attempt in range(RUNPOD_CREATION_RETRIES):
        # Execute the command and capture the output
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if process.returncode == 0:
            # Regex pattern to extract pod IDs
            pattern = r'pod "([a-zA-Z0-9]+)"'
            pod_ids = re.findall(pattern, process.stdout)
            return pod_ids
        else:
            print(f"Attempt {attempt + 1} failed. Error: {process.stderr}")
            if attempt < RUNPOD_CREATION_RETRIES - 1:  # Don't sleep after the last attempt
                print("Retrying...")
        return []

def ping_pod_until_ready(pod_id):
    """
    Pings the provided pod_id URL until a 200 response is received.

    Args:
    - pod_id (str): ID of the pod.

    Returns:
    - bool: True if 200 response is received, False otherwise.
    """
    url = f"http://{pod_id}-{RUNPOD_SD_PORT}.proxy.runpod.net"

    print("Waiting for pods to become ready...")
    for attempt in range(RUNPOD_POD_START_RETRIES):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print(f"Pod {pod_id} is ready!")
                return True
        except requests.ConnectionError:
            pass  # Handle connection errors gracefully

        if attempt < RUNPOD_POD_START_RETRIES - 1:  # Don't sleep after the last attempt
            time.sleep(RUNPOD_POD_START_RETRY_DELAY)
    return False

def get_domain_from_pod_id(pod_id):
    """
    Extracts the domain name from the provided pod ID.

    Args:
    - pod_id (str): ID of the pod.

    Returns:
    - str: Domain name.
    """
    return f"{pod_id}-{RUNPOD_SD_PORT}.proxy.runpod.net"

def generate_caddyfile(domains):
    """
    Generates a Caddyfile with the provided domains.

    Args:
    - domains (list): List of domains to add to the Caddyfile.

    Returns:
    - str: Caddyfile content.
    """
    config_domain = f"https://{CADDY_DOMAIN}" + """ {
    """
    tls_config = f"tls {CLOUDFLARE_EMAIL}" + """ {
        dns cloudflare """ + f"{CLOUDFLARE_API_KEY}" + """
    }"""
    base_config = """
    log
    reverse_proxy * {
        header_up Host {http.reverse_proxy.upstream.hostport}
        header_down X-Endpoint {http.reverse_proxy.upstream.hostport}
        lb_policy ip_hash
        lb_try_duration 30s
        lb_try_interval 250ms
        health_uri /
        to """
    backend_servers = " ".join([f"https://{domain}" for domain in domains])
    closing_config = """
    }
}
"""
    return config_domain + tls_config + base_config + backend_servers + closing_config

def create_lightsail_instance(caddyfile_content):
    """
    Creates a Lightsail instance with the provided Caddyfile content.

    Args:
    - caddyfile_content (str): Content of the Caddyfile.

    Returns:
    - str: Public IP address of the Lightsail instance.
    """
    
    # Initialize Lightsail client
    client = boto3.client('lightsail')

    launch_script = f"""sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
wget "https://caddyserver.com/api/download?os=linux&arch=amd64&p=github.com%2Fcaddy-dns%2Fcloudflare&idempotency=72161063061013" -O /tmp/caddy
sudo chmod +x /tmp/caddy
sudo dpkg-divert --divert /usr/bin/caddy.default --rename /usr/bin/caddy
sudo mv /tmp/caddy /usr/bin/caddy.custom
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.default 10
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.custom 50
echo '{caddyfile_content}' > /etc/caddy/Caddyfile
sudo systemctl restart caddy
    """

    # Create a Lightsail instance
    response = client.create_instances(
        instanceNames=[LIGHTSAIL_INSTANCE_NAME],
        availabilityZone=LIGHTSAIL_INSTANCE_REGION,
        blueprintId='ubuntu_22_04',
        bundleId=LIGHTSAIL_INSTANCE_BUNDLE_ID,
        userData=launch_script,
        ipAddressType="ipv4"
    )

    # The response contains information about the instances that were created.

    while True:
        response = client.get_instance(instanceName=LIGHTSAIL_INSTANCE_NAME)
        if response['instance']['state']['name'] == 'running':
            break
        print("Waiting for instance to be ready...")
        time.sleep(10)
    
    # add port 443
    port_info = {
        'fromPort': 443,
        'toPort': 443,
        'protocol': 'tcp',
        'cidrs': ['0.0.0.0/0'],  # This CIDR denotes everyone
    }

    # Update the instance port states
    client.open_instance_public_ports(
        instanceName=LIGHTSAIL_INSTANCE_NAME,
        portInfo=port_info
    )

    return response['instance']['publicIpAddress']

def create_dns_record(ip):
    """
    Creates a DNS record for the provided IP address.

    Args:
    - ip (str): IP address to create the DNS record for.

    Returns: 
    - None
    """
    
    url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records"

    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "type": "A",
        "name": CADDY_DOMAIN,
        "content": ip,
        "ttl": 120,  # 2 minutes, you can change this value
        "proxied": True  # Determines whether to use Cloudflare proxy, adjust as needed
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        print(f"DNS Record for {CADDY_DOMAIN} pointing to {ip} created successfully!")
    else:
        print(f"Error: {response.json()}")

if __name__ == '__main__':
    
    check_env_vars()

    # parse arguements
    parser = argparse.ArgumentParser(description="Runpod cluster setup with loadbalaner.")
    parser.add_argument("--skip-runpod", action="store_false", help="Skip runpod creation.")
    parser.add_argument("--skip-loadbalancer", action="store_false", help="Skip loadbalancer creation.")
    parser.add_argument("--skip-dns", action="store_false", help="Skip DNS record creation.")
    
    args = parser.parse_args()

    # flags
    CREATE_RUNPOD_PODS = args.skip_runpod
    CREATE_LOADBALANCER = args.skip_loadbalancer
    CREATE_DNS_RECORD = args.skip_dns

    if CREATE_RUNPOD_PODS:
        create_runpod_config()

        created_ids = run_command_and_extract_ids()

        if created_ids:
            print("Created Pod IDs:", created_ids)
        else:
            print(f"Command failed after ${RUNPOD_CREATION_RETRIES} retries.")
            sys.exit(1)
        
        working_ids = []

        # check if the pods are running
        for pod_id in created_ids:
            if ping_pod_until_ready(pod_id):
                working_ids.append(pod_id)
            else:
                print(f"Pod {pod_id} did not become ready after multiple pings.")

        print("Working Pod IDs:", working_ids)

        # Create a list of domains from the working IDs
        domains = [get_domain_from_pod_id(pod_id) for pod_id in working_ids]
        print("Working Domains:", domains)

        # Generate the Caddyfile
        if domains:
            caddyfile_content = generate_caddyfile(domains)

            # Write the Caddyfile to disk
            print("Writing Caddyfile to disk...")
            with open("Caddyfile", "w") as file:
                file.write(caddyfile_content)
    
    # # create balancer
    # # create a lightsail instance
    
    if CREATE_LOADBALANCER:
        if not CREATE_RUNPOD_PODS:
            try:
                caddyfile_content = open("Caddyfile", "r").read()
            except FileNotFoundError:
                print("Error: Runpod step should be run before load balancer creation.")
                sys.exit(1)

        lightsail_ip = create_lightsail_instance(caddyfile_content)

        print("Created Lightsail instance with IP:", lightsail_ip)

        # write the lightsail ip to a file
        with open("lightsail_ip.txt", "w") as file:
            file.write(lightsail_ip)

    # create dns record

    if CREATE_DNS_RECORD:
        if not CREATE_LOADBALANCER:
            try:
                lightsail_ip = open("lightsail_ip.txt", "r").read()
            except FileNotFoundError:
                print("Error: Load balancer step should be run before DNS record creation.")
                sys.exit(1)

        print(f"Creating A DNS record for {CADDY_DOMAIN} pointing to {lightsail_ip}...")
        create_dns_record(lightsail_ip)

    print("All steps are completed.")

    print(f"You can access the load balancer at https://{CADDY_DOMAIN}")