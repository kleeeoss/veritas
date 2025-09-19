# projects/veritas/ml/train.py

import os
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from PIL import Image, UnidentifiedImageError
from sklearn.model_selection import train_test_split
from torch.optim.lr_scheduler import StepLR

# --- Configuration ---
# CORRECTED: Go up one more directory to find the true project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "synthetic", "veritas")
LABELS_FILE = os.path.join(DATA_DIR, "labels.csv")
MODEL_OUTPUT_PATH = os.path.join(PROJECT_ROOT, 'models/veritas/v0/model_v0.pt')

NUM_EPOCHS = 100
BATCH_SIZE = 16
LEARNING_RATE = 0.0001


# --- 1. Custom Dataset Definition ---
class CertificateDataset(Dataset):
    def __init__(self, annotations_file, img_dir, transform=None):
        self.img_labels_df = pd.read_csv(annotations_file)
        self.img_dir = img_dir
        self.transform = transform

        self.string_labels = self.img_labels_df['label'].copy()
        self.numeric_labels = self.img_labels_df['label'].apply(lambda x: 1 if x == 'forged' else 0)

    def __len__(self):
        return len(self.img_labels_df)

    def __getitem__(self, idx):
        # Loop to find a valid image, skipping corrupted ones
        while True:
            try:
                label_folder = self.string_labels.iloc[idx]
                filename = self.img_labels_df.iloc[idx, 0]
                img_path = os.path.join(self.img_dir, label_folder, filename)

                # This is the line that can fail
                image = Image.open(img_path).convert('RGB')

                label = torch.tensor(self.numeric_labels.iloc[idx], dtype=torch.float32)

                if self.transform:
                    image = self.transform(image)

                return image, label

            except (IOError, UnidentifiedImageError):
                print(f"⚠️ Warning: Skipping corrupted image file: {img_path}")
                # If an image is corrupted, try the next one in the dataset
                idx = (idx + 1) % len(self)


# --- 2. Image Transformations (No change) ---
train_transforms = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomRotation(10),
    transforms.RandomHorizontalFlip(),
    transforms.ColorJitter(brightness=0.2, contrast=0.2),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

val_transforms = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# --- 3. Main Training Logic ---
if __name__ == '__main__':
    print("Starting model training process...")

    full_dataset = CertificateDataset(annotations_file=LABELS_FILE, img_dir=DATA_DIR)


    class TransformedDataset(Dataset):
        def __init__(self, original_dataset, indices, transform):
            self.original_dataset = original_dataset
            self.indices = indices
            self.transform = transform

        def __len__(self):
            return len(self.indices)

        def __getitem__(self, idx):
            original_idx = self.indices[idx]
            image, label = self.original_dataset[original_idx]
            image = self.transform(image)
            return image, label


    all_labels = pd.read_csv(LABELS_FILE)['label'].tolist()
    train_indices, val_indices = train_test_split(
        list(range(len(all_labels))),
        test_size=0.2,
        random_state=42,
        stratify=all_labels
    )

    train_dataset = TransformedDataset(full_dataset, train_indices, train_transforms)
    val_dataset = TransformedDataset(full_dataset, val_indices, val_transforms)

    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)

    print(f"Dataset loaded: {len(train_dataset)} training samples, {len(val_dataset)} validation samples.")

    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    num_ftrs = model.fc.in_features
    model.fc = nn.Sequential(nn.Linear(num_ftrs, 1), nn.Sigmoid())

    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = StepLR(optimizer, step_size=7, gamma=0.1)

    print("Starting training loop...")
    for epoch in range(NUM_EPOCHS):
        model.train()
        running_loss = 0.0
        for inputs, labels in train_loader:
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels.unsqueeze(1))
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * inputs.size(0)

        epoch_loss = running_loss / len(train_loader.dataset)
        print(f"Epoch {epoch + 1}/{NUM_EPOCHS}, Loss: {epoch_loss:.4f}")

        scheduler.step()

    print("Training finished. Saving model...")
    os.makedirs(os.path.dirname(MODEL_OUTPUT_PATH), exist_ok=True)
    torch.save(model.state_dict(), MODEL_OUTPUT_PATH)
    print(f"✅ Model saved successfully to {MODEL_OUTPUT_PATH}")