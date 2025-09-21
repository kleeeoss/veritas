# veritas/ml/model_server/server.py

import io
import base64
import numpy as np
import cv2
from PIL import Image

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models, transforms

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# --- 1. Initialize FastAPI App ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. Load Your Trained Model (Corrected Method) ---
# This is the corrected section. It builds a ResNet18 model first,
# then modifies the final layer, and THEN loads your saved weights.
# This ensures the architecture perfectly matches the saved file.

# Step 1: Load the standard ResNet18 architecture with default weights
model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)

# Step 2: Get the number of input features for the final layer
num_ftrs = model.fc.in_features

# Step 3: Replace the final layer with a new one for our binary task (1 output neuron)
model.fc = nn.Linear(num_ftrs, 1)

# Step 4: Now, load the trained weights from your file into this matching architecture
MODEL_PATH = "/app/models/v1/model_v1.pt"
model.load_state_dict(torch.load(MODEL_PATH, map_location=torch.device('cpu')))

# Step 5: Set the model to evaluation mode
model.eval()
print("✅ Custom forgery detection model loaded successfully.")

# --- 3. Image Preprocessing ---
preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# --- (Grad-CAM logic remains the same) ---
activations = None
gradients = None


def backward_hook(module, grad_input, grad_output):
    global gradients
    gradients = grad_output[0]


def forward_hook(module, input, output):
    global activations
    activations = output


def generate_heatmap(model, input_tensor, original_image):
    # Target the last convolutional layer in ResNet18
    target_layer = model.layer4[1].conv2

    handle_forward = target_layer.register_forward_hook(forward_hook)
    handle_backward = target_layer.register_full_backward_hook(backward_hook)

    output = model(input_tensor)
    model.zero_grad()

    # We backpropagate the output directly for Grad-CAM
    output.backward()

    pooled_gradients = torch.mean(gradients, dim=[0, 2, 3])
    for i in range(activations.shape[1]):
        activations[:, i, :, :] *= pooled_gradients[i]

    heatmap = torch.mean(activations, dim=1).squeeze().detach().cpu()
    heatmap = np.maximum(heatmap, 0)

    if torch.max(heatmap) > 0:
        heatmap /= torch.max(heatmap)

    heatmap = cv2.resize(np.array(heatmap), (original_image.shape[1], original_image.shape[0]))
    heatmap = np.uint8(255 * heatmap)
    heatmap = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

    superimposed_img = heatmap * 0.5 + original_image
    superimposed_img = np.clip(superimposed_img, 0, 255)
    superimposed_img = np.uint8(superimposed_img)

    # Remove the hooks after use
    handle_forward.remove()
    handle_backward.remove()

    return superimposed_img


# --- 5. Prediction Endpoint ---
@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    contents = await file.read()
    pil_image = Image.open(io.BytesIO(contents)).convert("RGB")

    input_tensor = preprocess(pil_image).unsqueeze(0)
    input_tensor.requires_grad = True

    output = model(input_tensor)
    # Apply sigmoid to the raw output to get a probability score
    forgery_score = torch.sigmoid(output).item()

    original_cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    heatmap_image = generate_heatmap(model, input_tensor, original_cv_image)

    _, buffer = cv2.imencode('.jpg', heatmap_image)
    heatmap_base64 = base64.b64encode(buffer).decode('utf-8')

    return {
        "forgery_score": forgery_score,
        "heatmap": heatmap_base64
    }