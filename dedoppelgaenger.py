import argparse
import json
import os
import sys

from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
import rawpy
import imagehash
from tqdm import tqdm


RAW_EXTENSIONS = {".nef", ".cr2", ".arw", ".dng", ".orf", ".rw2"}


def process_images(paths, threads):
    hashes = {}

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(process_image, path): path for path in paths}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Hashing images"):
            result = future.result()
            if result:
                path, hash = result
                hashes[path] = hash

    return hashes


def process_image(path):
    ext = os.path.splitext(path)[1].lower()
    image = None
    try:
        if ext not in RAW_EXTENSIONS:
            image = Image.open(path)
        else:
            with rawpy.imread(path) as raw:
                rgb = raw.postprocess(use_camera_wb=True, half_size=True)
            image = Image.fromarray(rgb)

        image_hash = imagehash.phash(image)
        return path, image_hash
    except Exception:
        print(f"{path} - failed to read", file=sys.stderr)
        return None
    finally:
        if image:
            image.close()


def load_hashes(json_file):
    with open(json_file, "r") as f:
        raw = json.load(f)
    return {fname: imagehash.hex_to_hash(h) for fname, h in raw.items()}


def gather_hashes(inputs, threads):
    hashes = {}

    # Collect all image files and JSON inputs
    image_files = []
    for input in inputs:
        if os.path.isdir(input):
            for root, _, files in os.walk(input):
                for name in files:
                    image_files.append(os.path.join(root, name))
        elif input.endswith(".json"):
            hashes.update(load_hashes(input))
        else:
            print(f"Skipping unsupported input: {input}", file=sys.stderr)

    # Process image files
    if image_files:
        hashes.update(process_images(image_files, threads))

    return hashes


def find_doppelgaenger(reference_hashes, target_hashes, max_distance):
    doppelgaenger = {}
    candidates_count = len(reference_hashes) * len(target_hashes)
    progress_bar = tqdm(desc="Searching for matches", total=candidates_count)
    for reference_filename, reference_hash in reference_hashes.items():
        matches = []
        for filename, hash in target_hashes.items():
            progress_bar.update()
            dist = reference_hash - hash # Hamming distance
            if dist <= max_distance:
                matches.append(filename)
        if matches:
            doppelgaenger[reference_filename] = matches

    progress_bar.close()
    return doppelgaenger


def get_cli_parser():
    parser = argparse.ArgumentParser(description="Image hashing & duplicate finder tool.")
    parser.add_argument(
        "-o", "--output",
        help="Optional output file (JSON). If omitted, writes to stdout."
    )
    parser.add_argument(
        "--only-hash", action="store_true",
        help="Stop after hash calculation and output merged hashes"
    )
    parser.add_argument(
        "-t", "--threads", type=int, default=4,
        help="Number of worker threads (default: 4)"
    )
    parser.add_argument(
        "-d", "--distance", type=int, default=0,
        help="Max Hamming distance (default: 0 = exact match)"
    )
    parser.add_argument(
        "-r", "--reference", action="append", required=True,
        help="Reference JSON/folder (can be repeated)"
    )
    parser.add_argument(
        "inputs", nargs="+", help="Folders/JSON files to compare against"
    )
    return parser


def handle_output(content, dest):
    try: 
        out = open(dest, "w") if dest else sys.stdout
        json.dump(content, out)
    finally:
        if dest:
            out.close()


def output_hashes(reference_hashes, target_hashes, dest):
    merged = {}
    for k, v in reference_hashes.items():
        merged[k] = str(v)
    for k, v in target_hashes.items():
        merged[k] = str(v)

    handle_output(merged, dest)


def main():
    try:
        args = get_cli_parser().parse_args()

        reference_hashes = gather_hashes(args.reference, threads=args.threads)
        target_hashes    = gather_hashes(args.inputs, threads=args.threads)

        if args.only_hash:
            output_hashes(reference_hashes, target_hashes, args.output)
            return

        doppelgaenger = find_doppelgaenger(reference_hashes, target_hashes, args.distance)
        handle_output(doppelgaenger, args.output)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

