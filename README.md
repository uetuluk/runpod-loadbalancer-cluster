# Tools for GPS Orientation SD Instance

## Requirements

* RunPod API key
* Cloudflare Token
* AWS Configure
* Direnv

## Steps

1. Setup the environment variables inside the .envrc file. You can use the .envrc.example as a template.

2. Configure runpodctl using API key.

```bash
runpodctl config --apiKey $RUNPOD_API_KEY
```

2. Create instances using that template.
3. Copy the SD model to the instance.