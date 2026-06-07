#!/bin/python
import argparse
import html
import re
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
        prog="scp_to_html",
        description="Extract Sugarcube passage from a complete (compiled) html file. "
        + "The script looks for the passage with the name given with the -p,--passage argument. "
        + "Then, it extracts its body into a sugarcube passage file (.scp) containing the "
        + "unescaped contents of the passage.  The script can also be invoked from bazel, as "
        + "'bazel run //scripts:extract_passage', but note that it will require absolute paths "
        + "for the input and output files.",
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
        type=str,
        nargs="*",
        default=[],
        help="Tags attributes to put on the generated tw-passagedata elements",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="Output HTML file (.html) containing all the tw-passagedata elements",
    )
    args = parser.parse_args()

    passage_header_pattern = re.compile(rf"/\*\s*PASSAGE:\s*(\S.*\S)\s*\*/", re.IGNORECASE)
    tags_str = html.escape(" ".join(args.tags))

    try:
        with open(args.output, "w", encoding="utf-8") as f_out:
            for filepath_in in args.input:
                current_passage = None
                with open(filepath_in, "r") as f_in:
                    f_lineno = 0
                    for f_line in f_in:
                        f_lineno += 1
                        if not current_passage:
                            if not f_line.strip():
                                # Ignore blank lines at the start.
                                continue
                            elif pm := passage_header_pattern.search(f_line):
                                current_passage = html.escape(pm.group(1))
                                if current_passage == "Start":
                                    f_out.write('<tw-passagedata name="Start" pid="1" tags="{}">'.format(tags_str))
                                else:
                                    f_out.write(
                                        '<tw-passagedata name="{}" tags="{}">'.format(current_passage, tags_str)
                                    )
                                f_line = f_line[pm.end() :]
                                if not f_line.strip():
                                    # Ignore blank line or break after passage header.
                                    continue
                            else:
                                raise SyntaxError(
                                    "Passage files must start with '/* PASSAGE: [some name] */'!",
                                    (filepath_in, f_lineno, 1, f_line),
                                )
                        f_out.write(html.escape(f_line, quote=False))
                if current_passage:
                    f_out.write("</tw-passagedata>")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
