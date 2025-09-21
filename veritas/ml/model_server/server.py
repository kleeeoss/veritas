# veritas/ml/model_server/server.py

import io
import base64
import numpy as np
import cv2
from PIL import Image

import torch
import torch.nn.functional as F
from torchvision import transforms

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# --- 1. Initialize FastAPI App ---
app = FastAPI()

# Allow all origins for development (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
``
# --- 2. Load Your Model ---
# Note: Make sure your model is in evaluation mode
# model = YourModelClass()
# model.load_state_dict(torch.load("path/to/your/model_v0.pt", map_location=torch.device('cpu')))
# model.eval()
# For demonstration, we'll create a placeholder model
model = torch.hub.load('pytorch/vision:v0.10.0', 'resnet18', pretrained=True)
model.eval()

# --- 3. Image Preprocessing ---
# This should match the transformations used during training
preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# --- 4. Grad-CAM and Heatmap Generation Logic ---
# Global variables to store activations and gradients
activations = None
gradients = None

def backward_hook(module, grad_input, grad_output):
    global gradients
    gradients = grad_output[0]

def forward_hook(module, input, output):
    global activations
    activations = output

def generate_heatmap(model, input_tensor, original_image, class_idx):
    """
    Generates a Grad-CAM heatmap and overlays it on the original image.
    """
    # Find the target layer (last conv layer)
    target_layer = model.layer4[1].conv2 
    
    # Register hooks
    target_layer.register_forward_hook(forward_hook)
    target_layer.register_backward_hook(backward_hook)

    # Forward pass
    output = model(input_tensor)
    
    # Backward pass
    model.zero_grad()
    output[0][class_idx].backward()

    # Get activations and gradients
    pooled_gradients = torch.mean(gradients, dim=[0, 2, 3])
    
    # Weight the activations with gradients
    for i in range(activations.shape[1]):
        activations[:, i, :, :] *= pooled_gradients[i]
        
    # Generate heatmap
    heatmap = torch.mean(activations, dim=1).squeeze().detach().cpu()
    heatmap = np.maximum(heatmap, 0)
    heatmap /= torch.max(heatmap)
    
    # Resize and apply colormap
    heatmap = cv2.resize(np.array(heatmap), (original_image.shape[1], original_image.shape[0]))
    heatmap = np.uint8(255 * heatmap)
    heatmap = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

    # Superimpose heatmap on original image
    superimposed_img = heatmap * 0.4 + original_image
    superimposed_img = np.uint8(superimposed_img)
    
    return superimposed_img


# --- 5. Prediction Endpoint ---
@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    # Read and process image
    contents = await file.read()
    pil_image = Image.open(io.BytesIO(contents)).convert("RGB")
    input_tensor = preprocess(pil_image).unsqueeze(0)

    # Get model prediction
    with torch.no_grad():
        output = model(input_tensor)
        probabilities = F.softmax(output, dim=1)
        
    # Assuming class 1 is "forged"
    forgery_score = probabilities[0][1].item() 
    predicted_class_idx = torch.argmax(probabilities).item()

    # Convert PIL image to OpenCV format for heatmap overlay
    # Note: OpenCV uses BGR, PIL uses RGB
    original_cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    
    # Generate the heatmap
    heatmap_image = generate_heatmap(model, input_tensor, original_cv_image, predicted_class_idx)

    # Encode heatmap image to base64
    _, buffer = cv2.imencode('.jpg', heatmap_image)
    heatmap_base64 = base64.b64encode(buffer).decode('utf-8')
    
    # Return JSON response
    return {
        "forgery_score": forgery_score,
        "heatmap": heatmap_base64
        # You can add the OCR text here as well if it's part of this service
    }

# Entry point for running the server (optional)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)