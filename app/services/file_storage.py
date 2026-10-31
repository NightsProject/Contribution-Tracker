from io import BytesIO
import os
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from app.config import get_settings

SUPPORTED_FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}
MAX_IMAGE_PIXELS = 25_000_000


class InvalidImageError(ValueError):
    pass


def decode_image(contents: bytes) -> tuple[bytes, str, str]:
    try:
        with Image.open(BytesIO(contents)) as image:
            image_format = image.format
            if image_format not in SUPPORTED_FORMATS:
                raise InvalidImageError("Upload must be a JPEG, PNG, or WebP image.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise InvalidImageError("Image dimensions exceed the allowed limit.")
            image.verify()
        with Image.open(BytesIO(contents)) as image:
            image.load()
            extension, media_type = SUPPORTED_FORMATS[image.format]
            output = BytesIO()
            if image.format == "JPEG":
                image.convert("RGB").save(output, format="JPEG", optimize=True)
            elif image.format == "PNG":
                image.save(output, format="PNG", optimize=True)
            else:
                image.save(output, format="WEBP", quality=90, method=4)
            return output.getvalue(), extension, media_type
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, DecompressionBombError) as error:
        raise InvalidImageError("Upload must be a valid JPEG, PNG, or WebP image.") from error


def store_private_image(contents: bytes) -> tuple[str, str, Path]:
    normalized, extension, media_type = decode_image(contents)
    directory = Path(get_settings().uploads_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    file_key = f"{uuid4().hex}.{extension}"
    file_path = directory / file_key
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(file_path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as image_file:
            image_file.write(normalized)
    except OSError:
        file_path.unlink(missing_ok=True)
        raise
    return file_key, media_type, file_path


def private_image_path(file_key: str) -> Path:
    directory = Path(get_settings().uploads_dir).resolve()
    file_path = (directory / file_key).resolve()
    if file_path.parent != directory:
        raise ValueError("Invalid private file key.")
    return file_path
