# tools/signing/sign_helper.py

import os
import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

KEY_DIR = "keys"
PRIVATE_KEY_PATH = os.path.join(KEY_DIR, "ecdsa_private_key.pem")
PUBLIC_KEY_PATH = os.path.join(KEY_DIR, "ecdsa_public_key.pem")

def load_or_create_keys():
    """
    Loads the ECDSA key pair from disk. If they don't exist, generates them.
    """
    if os.path.exists(PRIVATE_KEY_PATH):
        with open(PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
        return private_key, private_key.public_key()
    else:
        print("Private key not found. Generating new keys...")
        return generate_key_pair()

def generate_key_pair():
    """
    Generates an ECDSA private/public key pair and saves them to disk.
    """
    print("Generating new ECDSA key pair...")
    os.makedirs(KEY_DIR, exist_ok=True)
    
    private_key = ec.generate_private_key(ec.SECP384R1(), default_backend())
    public_key = private_key.public_key()
    
    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    print(f"Keys saved to {KEY_DIR}/")
    return private_key, public_key

def sign_data(data_dict: dict) -> str:
    """
    Signs a dictionary by first converting it to a consistent JSON string.

    Args:
        data_dict (dict): The dictionary payload to sign.

    Returns:
        str: The signature as a hex-encoded string.
    """
    private_key, _ = load_or_create_keys()

    # 1. CRITICAL FIX: Serialize the dictionary to a consistent JSON string.
    #    sort_keys=True ensures the order is always the same, creating a stable signature.
    payload_string = json.dumps(data_dict, sort_keys=True, separators=(",", ":"))

    # 2. Encode the string into bytes, which the signing function requires.
    payload_bytes = payload_string.encode('utf-8')

    # 3. Sign the bytes.
    signature = private_key.sign(
        payload_bytes,
        ec.ECDSA(hashes.SHA256())
    )

    # 4. Return the signature as a hex string for easy use in JSON.
    return signature.hex()

def verify_signature(public_key: ec.EllipticCurvePublicKey, signature_hex: str, data_dict: dict) -> bool:
    """
    Verifies a hex signature against the original dictionary data.
    """
    try:
        # Convert the dictionary to the exact same byte representation used for signing.
        payload_string = json.dumps(data_dict, sort_keys=True, separators=(",", ":"))
        payload_bytes = payload_string.encode('utf-8')
        
        # Convert the hex signature back to bytes.
        signature_bytes = bytes.fromhex(signature_hex)

        public_key.verify(
            signature_bytes,
            payload_bytes,
            ec.ECDSA(hashes.SHA256())
        )
        return True
    except Exception as e:
        print(f"Signature verification failed: {e}")
        return False

# --- Test harness ---
if __name__ == "__main__":
    _, test_public_key = load_or_create_keys()

    test_data_dict = {
      "filename": "test_document.pdf",
      "ocr_text": "This is a genuine document.",
      "timestamp": "2025-09-20T18:00:00Z"
    }
    
    print(f"Signing data: {test_data_dict}")
    hex_sig = sign_data(test_data_dict)
    print(f"Generated Hex Signature: {hex_sig}")

    is_valid = verify_signature(test_public_key, hex_sig, test_data_dict)
    print(f"Verification with correct data: {is_valid}")
    
    tampered_data = {"filename": "hacked.doc"}
    is_valid_tampered = verify_signature(test_public_key, hex_sig, tampered_data)
    print(f"Verification with tampered data: {is_valid_tampered}")