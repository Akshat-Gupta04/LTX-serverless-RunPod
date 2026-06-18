#!/usr/bin/env python3
"""
Generate Video API client for LTX 2.3 RunPod Serverless.
Allows generating video from image (I2V) or text (T2V) using base64 encoding, custom settings, and batch processing.
"""

import os
import requests
import json
import time
import base64
from typing import Optional, Dict, Any, List, Union
import logging

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GenerateVideoClient:
    def __init__(
        self,
        runpod_endpoint_id: str,
        runpod_api_key: str
    ):
        """
        Initialize LTX 2.3 Generate Video client
        
        Args:
            runpod_endpoint_id: RunPod serverless endpoint ID
            runpod_api_key: RunPod API key
        """
        self.runpod_endpoint_id = runpod_endpoint_id
        self.runpod_api_key = runpod_api_key
        self.runpod_api_endpoint = f"https://api.runpod.ai/v2/{runpod_endpoint_id}/run"
        self.status_url = f"https://api.runpod.ai/v2/{runpod_endpoint_id}/status"
        
        # Initialize HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {runpod_api_key}',
            'Content-Type': 'application/json'
        })
        
        logger.info(f"GenerateVideoClient initialized for LTX 2.3 - Endpoint: {runpod_endpoint_id}")
    
    def encode_file_to_base64(self, file_path: str) -> Optional[str]:
        """
        Encode image file to base64 string
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"File does not exist: {file_path}")
                return None
            
            with open(file_path, 'rb') as f:
                file_data = f.read()
                base64_data = base64.b64encode(file_data).decode('utf-8')
            
            logger.info(f"✅ Image base64 encoding completed: {file_path}")
            return base64_data
            
        except Exception as e:
            logger.error(f"❌ Image base64 encoding failed: {e}")
            return None
    
    def submit_job(self, input_data: Dict[str, Any]) -> Optional[str]:
        """
        Submit a serverless job to RunPod
        """
        payload = {"input": input_data}
        
        try:
            logger.info(f"Submitting LTX 2.3 job to RunPod: {self.runpod_api_endpoint}")
            # Log payload without the raw base64 data to keep output clean
            log_payload = input_data.copy()
            if "image_base64" in log_payload:
                log_payload["image_base64"] = "<base64_data_truncated>"
                
            logger.info(f"Input payload parameters: {json.dumps(log_payload, indent=2, ensure_ascii=False)}")
            
            response = self.session.post(self.runpod_api_endpoint, json=payload, timeout=30)
            response.raise_for_status()
            
            response_data = response.json()
            job_id = response_data.get('id')
            
            if job_id:
                logger.info(f"✅ Job submission successful! Job ID: {job_id}")
                return job_id
            else:
                logger.error(f"❌ Failed to receive Job ID: {response_data}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Job submission failed: {e}")
            return None
    
    def wait_for_completion(self, job_id: str, check_interval: int = 10, max_wait_time: int = 1800) -> Dict[str, Any]:
        """
        Wait for RunPod job to complete, checking status periodically
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                logger.info(f"⏱️ Checking job status... (Job ID: {job_id})")
                
                response = self.session.get(f"{self.status_url}/{job_id}", timeout=30)
                response.raise_for_status()
                
                status_data = response.json()
                status = status_data.get('status')
                
                if status == 'COMPLETED':
                    logger.info("✅ Job completed!")
                    return {
                        'status': 'COMPLETED',
                        'output': status_data.get('output'),
                        'job_id': job_id
                    }
                elif status == 'FAILED':
                    logger.error("❌ Job failed.")
                    return {
                        'status': 'FAILED',
                        'error': status_data.get('error', 'Unknown error'),
                        'job_id': job_id
                    }
                elif status in ['IN_QUEUE', 'IN_PROGRESS']:
                    logger.info(f"🏃 Job in progress... (Status: {status})")
                    time.sleep(check_interval)
                else:
                    logger.warning(f"❓ Unknown status: {status}")
                    return {
                        'status': 'UNKNOWN',
                        'data': status_data,
                        'job_id': job_id
                    }
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Status check error: {e}")
                time.sleep(check_interval)
        
        logger.error(f"❌ Job wait timeout ({max_wait_time} seconds)")
        return {
            'status': 'TIMEOUT',
            'job_id': job_id
        }
    
    def save_video_result(self, result: Dict[str, Any], output_path: str) -> bool:
        """
        Save base64 video response to an MP4 file
        """
        try:
            if result.get('status') != 'COMPLETED':
                logger.error(f"Job not completed successfully: {result.get('status')}")
                return False
            
            output = result.get('output', {})
            video_b64 = output.get('video')
            
            if not video_b64:
                logger.error("Video output base64 data not found in response")
                return False
            
            # Clean base64 metadata prefix if present
            if ',' in video_b64:
                video_b64 = video_b64.split(',')[1]
                
            # Create output directories
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            decoded_video = base64.b64decode(video_b64)
            with open(output_path, 'wb') as f:
                f.write(decoded_video)
            
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ Video saved successfully: {output_path} ({file_size / (1024*1024):.2f}MB)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save video output file: {e}")
            return False
    
    def generate_video(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        text_to_video: bool = False,
        negative_prompt: Optional[str] = None,
        width: int = 1280,
        height: int = 720,
        duration: int = 5,
        frame_rate: int = 25,
        seed: int = 42,
        cfg: float = 1.0,
        lora_name: str = "ltx-2.3-22b-distilled-lora-384.safetensors",
        lora_weight: float = 0.5
    ) -> Dict[str, Any]:
        """
        Generate a video using LTX 2.3
        
        Args:
            prompt: Text prompt describing the video
            image_path: Local path to the input image (I2V mode)
            image_url: URL to the input image (I2V mode)
            image_base64: Base64 string of the input image (I2V mode)
            text_to_video: True for T2V, False for I2V
            negative_prompt: Negative prompt to exclude unwanted aesthetics
            width: Output width (px)
            height: Output height (px)
            duration: Video duration in seconds
            frame_rate: Frames per second
            seed: Denoising seed
            cfg: Classifier Free Guidance scale
            lora_name: Distilled LoRA name
            lora_weight: Distilled LoRA model weight strength
        """
        input_data = {
            "prompt": prompt,
            "text_to_video": text_to_video,
            "width": width,
            "height": height,
            "duration": duration,
            "frame_rate": frame_rate,
            "seed": seed,
            "cfg": cfg,
            "lora_name": lora_name,
            "lora_weight": lora_weight
        }
        
        if negative_prompt:
            input_data["negative_prompt"] = negative_prompt
            
        # Handle image encoding if image_path is supplied and not running in pure T2V
        if not text_to_video:
            if image_base64:
                input_data["image_base64"] = image_base64
            elif image_url:
                input_data["image_url"] = image_url
            elif image_path:
                encoded_img = self.encode_file_to_base64(image_path)
                if not encoded_img:
                    return {"error": "Failed to encode image path to base64"}
                input_data["image_base64"] = encoded_img
            else:
                logger.warning("No image input was supplied for Image-to-Video mode. Fallback placeholder will be used.")

        # Submit job
        job_id = self.submit_job(input_data)
        if not job_id:
            return {"error": "Failed to submit job to RunPod"}
        
        # Wait for Completion
        return self.wait_for_completion(job_id)

    def batch_process_images(
        self,
        image_folder_path: str,
        output_folder_path: str,
        prompt: str,
        valid_extensions: tuple = ('.jpg', '.jpeg', '.png', '.bmp', '.webp'),
        negative_prompt: Optional[str] = None,
        width: int = 1280,
        height: int = 720,
        duration: int = 5,
        frame_rate: int = 25,
        seed: int = 42,
        cfg: float = 1.0,
        lora_name: str = "ltx-2.3-22b-distilled-lora-384.safetensors",
        lora_weight: float = 0.5
    ) -> Dict[str, Any]:
        """
        Submit a batch of Image-to-Video generation jobs from a folder of images
        """
        if not os.path.isdir(image_folder_path):
            return {"error": f"Image folder path does not exist: {image_folder_path}"}
            
        os.makedirs(output_folder_path, exist_ok=True)
        
        image_files = [
            f for f in os.listdir(image_folder_path)
            if f.lower().endswith(valid_extensions)
        ]
        
        if not image_files:
            return {"error": f"No valid images found in: {image_folder_path}"}
            
        logger.info(f"Starting batch processing of {len(image_files)} image files...")
        
        results = {
            "total_files": len(image_files),
            "successful": 0,
            "failed": 0,
            "results": []
        }
        
        for filename in image_files:
            logger.info(f"\n🚀 Batch Job Started: {filename}")
            image_path = os.path.join(image_folder_path, filename)
            
            result = self.generate_video(
                prompt=prompt,
                image_path=image_path,
                text_to_video=False,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                duration=duration,
                frame_rate=frame_rate,
                seed=seed,
                cfg=cfg,
                lora_name=lora_name,
                lora_weight=lora_weight
            )
            
            if result.get('status') == 'COMPLETED':
                base_name = os.path.splitext(filename)[0]
                out_file = os.path.join(output_folder_path, f"ltx23_{base_name}.mp4")
                
                if self.save_video_result(result, out_file):
                    results["successful"] += 1
                    results["results"].append({
                        "filename": filename,
                        "status": "success",
                        "output": out_file,
                        "job_id": result.get('job_id')
                    })
                else:
                    results["failed"] += 1
                    results["results"].append({
                        "filename": filename,
                        "status": "failed",
                        "error": "Failed to save generated video",
                        "job_id": result.get('job_id')
                    })
            else:
                results["failed"] += 1
                results["results"].append({
                    "filename": filename,
                    "status": "failed",
                    "error": result.get('error', 'Unknown job execution error'),
                    "job_id": result.get('job_id')
                })
                
        logger.info(f"\n🎉 Batch processing finished: {results['successful']} successful, {results['failed']} failed.")
        return results

def main():
    # Example client usage configurations
    ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "your-endpoint-id")
    API_KEY = os.getenv("RUNPOD_API_KEY", "your-runpod-api-key")
    
    client = GenerateVideoClient(runpod_endpoint_id=ENDPOINT_ID, runpod_api_key=API_KEY)
    
    print("LTX 2.3 Serverless Client Example Usage:")
    print("------------------------------------------")
    print("1. Launching Image-to-Video generation...")
    # Example payload submission
    result = client.generate_video(
        prompt="A majestic lion standing atop a hill overlooking the savannah at sunrise, high quality, realistic",
        image_path="./example_image.png",
        width=1280,
        height=720,
        duration=5,
        seed=100
    )
    
    if result.get("status") == "COMPLETED":
        client.save_video_result(result, "./output_lion.mp4")
    else:
        print(f"Generation failed: {result.get('error')}")

if __name__ == "__main__":
    main()
