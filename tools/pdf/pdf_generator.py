from fpdf import FPDF
import os
from typing import Dict

class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 16)
        self.cell(0, 10, 'Nullpoint Systems - Certificate of Sanitization', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def create_wipe_certificate(cert_data: Dict[str, str], qr_image_path: str, output_path: str):
    """
    Generates a PDF certificate from wipe data and a QR code.

    Args:
        cert_data: A dictionary containing the certificate details.
        qr_image_path: The file path to the QR code image to embed.
        output_path: The full path where the PDF will be saved.
    """
    try:
        pdf = PDF()
        pdf.add_page()
        pdf.set_font('Helvetica', '', 12)

        for key, value in cert_data.items():
            pdf.set_font('Helvetica', 'B', 12)
            pdf.cell(50, 10, f"{key}:", 0, 0)
            pdf.set_font('Helvetica', '', 12)
            pdf.cell(0, 10, value, 0, 1)

        pdf.ln(10)

        if os.path.exists(qr_image_path):
            pdf.image(qr_image_path, x=(210-50)/2, w=50)
        
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        pdf.output(output_path)
        print(f"PDF certificate successfully generated at: {output_path}")
    except Exception as e:
        print(f"Error generating PDF: {e}")

if __name__ == '__main__':
    # This block requires the qr_generator module to exist
    try:
        from tools.qr.qr_generator import generate_qr_code
    except ImportError:
        print("Could not import generate_qr_code. Please ensure tools/qr/qr_generator.py exists.")
        generate_qr_code = None

    print("--- Running PDF Certificate Generator Test ---")
    
    test_verification_url = "https://nullpoint.sih.gov/verify/hash_abcdef123456"
    test_cert_data = {
        "Certificate ID": "NP-CERT-2025-001",
        "Timestamp (UTC)": "2025-09-12 17:00:00",
        "Device ID": "SN-987654321",
        "Wipe Method": "DoD 5220.22-M (3-pass)",
        "Pre-Wipe Hash (SHA256)": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "Post-Wipe Hash (SHA256)": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "Verification URL": test_verification_url
    }
    test_output_dir = "demos/generated_certs"
    
    if generate_qr_code:
        qr_path = generate_qr_code(
            data=test_verification_url, 
            output_dir=test_output_dir, 
            filename="cert_qr.png"
        )

        if qr_path:
            pdf_path = os.path.join(test_output_dir, "sample_certificate.pdf")
            create_wipe_certificate(
                cert_data=test_cert_data, 
                qr_image_path=qr_path, 
                output_path=pdf_path
            )
    
    print("--- Test Complete ---")