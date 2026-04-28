import argparse
from pathlib import Path

from PIL import Image


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp"}


def collect_images(input_dir: Path) -> list[Path]:
    images = [path for path in input_dir.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS]
    return sorted(images, key=lambda path: path.name.lower())


def images_to_pdf(input_dir: Path, output_pdf: Path) -> Path:
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")

    image_paths = collect_images(input_dir)
    if not image_paths:
        raise ValueError(f"No image files found in: {input_dir}")

    converted: list[Image.Image] = []
    for image_path in image_paths:
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        converted.append(image)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    first, rest = converted[0], converted[1:]
    first.save(output_pdf, save_all=True, append_images=rest)

    for image in converted:
        image.close()

    return output_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Join images from folder into a single PDF.")
    parser.add_argument("--input-dir", required=True, type=Path, help="Folder with image files.")
    parser.add_argument("--output-pdf", required=True, type=Path, help="Output PDF path.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output = images_to_pdf(args.input_dir, args.output_pdf)
    print(f"PDF generated: {output}")
