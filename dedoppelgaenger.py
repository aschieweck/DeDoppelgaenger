import argparse
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, NewType

import rawpy
import imagehash
import vptree
from PIL import Image
from tqdm import tqdm


class ImageHashTable:
    def __init__(self) -> None:
        self.__image_hashes = defaultdict(set)

    @property
    def hashes(self) -> dict[imagehash.ImageHash, set[Path]]:
        return self.__image_hashes

    def __getitem__(self, key: imagehash.ImageHash) -> set[Path]:
        return self.__image_hashes[key]

    def __setitem__(self, key: imagehash.ImageHash, values: set[Path]) -> None:
        self.__image_hashes[key] = values

    def keys(self) -> Iterable[imagehash.ImageHash]:
        return self.__image_hashes.keys()

    def items(self) -> Iterable[tuple[imagehash.ImageHash, set[Path]]]:
        return self.__image_hashes.items()

    def update(self, other: "ImageHashTable") -> None:
        for entry_hash, entry_files in other.__image_hashes.items():
            self.__image_hashes[entry_hash] |= entry_files

    def __str__(self) -> str:
        result = ""
        for image_hash, files in self.__image_hashes.items():
            result += f"{image_hash}\n"
            for f in files:
                result += f"    {f}\n"
        return result


DoppelgaengerList = NewType("DoppelgaengerList", dict[Path, set[Path]])


RAW_EXTENSIONS = {".nef", ".cr2", ".arw", ".dng", ".orf", ".rw2"}
EPSILON = 0.01


def hash_images(hashes: ImageHashTable, paths: Iterable[Path], threads: int) -> ImageHashTable:
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(hash_image, path): path for path in paths}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Hashing images"):
            result = future.result()
            if result:
                image_hash, path = result
                hashes[image_hash].add(path)

    return hashes


def hash_image(path: Path) -> tuple[imagehash.ImageHash, Path] | None:
    ext = path.suffix.lower()
    image = None
    try:
        if ext not in RAW_EXTENSIONS:
            image = Image.open(path)
        else:
            with rawpy.imread(path) as raw:
                rgb = raw.postprocess(use_camera_wb=True, half_size=True)
            image = Image.fromarray(rgb)

        image_hash = imagehash.phash(image)
        return image_hash, path
    except Exception:
        print(f"{path} - failed to read", file=sys.stderr)
        return None
    finally:
        if image:
            image.close()


def load_hashes(hashes: ImageHashTable, json_file: Path) -> ImageHashTable:
    with open(json_file, "r") as f:
        raw = json.load(f)

    for image_hash_str, files in raw.items():
        image_hash = imagehash.hex_to_hash(image_hash_str)
        files_set = {Path(f) for f in files}
        hashes[image_hash] = set(files_set)
    return hashes


def collect_hashes(paths: Iterable[Path], threads: int) -> ImageHashTable:
    hashes = ImageHashTable()

    # Collect all image files and JSON inputs
    json_files = []
    image_files = []
    for path in paths:
        items = path.rglob("*") if path.is_dir() else [path]

        for item in items:
            if not item.is_file():
                continue

            if item.suffix.lower() == ".json":
                json_files.append(item)
            else:
                image_files.append(item)

    # Process JSON files
    for file in json_files:
        load_hashes(hashes, file)

    # Process image files
    if image_files:
        hash_images(hashes, image_files, threads)

    return hashes


def find_doppelgaenger(
    reference_hashes: ImageHashTable, target_hashes: ImageHashTable, max_distance: int
) -> DoppelgaengerList:
    tree_hashes = list(target_hashes.keys())
    tree = tree = vptree.VPTree(tree_hashes, lambda a, b: b - a)

    doppelgaenger = DoppelgaengerList({})
    for reference_hash, reference_filenames in tqdm(reference_hashes.items(), desc="Searching for matches"):
        matches = tree.get_all_in_range(reference_hash, max_distance + EPSILON)

        if matches:
            all_matching_files = set()
            for _, matched_hash in matches:
                all_matching_files |= target_hashes[matched_hash]

            for reference_filename in reference_filenames:
                doppelgaenger[reference_filename] = all_matching_files

    return doppelgaenger


def get_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Image hashing & duplicate finder tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_parser = subparsers.add_parser("hash", help="Just calculate the hashes of the proviced files.")
    hash_parser.add_argument(
        "-o", "--output", type=Path, help="Optional output file (JSON). If omitted, writes to stdout."
    )
    hash_parser.add_argument("-t", "--threads", type=int, default=4, help="Number of worker threads (default: 4)")
    hash_parser.add_argument("inputs", nargs="+", type=Path, help="Folders/JSON files to compute the hashes for.")

    find_parser = subparsers.add_parser("find", help="Find Doppelgaenger.")
    find_parser.add_argument(
        "-o", "--output", type=Path, help="Optional output file (JSON). If omitted, writes to stdout."
    )
    find_parser.add_argument("-t", "--threads", type=int, default=4, help="Number of worker threads (default: 4)")
    find_parser.add_argument(
        "-d", "--distance", type=int, default=0, help="Max Hamming distance (default: 0 = exact match)"
    )
    find_parser.add_argument(
        "-r", "--reference", action="append", required=True, type=Path, help="Reference JSON/folder (can be repeated)"
    )
    find_parser.add_argument("inputs", nargs="+", type=Path, help="Folders/JSON files to compare against")

    return parser


def json_encoder(obj: imagehash.ImageHash | Path | set) -> str | list:
    if isinstance(obj, (imagehash.ImageHash, Path)):
        return str(obj)
    elif isinstance(obj, set):
        return list(obj)
    else:
        raise TypeError


def handle_output(content: Any, dest: Path | None) -> None:
    if isinstance(content, dict):
        content = {str(k): v for k, v in content.items()}

    if dest:
        with open(dest, "w") as out:
            json.dump(content, out, default=json_encoder)
    else:
        json.dump(content, sys.stdout, default=json_encoder)


def output_hashes(reference_hashes: ImageHashTable, target_hashes: ImageHashTable, dest: Path) -> None:
    merged = ImageHashTable()
    for k, v in reference_hashes.items():
        merged[k] = v
    for k, v in target_hashes.items():
        merged[k] |= v

    handle_output(merged.hashes, dest)


def main() -> None:
    try:
        parser = get_cli_parser()
        args = parser.parse_args()

        if args.command == "hash":
            target_hashes = collect_hashes(args.inputs, threads=args.threads)
            output_hashes(target_hashes, target_hashes, args.output)

        elif args.command == "find":
            reference_hashes = collect_hashes(args.reference, threads=args.threads)
            target_hashes = collect_hashes(args.inputs, threads=args.threads)

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
