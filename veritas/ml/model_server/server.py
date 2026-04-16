# veritas/ml/model_server/server.py

import io
import base64
import os
import numpy as np
import cv2
from PIL import Image

import torch
import torch.nn as nn
from torchvision import models, transforms

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# --- (App Initialization, Model Definition, and Model Loading are unchanged) ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
num_ftrs = model.fc.in_features
model.fc = nn.Linear(num_ftrs, 1)

MODEL_PATH = "/app/models/v1/model_v1.pt"
MODEL_VERSION = os.getenv("MODEL_VERSION", "v1")
try:
    model.load_state_dict(torch.load(MODEL_PATH, map_location=torch.device('cpu')))
    print("✅ Custom forgery detection model loaded successfully.")
except Exception as e:
    print(f"❌ Failed to load model: {e}")
model.eval()

preprocess = transforms.Compose([
    transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# --- (Grad-CAM logic is unchanged) ---
activations, gradients = None, None


def backward_hook(module, grad_input, grad_output): global gradients; gradients = grad_output[0]


def forward_hook(module, input, output): global activations; activations = output


def generate_heatmap(model, input_tensor, original_image):
    target_layer = model.layer4[1].conv2
    handle_forward = target_layer.register_forward_hook(forward_hook)
    handle_backward = target_layer.register_full_backward_hook(backward_hook)
    output = model(input_tensor)
    model.zero_grad()
    output.backward()
    pooled_gradients = torch.mean(gradients, dim=[0, 2, 3])
    for i in range(activations.shape[1]): activations[:, i, :, :] *= pooled_gradients[i]
    heatmap = torch.mean(activations, dim=1).squeeze().detach().cpu()
    heatmap = np.maximum(heatmap, 0)
    if torch.max(heatmap) > 0: heatmap /= torch.max(heatmap)
    heatmap = cv2.resize(np.array(heatmap), (original_image.shape[1], original_image.shape[0]))
    heatmap = np.uint8(255 * heatmap)
    heatmap = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
    superimposed_img = heatmap * 0.5 + original_image
    superimposed_img = np.clip(superimposed_img, 0, 255)
    superimposed_img = np.uint8(superimposed_img)
    handle_forward.remove()
    handle_backward.remove()
    return superimposed_img


@app.get("/metadata")
def metadata():
    return {
        "model_version": MODEL_VERSION,
        "model_path": MODEL_PATH,
        "status": "loaded",
        "architecture": "resnet18-binary",
    }


# --- 5. Prediction Endpoint ---
@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    contents = await file.read()
    pil_image = Image.open(io.BytesIO(contents)).convert("RGB")

    input_tensor = preprocess(pil_image).unsqueeze(0)
    input_tensor.requires_grad = True

    output = model(input_tensor)
    forgery_score = torch.sigmoid(output).item()

    original_cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    heatmap_image = generate_heatmap(model, input_tensor, original_cv_image)

    _, buffer = cv2.imencode('.jpg', heatmap_image)
    heatmap_base64 = base64.b64encode(buffer).decode('utf-8')

    return {
        "forgery_score": forgery_score,
        "heatmap": heatmap_base64,
        "model_version": MODEL_VERSION,
    }
