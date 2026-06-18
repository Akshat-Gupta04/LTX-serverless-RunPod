import runpod
from runpod.serverless.utils import rp_upload
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.parse
import binascii
import subprocess
import time
from PIL import Image

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_address = os.getenv('SERVER_ADDRESS', '127.0.0.1')
client_id = str(uuid.uuid4())

def to_nearest_multiple_of_16(value):
    """Adjust dimensions to the nearest multiple of 16 (minimum 16)"""
    try:
        numeric_value = float(value)
    except Exception:
        raise Exception(f"Dimension value is not a number: {value}")
    adjusted = int(round(numeric_value / 16.0) * 16)
    if adjusted < 16:
        adjusted = 16
    return adjusted

def ensure_default_image():
    """Ensure a default placeholder image exists at /example_image.png"""
    default_path = "/example_image.png"
    if not os.path.exists(default_path):
        try:
            img = Image.new('RGB', (512, 512), color='black')
            img.save(default_path)
            logger.info(f"✅ Created default dummy image at {default_path}")
        except Exception as e:
            logger.error(f"❌ Failed to create default dummy image: {e}")

def process_input(input_data, temp_dir, output_filename, input_type):
    """Process file inputs from path, URL, or Base64 encoding"""
    if input_type == "path":
        logger.info(f"📁 Path input: {input_data}")
        return input_data
    elif input_type == "url":
        logger.info(f"🌐 URL input: {input_data}")
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        return download_file_from_url(input_data, file_path)
    elif input_type == "base64":
        logger.info(f"🔢 Base64 input")
        return save_base64_to_file(input_data, temp_dir, output_filename)
    else:
        raise Exception(f"Unsupported input type: {input_type}")

def download_file_from_url(url, output_path):
    """Download a file from a URL using wget"""
    try:
        result = subprocess.run([
            'wget', '-O', output_path, '--no-verbose', url
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ Downloaded file from URL: {url} -> {output_path}")
            return output_path
        else:
            logger.error(f"❌ wget download failed: {result.stderr}")
            raise Exception(f"URL download failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("❌ Download timed out")
        raise Exception("Download timed out")
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
        raise Exception(f"Download error: {e}")

def save_base64_to_file(base64_data, temp_dir, output_filename):
    """Save decoded Base64 content to a file"""
    try:
        # Strip potential metadata prefixes (e.g., 'data:image/png;base64,')
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]
            
        decoded_data = base64.b64decode(base64_data)
        os.makedirs(temp_dir, exist_ok=True)
        
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        with open(file_path, 'wb') as f:
            f.write(decoded_data)
        
        logger.info(f"✅ Saved Base64 input to file: {file_path}")
        return file_path
    except (binascii.Error, ValueError) as e:
        logger.error(f"❌ Base64 decoding failed: {e}")
        raise Exception(f"Base64 decoding failed: {e}")

def queue_prompt(prompt):
    """Submit prompt payload to ComfyUI server"""
    url = f"http://{server_address}:8188/prompt"
    logger.info(f"Queueing prompt to: {url}")
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_history(prompt_id):
    """Fetch prompt execution history from ComfyUI"""
    url = f"http://{server_address}:8188/history/{prompt_id}"
    logger.info(f"Getting history from: {url}")
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())

def get_videos(ws, prompt):
    """Monitor execution state via websocket and extract base64-encoded output video"""
    prompt_id = queue_prompt(prompt)['prompt_id']
    output_videos = {}
    
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break
        else:
            continue

    history = get_history(prompt_id)[prompt_id]
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        videos_output = []
        
        # Check for 'gifs' (common VideoHelperSuite output key)
        if 'gifs' in node_output:
            for video in node_output['gifs']:
                filepath = video.get('fullpath')
                if not filepath or not os.path.exists(filepath):
                    filename = video.get('filename')
                    if filename:
                        filepath = os.path.join("/ComfyUI/output", video.get('subfolder', ''), filename)
                
                if filepath and os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        video_data = base64.b64encode(f.read()).decode('utf-8')
                    videos_output.append(video_data)
                    logger.info(f"✅ Loaded output video from: {filepath}")
        
        # Fallback check for 'images'
        elif 'images' in node_output:
            for img in node_output['images']:
                filename = img.get('filename')
                if filename:
                    filepath = os.path.join("/ComfyUI/output", img.get('subfolder', ''), filename)
                    if os.path.exists(filepath):
                        with open(filepath, 'rb') as f:
                            video_data = base64.b64encode(f.read()).decode('utf-8')
                        videos_output.append(video_data)
                        logger.info(f"✅ Loaded output media from: {filepath}")
                        
        output_videos[node_id] = videos_output

    return output_videos

def load_workflow(workflow_path):
    """Load JSON workflow config"""
    with open(workflow_path, 'r') as file:
        return json.load(file)

def handler(job):
    job_input = job.get("input", {})
    logger.info(f"Received job input: {job_input}")
    
    # Ensure default placeholder image is created
    ensure_default_image()
    
    task_id = f"task_{uuid.uuid4()}"

    # Resolve image inputs
    image_path = None
    if "image_path" in job_input:
        image_path = process_input(job_input["image_path"], task_id, "input_image.jpg", "path")
    elif "image_url" in job_input:
        image_path = process_input(job_input["image_url"], task_id, "input_image.jpg", "url")
    elif "image_base64" in job_input:
        image_path = process_input(job_input["image_base64"], task_id, "input_image.jpg", "base64")
    else:
        # Default fallback
        image_path = "/example_image.png"
        logger.info("Using default image path: /example_image.png")

    workflow_file = "/workflow_ltx23_api.json"
    logger.info(f"Loading workflow file: {workflow_file}")
    prompt = load_workflow(workflow_file)

    # Apply properties to workflow
    
    # Mode Toggle: Text-to-Video vs Image-to-Video
    text_to_video = job_input.get("text_to_video", False)
    prompt["320:302"]["inputs"]["value"] = text_to_video
    logger.info(f"Text-to-Video mode enabled: {text_to_video}")
    
    # Image input node
    prompt["269"]["inputs"]["image"] = image_path

    # Pos and Neg prompts
    prompt["320:319"]["inputs"]["value"] = job_input.get("prompt", "")
    if "negative_prompt" in job_input:
        prompt["320:313"]["inputs"]["text"] = job_input["negative_prompt"]

    # Resolution (adjusted to multiple of 16)
    width = to_nearest_multiple_of_16(job_input.get("width", 1280))
    height = to_nearest_multiple_of_16(job_input.get("height", 720))
    prompt["320:312"]["inputs"]["value"] = width
    prompt["320:299"]["inputs"]["value"] = height

    # Seeds (both sampler seeds)
    seed = job_input.get("seed", 42)
    prompt["320:277"]["inputs"]["noise_seed"] = seed
    prompt["320:276"]["inputs"]["noise_seed"] = seed

    # CFG scale
    cfg = job_input.get("cfg", 1.0)
    prompt["320:282"]["inputs"]["cfg"] = cfg
    prompt["320:314"]["inputs"]["cfg"] = cfg

    # Frame Rate and Duration / Length logic
    frame_rate = job_input.get("frame_rate", 25)
    if "length" in job_input:
        # Calculate duration based on frame rate (length = duration * frame_rate + 1)
        # Therefore duration = (length - 1) / frame_rate
        duration = max(1, int((job_input["length"] - 1) / frame_rate))
    else:
        duration = job_input.get("duration", 5)
        
    prompt["320:300"]["inputs"]["value"] = frame_rate
    prompt["320:301"]["inputs"]["value"] = duration
    logger.info(f"Configuration: Resolution={width}x{height}, FrameRate={frame_rate}, Duration={duration}s, Seed={seed}, CFG={cfg}")

    # Override Distilled LoRA details if specified
    lora_name = job_input.get("lora_name", "ltx-2.3-22b-distilled-lora-384.safetensors")
    lora_weight = job_input.get("lora_weight", 0.5)
    prompt["320:285"]["inputs"]["lora_name"] = lora_name
    prompt["320:285"]["inputs"]["strength_model"] = lora_weight
    logger.info(f"LoRA: {lora_name} (weight={lora_weight})")

    # Connect to WebSocket
    ws_url = f"ws://{server_address}:8188/ws?clientId={client_id}"
    logger.info(f"Connecting to WebSocket: {ws_url}")
    
    # Confirm HTTP readiness
    http_url = f"http://{server_address}:8188/"
    max_http_attempts = 180
    for http_attempt in range(max_http_attempts):
        try:
            urllib.request.urlopen(http_url, timeout=5)
            logger.info(f"HTTP Connection verified (attempt {http_attempt+1})")
            break
        except Exception as e:
            logger.warning(f"HTTP Connection failed (attempt {http_attempt+1}/{max_http_attempts}): {e}")
            if http_attempt == max_http_attempts - 1:
                raise Exception("Failed to reach ComfyUI server.")
            time.sleep(1)
    
    ws = websocket.WebSocket()
    max_attempts = 36
    for attempt in range(max_attempts):
        try:
            ws.connect(ws_url)
            logger.info(f"WebSocket Connected successfully (attempt {attempt+1})")
            break
        except Exception as e:
            logger.warning(f"WebSocket Connection failed (attempt {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                raise Exception("WebSocket connection timed out.")
            time.sleep(5)

    videos = get_videos(ws, prompt)
    ws.close()

    # Find and return the generated video
    for node_id in videos:
        if videos[node_id]:
            return {"video": videos[node_id][0]}
    
    return {"error": "Generated video could not be found."}

if __name__ == '__main__':
    runpod.serverless.start({"handler": handler})
