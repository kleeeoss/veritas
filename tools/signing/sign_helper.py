# tools/signing/sign_helper.py

import os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

KEY_DIR = "keys"
PRIVATE_KEY_PATH = os.path.join(KEY_DIR, "ecdsa_private_key.pem")
PUBLIC_KEY_PATH = os.path.join(KEY_DIR, "ecdsa_public_key.pem")

def generate_key_pair():
    """
    Generates an ECDSA private/public key pair and saves them to disk.
    Only needs to be run once.
    """
    print("Generating new ECDSA key pair...")
    os.makedirs(KEY_DIR, exist_ok=True)
    
    # Generate private key
    private_key = ec.generate_private_key(ec.SECP384R1(), default_backend())
    
    # Generate public key
    public_key = private_key.public_key()
    
    # Save private key to PEM file
    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Save public key to PEM file
    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    print(f"Keys saved to {KEY_DIR}/")
    return private_key, public_key

def sign_data(data: bytes) -> bytes:
    """
    Signs a piece of byte data using the saved private key.
    
    Args:
        data (bytes): The data to be signed.
        
    Returns:
        bytes: The ECDSA signature.
    """
    try:
        with open(PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend()
            )
    except FileNotFoundError:
        print("Private key not found. Generating new keys...")
        private_key, _ = generate_key_pair()

    signature = private_key.sign(
        data,
        ec.ECDSA(hashes.SHA256())
    )
    return signature

def verify_signature(public_key_pem: bytes, signature: bytes, data: bytes) -> bool:
    """
    Verifies a signature against the data using a given public key.
    
    Args:
        public_key_pem (bytes): The public key in PEM format.
        signature (bytes): The signature to verify.
        data (bytes): The original data.

    Returns:
        bool: True if signature is valid, False otherwise.
    """
    try:
        public_key = serialization.load_pem_public_key(
            public_key_pem,
            backend=default_backend()
        )
        
        public_key.verify(
            signature,
            data,
            ec.ECDSA(hashes.SHA256())
        )
        return True
    except Exception as e:
        # This will fail (as it should) if the signature or data is tampered with
        print(f"Signature verification failed: {e}")
        return False

# --- Test harness ---
if __name__ == "__main__":
    # Generate keys if they don't exist
    if not os.path.exists(PRIVATE_KEY_PATH):
        generate_key_pair()
    
    # Test signing
    test_data = b"This is a test log file for Oblivion wipe."
    print(f"Signing data: {test_data.decode()}")
    sig = sign_data(test_data)
    print(f"Generated Signature (first 20 bytes): {sig[:20].hex()}...")

    # Test verification
    with open(PUBLIC_KEY_PATH, "rb") as f:
        pub_key_pem = f.read()
    
    is_valid = verify_signature(pub_key_pem, sig, test_data)
    print(f"Verification with correct data: {is_valid}")
    
    # Test with tampered data
    tampered_data = b"This is a TAMPERED log file for Oblivion wipe."
    is_valid_tampered = verify_signature(pub_key_pem, sig, tampered_data)
    print(f"Verification with tampered data: {is_valid_tampered}")