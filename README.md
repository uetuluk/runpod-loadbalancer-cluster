# RunPod Cluster

## Requirements

### Software
* direnv
* python
* runpodctl

### Resources
* RunPod API key
* Cloudflare Token
* AWS API key with access to Lightsail

## Steps

1. Setup the environment variables inside the .envrc file. You can use the .envrc.example as a template.

2. Run `direnv allow .` to load the environment variables.

3. Run `python app.py` to create the cluster. You can also refer to Makefile.
   1. The RunPod cluster will be created according to the variables in the .envrc file and a Caddyfile will be created.
   2. The Caddy loadbalancer will be created using the Caddyfile.
   3. The DNS records will be created to point to the loadbalancer. 

Done.

## Notes

1. You can remove the cluster by running `python remove.py`.

2. If you want to skip steps of the cluster creation, you can use the `--skip-runpod`, `--skip-loadbalancer`, `--skip-dns` to skip the respective steps. You can also use the same flags in the remove.py script.