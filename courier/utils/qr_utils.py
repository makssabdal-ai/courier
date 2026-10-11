from typing import Optional
import cv2
import numpy as np


def generate_qr_bytes(data: str) -> bytes:
    encoder = cv2.QRCodeEncoder.create()
    qr_img = encoder.encode(data)
    qr_img = cv2.resize(qr_img, (300, 300), interpolation=cv2.INTER_NEAREST)
    _, buf = cv2.imencode('.png', qr_img)
    return bytes(buf)


def decode_qr_from_bytes(image_bytes: bytes) -> Optional[str]:
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return data if data else None


def make_qr_data(track_number: str, internal_number: str,
                 recipient_name: str, recipient_address: str) -> str:
    return (
        f"TRACK:{track_number};"
        f"INTERNAL:{internal_number};"
        f"RECIPIENT:{recipient_name};"
        f"ADDRESS:{recipient_address}"
    )


def parse_qr_data(raw: str) -> dict:
    result = {}
    for part in raw.split(';'):
        if ':' in part:
            key, _, val = part.partition(':')
            result[key.strip()] = val.strip()
    return result
