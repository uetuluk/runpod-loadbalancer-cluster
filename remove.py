import boto3
import requests
import os
import subprocess
import sys
import argparse

def setup_environment():
    """
    Sets up the environment variables needed to run the script.

    The environment variables are stored in a file called env_vars.txt.
    """
    
    print("Setting up environment variables...")
    with open("env_vars.txt", "r") as file:
        for line in file:
            key, value = line.split("=")
            os.environ[key] = value.strip()
    print("Done.")

def check_env_vars():
    """
    Checks that all the environment variables needed to run the script are set.
    """
    
    print("Checking environment variables...")
    env_vars = [
        "CLOUDFLARE_API_KEY",
        "CLOUDFLARE_ZONE_ID",
        "CADDY_DOMAIN",
        "RUNPOD_POD_NAME",
        "RUNPOD_POD_COUNT",
        "LIGHTSAIL_INSTANCE_NAME"
    ]
    
    for var in env_vars:
        if var not in os.environ:
            print(f"Error: The {var} environment variable is not set!")
            sys.exit(1)

    print("All required environment variables are set.")

def delete_runpod_containers():
    """
    Deletes the runpod containers.
    """
    
    try:
        # Delete the runpod containers
        cmd = ['runpodctl', 'remove', 'pods', RUNPOD_POD_NAME, "--podCount", f"{RUNPOD_POD_COUNT}"]
        subprocess.run(cmd, check=True)
        print(f"Deleted runpod containers with name '{RUNPOD_POD_NAME}'.")
    except subprocess.CalledProcessError as e:
        print(f"Error deleting runpod containers: {e}")

def delete_runpod_config():
    """
    Deletes the runpod config file.
    """
    
    config_path = os.path.join(os.environ['HOME'], ".runpod.yaml")
    if os.path.exists(config_path):
        os.remove(config_path)
        print(f"Deleted {config_path}.")
    else:
        print(f"Error: {config_path} does not exist!")

def delete_lightsail_instance():
    """
    Deletes the Lightsail instance.
    """
    
    client = boto3.client('lightsail')
    
    try:
        # Delete the Lightsail instance
        client.delete_instance(instanceName=LIGHTSAIL_INSTANCE_NAME)
        print(f"Deleted Lightsail instance named '{LIGHTSAIL_INSTANCE_NAME}'.")
    except Exception as e:
        print(f"Error deleting Lightsail instance: {e}")

def delete_dns_record():
    """
    Deletes the DNS record for the Caddy domain.
    """
    
    url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records"
    
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # First, get the record ID for the given domain
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get('result', [])
        record_id = next((record['id'] for record in records if record['name'] == CADDY_DOMAIN), None)
        
        if not record_id:
            print(f"Error: Could not find DNS record for domain {CADDY_DOMAIN}")
            sys.exit(1)
        
        # Delete the DNS record
        delete_url = f"{url}/{record_id}"
        delete_response = requests.delete(delete_url, headers=headers)
        if delete_response.status_code == 200:
            print(f"Deleted DNS Record for {CADDY_DOMAIN}.")
        else:
            print(f"Error deleting DNS record for {CADDY_DOMAIN}: {delete_response.json()}")
    else:
        print(f"Error fetching DNS records: {response.json()}")

if __name__ == '__main__':

    setup_environment()

    check_env_vars()

    # parse arguements
    parser = argparse.ArgumentParser(description="Cluster cleanup.")
    parser.add_argument("--skip-runpod", action="store_false", help="Skip runpod deletion.")
    parser.add_argument("--skip-loadbalancer", action="store_false", help="Skip loadbalancer deletion.")
    parser.add_argument("--skip-dns", action="store_false", help="Skip DNS record deletion.")
    
    args = parser.parse_args()

    # flags
    DELETE_RUNPOD_PODS = args.skip_runpod
    DELETE_LOADBALANCER = args.skip_loadbalancer
    DELETE_DNS_RECORD = args.skip_dns
    
    if DELETE_RUNPOD_PODS:
        print("Deleting runpod pods...")
        
        delete_runpod_containers()
    
        delete_runpod_config()
    
    if DELETE_LOADBALANCER:
        print("Deleting loadbalancer...")
        
        delete_lightsail_instance()
    
    if DELETE_DNS_RECORD:
        print("Deleting DNS record...")
    
        delete_dns_record()

    print("All steps are completed.")