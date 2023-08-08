import re
import subprocess
import sys
import requests
import time
import boto3
import os

# env constants
# runpod
RUNPOD_CREATION_RETRIES = os.environ.get("RUNPOD_CREATION_RETRIES", 3)
RUNPOD_GPU_TYPE = os.environ.get("RUNPOD_GPU_TYPE")
RUNPOD_IMAGE_NAME = os.environ.get("RUNPOD_IMAGE_NAME")
RUNPOD_POD_NAME = os.environ.get("RUNPOD_POD_NAME")
RUNPOD_POD_COUNT = os.environ.get("RUNPOD_POD_COUNT")
RUNPOD_POD_START_RETRIES = os.environ.get("RUNPOD_POD_START_RETRIES", 30)
RUNPOD_POD_START_RETRY_DELAY = os.environ.get("RUNPOD_POD_START_RETRY_DELAY", 60)

# caddy
CADDY_DOMAIN = os.environ.get("CADDY_DOMAIN")

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
        "RUNPOD_GPU_TYPE",
        "RUNPOD_IMAGE_NAME",
        "RUNPOD_POD_NAME",
        "RUNPOD_POD_COUNT",
        "CADDY_DOMAIN",
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
        file.write(f"RUNPOD_CREATION_RETRIES={RUNPOD_CREATION_RETRIES}\n")
        file.write(f"RUNPOD_GPU_TYPE={RUNPOD_GPU_TYPE}\n")
        file.write(f"RUNPOD_IMAGE_NAME={RUNPOD_IMAGE_NAME}\n")
        file.write(f"RUNPOD_POD_NAME={RUNPOD_POD_NAME}\n")
        file.write(f"RUNPOD_POD_COUNT={RUNPOD_POD_COUNT}\n")
        file.write(f"RUNPOD_POD_START_RETRIES={RUNPOD_POD_START_RETRIES}\n")
        file.write(f"RUNPOD_POD_START_RETRY_DELAY={RUNPOD_POD_START_RETRY_DELAY}\n")
        file.write(f"CADDY_DOMAIN={CADDY_DOMAIN}\n")
        file.write(f"LIGHTSAIL_INSTANCE_NAME={LIGHTSAIL_INSTANCE_NAME}\n")
        file.write(f"LIGHTSAIL_INSTANCE_REGION={LIGHTSAIL_INSTANCE_REGION}\n")
        file.write(f"LIGHTSAIL_INSTANCE_BUNDLE_ID={LIGHTSAIL_INSTANCE_BUNDLE_ID}\n")
        file.write(f"CLOUDFLARE_API_KEY={CLOUDFLARE_API_KEY}\n")
        file.write(f"CLOUDFLARE_ZONE_ID={CLOUDFLARE_ZONE_ID}\n")
    
    print("Wrote environment variables to env_vars.txt.")
    
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
    config_domain = f"https://{CADDY_DOMAIN}"
    base_config = """ {
    log
    reverse_proxy / {
        header_up Host {http.reverse_proxy.upstream.hostport}
        lb_policy header X-Forwarded-For
        lb_try_duration 30s
        lb_try_interval 250ms
"""
    backend_servers = "\n".join([f"        to https://{domain}" for domain in domains])
    closing_config = """
    }
}
"""
    return config_domain + base_config + backend_servers + closing_config

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
echo '{caddyfile_content}' > /etc/caddy/Caddyfile
sudo systemctl reload caddy
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

    lightsail_ip = create_lightsail_instance(caddyfile_content)

    print("Created Lightsail instance with IP:", lightsail_ip)

    # create dns record
    print(f"Creating A DNS record for {CADDY_DOMAIN} pointing to {lightsail_ip}...")
    create_dns_record(lightsail_ip)

    print("All steps are completed.")

    print(f"You can access the load balancer at {CADDY_DOMAIN}")