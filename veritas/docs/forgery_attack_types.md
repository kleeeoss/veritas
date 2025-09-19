
# Veritas: Forgery Attack Vector Specification

This document specifies the types of forgeries Sehaj must generate for the synthetic dataset. The goal is to create a diverse training set that covers common digital forgery techniques.

### Synthetic Forgery Types

The `veritas_generator.py` script must be updated to support the following transformations. Each "forged" sample should have at least one of these transformations applied.

1.  **Text Tampering**
    -   **Description:** Altering critical text fields directly on the document.
    -   **Examples:**
        -   Change a name ("Jane Doe" to "Jane Smith").
        -   Modify the course name ("Computer Science" to "Computational Sciences").
        -   Alter the date of issuance.
    -   **Implementation:** Locate text bounding boxes and replace the text using a similar (but not identical) font. Introduce slight alignment errors.

2.  **Logo Swap**
    -   **Description:** Replacing the official institution logo with a slightly different or entirely incorrect one.
    -   **Examples:**
        -   Use an older, low-resolution version of the institution's logo.
        -   Use the logo of a different institution.
    -   **Implementation:** Paste a new logo image over the original logo's location.

3.  **Signature Forgery**
    -   **Description:** Replacing or altering the digital or scanned signature.
    -   **Examples:**
        -   Copy-paste a signature from a different document.
        -   Slightly erase parts of the original signature.
    -   **Implementation:** Identify the signature area and overlay a different signature image with a transparent background.

4.  **Font Inconsistency**
    -   **Description:** Using a font that is inconsistent with the rest of the document for an altered field.
    -   **Example:** The entire document uses Times New Roman, but a changed name is in Arial.
    -   **Implementation:** When performing Text Tampering, use a noticeably different font family or weight.
