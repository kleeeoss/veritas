# Veritas Synthetic Dataset

## Overview

This directory contains the synthetic dataset used for training and testing the Veritas document forgery detection model. The dataset consists of PNG images of certificates, categorized as either "genuine" or "forged".

---

## Directory Structure

-   **/genuine/**: Contains original, unaltered certificate images. These are considered the "ground truth" for authentic documents.
-   **/forged/**: Contains modified versions of the genuine certificates. Forgeries may include altered names, dates, grades, or other subtle manipulations.
-   **labels.csv**: A manifest file that maps each image filename to its correct label.

---

## `labels.csv` File Format

The `labels.csv` file is the source of truth for the dataset labels. It has two columns:

-   `filename`: The name of the image file (e.g., `cert_001.png`).
-   `label`: The classification of the image. This will be either `genuine` or `forged`.

**Example:**

```csv
filename,label
cert_001.png,genuine
cert_002_forged.png,forged
```