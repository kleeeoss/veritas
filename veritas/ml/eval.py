# projects/veritas/ml/eval.py

import os
import torch
from torchvision import models, datasets, transforms
import torch.nn as nn
from torch.utils.data import DataLoader, SubsetRandomSampler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, confusion_matrix
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# --- Configuration ---
DATA_DIR = 'data/synthetic/veritas'
MODEL_PATH = 'models/veritas/v1/model_v1.pt' # Make sure this points to the model you just trained
OUTPUT_DIR = 'models/veritas/v1/'
BATCH_SIZE = 16

# --- Validation Transforms (must match the ones from training) ---
val_transforms = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# --- Main Evaluation Logic ---
if __name__ == '__main__':
    DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

    # --- New Data Loading using ImageFolder ---
    eval_dataset = datasets.ImageFolder(DATA_DIR, transform=val_transforms)
    all_labels = eval_dataset.targets
    
    # Get the *exact same* validation split as in train.py (using same random_state)
    train_indices, val_indices = train_test_split(
        list(range(len(all_labels))), 
        test_size=0.2, 
        random_state=42,
        stratify=all_labels
    )
    
    val_sampler = SubsetRandomSampler(val_indices)
    eval_loader = DataLoader(eval_dataset, batch_size=BATCH_SIZE, sampler=val_sampler)
    
    # Re-create model architecture
    model = models.resnet18(weights=None)
    num_ftrs = model.fc.in_features
    model.fc = nn.Linear(num_ftrs, 1) # Must match the saved model
    
    # Load the saved weights
    model.load_state_dict(torch.load(MODEL_PATH, map_location=torch.device(DEVICE)))
    model.to(DEVICE)
    model.eval()
    
    all_labels_eval = []
    all_preds = []
    
    print("Running evaluation on the validation set...")
    with torch.no_grad():
        for inputs, labels in eval_loader:
            inputs, labels = inputs.to(DEVICE), labels.to(DEVICE)
            
            outputs = model(inputs)
            
            # Convert outputs (logits) to probabilities (sigmoid) then to preds (0 or 1)
            preds = (torch.sigmoid(outputs) > 0.5).float() # 1 = predicted forged
            
            # <<< NEW LABEL LOGIC >>>
            # ImageFolder labels: forged=0, genuine=1
            # We want: forged=1, genuine=0 (to match our model's output logic)
            true_labels = 1.0 - labels.float()
            
            all_labels_eval.extend(true_labels.cpu().numpy())
            all_preds.extend(preds.cpu().numpy().flatten())

    # Calculate and Print Metrics
    accuracy = accuracy_score(all_labels_eval, all_preds)
    precision = precision_score(all_labels_eval, all_preds)
    recall = recall_score(all_labels_eval, all_preds)
    cm = confusion_matrix(all_labels_eval, all_preds)
    
    print("\n--- Evaluation Metrics for model_v1 ---")
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print("---------------------------------------\n")
    
    print("Confusion Matrix:")
    plt.figure(figsize=(6, 5))
    # Labels for confusion matrix: 0=Genuine, 1=Forged
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=['Genuine (0)', 'Forged (1)'], yticklabels=['Genuine (0)', 'Forged (1)'])
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.title('Confusion Matrix for model_v1')
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, 'confusion_matrix_v1.png')
    plt.savefig(output_path)
    print(f"✅ Confusion matrix plot saved to {output_path}")