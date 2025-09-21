import qrcode
import io
import base64
import json
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer

def create_qr_code(data: dict) -> str:
    """
    Generates a stylized QR code from the given dictionary,
    and returns it as a base64 encoded string.

    Args:
        data: A dictionary to encode into the QR code.

    Returns:
        A base64 encoded string representation of the QR code image.
    """
    try:
        # Convert the dictionary to a JSON string to embed in the QR code
        data_str = json.dumps(data, indent=None, separators=(",", ":"))

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data_str)
        qr.make(fit=True)

        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer()
        )

        # Save the image to an in-memory buffer
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")

        # Encode the bytes in the buffer to a base64 string
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # Return the standard data URI for the frontend
        return f"data:image/png;base64,{img_str}"

    except Exception as e:
        print(f"Error generating QR code: {e}")
        # In case of an error, return an empty string or handle it as needed
        return ""