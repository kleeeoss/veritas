import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
import os
from typing import Optional

def generate_qr_code(data: str, output_dir: str, filename: str = "qr_code.png") -> Optional[str]:
    """
    Generates a stylized QR code image from the given data.

    Args:
        data: The string data to encode in the QR code (e.g., a verification URL).
        output_dir: The directory to save the generated image in.
        filename: The name of the output image file.

    Returns:
        The full path to the generated QR code image, or None on failure.
    """
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer()
        )

        output_path = os.path.join(output_dir, filename)
        img.save(output_path)
        print(f"QR Code successfully generated at: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None

if __name__ == '__main__':
    print("--- Running QR Code Generator Test ---")
    test_data = "https://nullpoint.sih.gov/verify/cert_hash_12345"
    test_output_dir = "demos/generated_certs"
    generate_qr_code(data=test_data, output_dir=test_output_dir, filename="sample_qr.png")
    print("--- Test Complete ---")