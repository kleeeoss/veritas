# tools/data_validator.py

import os
import pandas as pd
from PIL import Image


def validate_dataset(base_path='data/synthetic/veritas'):
    """
    Validates the Veritas dataset by checking for file existence and integrity.

    - Reads the labels.csv file.
    - Checks if each image file listed exists in the correct subfolder.
    - Tries to open each image to check for corruption.
    """
    labels_path = os.path.join(base_path, 'labels.csv')
    if not os.path.exists(labels_path):
        print(f"❌ Error: labels.csv not found at '{labels_path}'")
        return

    print(f"🔍 Reading dataset labels from '{labels_path}'...")
    df = pd.read_csv(labels_path)

    missing_files = 0
    corrupted_files = 0

    print(f"🔬 Starting validation for {len(df)} entries...")

    for index, row in df.iterrows():
        filename = row['filename']
        label = row['label']  # 'genuine' or 'forged'

        # Construct the full path to the image
        # The label directly corresponds to the folder name
        image_path = os.path.join(base_path, label, filename)

        # 1. Check if the file exists
        if not os.path.exists(image_path):
            print(f"  - ❗️ Missing file: {image_path}")
            missing_files += 1
            continue  # Skip to the next file

        # 2. Check if the file is a valid image (not corrupt)
        try:
            with Image.open(image_path) as img:
                img.verify()  # Verifies image integrity
        except Exception as e:
            print(f"  - ❗️ Corrupted file: {image_path} (Error: {e})")
            corrupted_files += 1

    print("\n✅ Validation Complete!")
    print("---" * 10)
    print(f"📊 Summary:")
    print(f"  - Total entries checked: {len(df)}")
    print(f"  - Missing files found: {missing_files}")
    print(f"  - Corrupted files found: {corrupted_files}")
    print("---" * 10)


if __name__ == "__main__":
    validate_dataset()