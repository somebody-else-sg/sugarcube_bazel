#!/bin/python
import argparse
import re
import sys
from pathlib import Path


def require_file_exists(filepath):
    """Verifies that the provided path points to a file that actually exists."""
    path = Path(filepath)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"The file '{filepath}' does not exist.")
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"'{filepath}' is a directory, not a file.")
    return path


def main():
    parser = argparse.ArgumentParser(
        prog="scp_to_tw",
        description="Convert sugarcube passage files (.scp) into twee files (.tw).",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=require_file_exists,
        nargs="+",
        help="Sugarcube passage files (.scp)",
    )
    parser.add_argument(
        "-t",
        "--tags",
        nargs="*",
        default=[],
        help="Tags attributes to put on the generated tw files",
    )
    args = parser.parse_args()

    passage_header_pattern = re.compile(r"/\*\s*PASSAGE:\s*(\S.*\S)\s*\*/", re.IGNORECASE)
    tags_str = " ".join(args.tags)

    try:
        for filepath_in in args.input:
            current_passage = None
            if filepath_in.suffix in [".tw", ".twee"]:
                continue
            filepath_out = filepath_in.with_suffix(".tw")
            with open(filepath_out, "w", encoding="utf-8") as f_out:
                with open(filepath_in, "r", encoding="utf-8") as f_in:
                    for f_line in f_in:
                        if not current_passage and not f_line.strip():
                            # Ignore blank lines at the start.
                            continue
                        if not current_passage:
                            if pm := passage_header_pattern.search(f_line):
                                current_passage = pm.group(1)
                                f_out.write(":: {}{}\n".format(current_passage, f" [{tags_str}]" if tags_str else ""))
                                f_line = f_line[pm.end() :]
                            else:
                                current_passage = filepath_in.stem
                                f_out.write(":: {}{}\n".format(current_passage, f" [{tags_str}]" if tags_str else ""))
                            if not f_line.strip():
                                # Ignore blank line or break after passage header.
                                continue
                        f_out.write(f_line)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
