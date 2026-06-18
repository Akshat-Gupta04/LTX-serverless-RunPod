# LTX 2.3 RunPod Serverless API

This directory contains the files required to build and deploy a **RunPod Serverless Worker** for generating videos using the **LTX 2.3** unified model. It integrates with ComfyUI under the hood and exposes a clean, single-endpoint REST API for video generation.

---

## ✨ Features

- **Unified LTX 2.3 Pipeline**: Support for high-quality audio-video generation.
- **Image-to-Video (I2V)** & **Text-to-Video (T2V)**: Easily toggle between modes using a simple boolean flag (`text_to_video`).
- **Quantized Setup**: Runs the memory-efficient FP8 base model (`ltx-2.3-22b-dev-fp8.safetensors`) alongside the Gemma-3 12B IT text encoder (`gemma_3_12B_it_fp4_mixed.safetensors`), fitting on standard GPUs.
- **Fast Generation**: Utilizes the official distilled LoRA (`ltx-2.3-22b-distilled-lora-384.safetensors`) with customizable weight strengths.
- **High-speed base64 IO**: Send images and retrieve generated MP4 videos directly via Base64.
- **Flexibility**: Configurable prompt, negative prompt, duration, resolution, frame rate, seed, and CFG.

---

## 🛠️ Deploy to RunPod

### 1. Build and Push the Docker Image
Build the Docker image locally or via a cloud builder, and push it to your container registry (Docker Hub, GitHub Packages, etc.):

```bash
docker build -t yourregistry/ltx-2.3-serverless:latest .
docker push yourregistry/ltx-2.3-serverless:latest
```

### 2. Configure RunPod Endpoint
1. Go to the **RunPod Dashboard** and navigate to **Serverless -> Endpoints**.
2. Click **New Endpoint** and specify:
   - **Endpoint Name**: `ltx-2.3-generation`
   - **Container Image**: `yourregistry/ltx-2.3-serverless:latest`
   - **GPU Type**: We recommend GPUs with at least **24GB VRAM** (e.g., A10G, A30, A40, A100, RTX 4090/6000 Ada).
   - **Active Limits**: Adjust according to your traffic.
3. Save the endpoint and copy your **Endpoint ID** and **API Key**.

---

## 🔧 API Reference

### Input Payload
Send a JSON payload matching the following format:

| Parameter | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `prompt` | `string` | **Yes** | - | Multiline text description of the desired video. |
| `text_to_video` | `boolean` | No | `false` | Set to `true` to run in Text-to-Video mode. Bypasses image input. |
| `image_path` | `string` | No | - | Absolute local file path of the input image on a connected volume. |
| `image_url` | `string` | No | - | Public URL of the input image to download. |
| `image_base64` | `string` | No | - | Base64 encoded string of the input image. |
| `negative_prompt` | `string` | No | *Standard* | Negative prompts to exclude bad aesthetics. |
| `width` | `integer` | No | `1280` | Output width (adjusted to the nearest multiple of 16). |
| `height` | `integer` | No | `720` | Output height (adjusted to the nearest multiple of 16). |
| `duration` | `integer` | No | `5` | Length of video in seconds. |
| `frame_rate` | `integer` | No | `25` | Frames per second. |
| `seed` | `integer` | No | `42` | Random noise seed. |
| `cfg` | `float` | No | `1.0` | Guidance scale. |
| `lora_name` | `string` | No | `ltx-2.3-22b-distilled-lora-384.safetensors` | Overrides distilled LoRA filename. |
| `lora_weight` | `float` | No | `0.5` | Strength of the distilled LoRA. |

---

### Request Payload Examples

#### 1. Image-to-Video (I2V) with Base64 Image
```json
{
  "input": {
    "prompt": "An Egyptian queen walking forward, desert background, high cinematic realism",
    "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "width": 1280,
    "height": 720,
    "duration": 5,
    "seed": 42
  }
}
```

#### 2. Text-to-Video (T2V) Mode
```json
{
  "input": {
    "prompt": "Cinematic shot of a fast-moving stream inside an enchanted forest, glowing flora, volumetric lighting",
    "text_to_video": true,
    "width": 1280,
    "height": 720,
    "duration": 4,
    "seed": 1024
  }
}
```

---

## 🐍 Python Client Usage

Integrate with your endpoint programmatically using `generate_video_client.py`:

```python
from generate_video_client import GenerateVideoClient

# Initialize Client
client = GenerateVideoClient(
    runpod_endpoint_id="your-endpoint-id",
    runpod_api_key="your-api-key"
)

# 1. Run Single Image-to-Video Generation
result = client.generate_video(
    prompt="A magical waterfall inside a cave, fantasy art, photorealistic",
    image_path="./cave_entrance.png",
    width=1280,
    height=720,
    duration=5
)

if result.get("status") == "COMPLETED":
    client.save_video_result(result, "./output_magic_cave.mp4")
else:
    print(f"Error: {result.get('error')}")
```

---

## 📁 Using Network Volumes

To run your serverless worker efficiently, you can connect a **RunPod Network Volume** to store large checkpoints, LoRAs, and text encoders. This prevents you from having to build a massive Docker image containing all weight files and speeds up endpoint boot times.

### 1. Create a Network Volume in RunPod
1. Navigate to the **Storage** tab in your RunPod Dashboard and click **Create Volume**.
2. **Important**: Select the **exact same GPU region** (e.g., `US-East-1`) where you plan to deploy your Serverless Endpoint.
3. Configure the size (50 GB+ recommended) and name the volume.

### 2. Upload Models to the Volume
1. Spin up a standard **RunPod GPU Pod** (workspace container) in the same region.
2. In the Pod configuration settings, attach the **Network Volume** you created.
3. Once running, open the Pod terminal or file explorer, navigate to the mounted `/runpod-volume` directory, and create these folders:
   ```bash
   mkdir -p /runpod-volume/checkpoints
   mkdir -p /runpod-volume/loras
   mkdir -p /runpod-volume/text_encoders
   ```
4. Upload your model weights directly into their respective folders.
5. Once complete, terminate the pod to detach the volume.

### 3. Attach Volume to the Serverless Endpoint
1. Go to your **Serverless Endpoint** settings.
2. Under the **Network Volume** setting, select your volume.
3. Save the endpoint. The volume will automatically mount at `/runpod-volume` inside the container when a worker starts.

### 4. How the Files are Referenced
Our configuration automatically maps the network volume folders:
- **LoRA Files**: Store in `/runpod-volume/loras/`. Reference in the API using only the filename (e.g., `"my-custom-lora.safetensors"`).
- **Checkpoints**: Store in `/runpod-volume/checkpoints/`. Reference in the API using only the filename (e.g., `"ltx-2.3-22b-dev-fp8.safetensors"`).
- **Text Encoders**: Store in `/runpod-volume/text_encoders/`. Reference by filename (e.g., `"gemma_3_12B_it_fp4_mixed.safetensors"`).

