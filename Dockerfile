# Use specific version of nvidia cuda image
FROM wlsdml1114/engui_genai-base_blackwell:1.1 as runtime

# Install pip updates and core packages
RUN pip install -U "huggingface_hub[hf_transfer]"
RUN pip install runpod websocket-client Pillow

WORKDIR /

# Clone and install ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd /ComfyUI && \
    pip install -r requirements.txt

# Clone custom nodes
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Comfy-Org/ComfyUI-Manager.git && \
    cd ComfyUI-Manager && \
    pip install -r requirements.txt
    
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git && \
    cd ComfyUI-KJNodes && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git && \
    cd ComfyUI-LTXVideo && \
    pip install -r requirements.txt

RUN mkdir -p /ComfyUI/models/checkpoints && \
    wget -q https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors -O /ComfyUI/models/checkpoints/ltx-2.3-22b-dev-fp8.safetensors

RUN mkdir -p /ComfyUI/models/text_encoders && \
    wget -q https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors -O /ComfyUI/models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors

RUN mkdir -p /ComfyUI/models/latent_upscale_models && \
    wget -q https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors -O /ComfyUI/models/latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors

RUN mkdir -p /ComfyUI/models/loras && \
    wget -q https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384.safetensors -O /ComfyUI/models/loras/ltx-2.3-22b-distilled-lora-384.safetensors

# Copy configuration and code files
COPY . .
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
COPY workflow_ltx23_api.json /workflow_ltx23_api.json

RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
