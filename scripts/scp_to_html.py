#!/bin/python
import argparse
import html
import json
import re
import sys
from enum import Enum
from pathlib import Path


class InputFormat(Enum):
    TWEE = 1
    SCP = 2
    PLAIN = 3


def _twee_unescape(nm: str):
    return re.sub(r"\\(.)", "\1", nm)


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
        description="Convert sugarcube passage files (.tw/.scp) into a partial html file "
        + "containing the <tw-passagedata> elements from those passage files.",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=require_file_exists,
        nargs="+",
        help="Sugarcube passage files (.tw/.scp)",
    )
    parser.add_argument(
        "-t",
        "--tags",
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

    passage_header_pattern = re.compile(r"/\*\s*PASSAGE:\s*(\S.*\S)\s*\*/", re.IGNORECASE)
    twee_header_pattern = re.compile(r"^::\s*(\S.*\S)\n?$")
    twee_name_tags_pattern = re.compile(r"^(.*?[^\\])\[(.*?[^\\])\]\s*(.*)?$")
    twee_name_notags_pattern = re.compile(r"^(.*?[^\\])(\{.*)?$")
    tags_str = html.escape(" ".join(args.tags))

    try:
        with open(args.output, "w", encoding="utf-8") as f_out:

            def start_passage(passage_name: str, tail_attr: str, html_block: str):
                if html_block == "script":
                    f_out.write('<script role="script" type="text/twine-javascript">\n')
                    return
                if html_block == "style":
                    f_out.write('<style role="stylesheet" type="text/twine-css">\n')
                    return
                if passage_name in ["StoryTitle", "StoryData"]:
                    print(
                        f"ERROR: Special passage '{passage_name}' is not used by sugarcube_bazel! "
                        + "This information is specified in build configurations.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                if passage_name.capitalize() == "Start":
                    f_out.write('<tw-passagedata name="Start" pid="1" {}>'.format(tail_attr))
                else:
                    f_out.write('<tw-passagedata name="{}" {}>'.format(passage_name, tail_attr))

            def close_passage(html_block: str):
                f_out.write(f"</{html_block}>\n")

            for filepath_in in args.input:
                current_passage = None
                current_html_block = None
                input_format = InputFormat.PLAIN
                with open(filepath_in, "r", encoding="utf-8") as f_in:
                    f_lineno = 0
                    for f_line in f_in:
                        f_lineno += 1
                        if not current_passage and not f_line.strip():
                            # Ignore blank lines at the start.
                            continue
                        if not current_passage or input_format == InputFormat.TWEE:
                            if tm := twee_header_pattern.fullmatch(f_line):
                                if current_passage:
                                    close_passage(current_html_block)
                                ttm = twee_name_tags_pattern.fullmatch(tm.group(1))
                                tnm = twee_name_notags_pattern.fullmatch(tm.group(1))
                                input_format = InputFormat.TWEE
                                if not ttm or (len(tnm.group(1)) < len(ttm.group(1))):
                                    current_passage = html.escape(_twee_unescape(tnm.group(1).strip()))
                                    current_html_block = "tw-passagedata"
                                    extra_attrs = json.loads(tnm.group(2)) if tnm.group(2) else {}
                                    current_tags = tags_str
                                    if "widget" in args.tags:
                                        print(
                                            f"ERROR: Passage '{html.unescape(current_passage)}' has been built within a "
                                            + "widget build target, but the twee file header does not contain that tag!",
                                            file=sys.stderr,
                                        )
                                        sys.exit(1)
                                else:
                                    current_passage = html.escape(_twee_unescape(ttm.group(1).strip()))
                                    extra_attrs = json.loads(ttm.group(3)) if ttm.group(3) else {}
                                    embedded_tags = _twee_unescape(ttm.group(2)).split(" ")
                                    if "widget" in embedded_tags and "widget" not in args.tags:
                                        print(
                                            f"ERROR: Passage '{html.unescape(current_passage)}' has 'widget' tag embedded "
                                            + "in its twee header, but the build configurations for this target does "
                                            + "not contain that tag. sugarcube_bazel needs to know about widget passages. "
                                            + "Please put those passages in separate targets and marked with that tag.",
                                            file=sys.stderr,
                                        )
                                        sys.exit(1)
                                    elif "widget" in args.tags and "widget" not in embedded_tags:
                                        print(
                                            f"ERROR: Passage '{html.unescape(current_passage)}' has been built within a "
                                            + "widget build target, but the twee file header does not contain that tag!",
                                            file=sys.stderr,
                                        )
                                        sys.exit(1)
                                    elif "script" in embedded_tags:
                                        current_html_block = "script"
                                    elif "stylesheet" in embedded_tags:
                                        current_html_block = "style"
                                    else:
                                        current_html_block = "tw-passagedata"
                                        current_tags = html.escape(" ".join(set(args.tags + embedded_tags)))

                                tail_str = ""
                                if current_html_block == "tw-passagedata":
                                    tail_str += 'tags="{}"'.format(current_tags)
                                tail_str += " ".join([f' {nm}="{html.escape(val)}"' for nm, val in extra_attrs.items()])
                                start_passage(current_passage, tail_str, current_html_block)
                                # Full-match of passage header, don't output this line.
                                continue
                        if not current_passage:
                            if pm := passage_header_pattern.search(f_line):
                                current_passage = html.escape(pm.group(1))
                                current_html_block = "tw-passagedata"
                                input_format = InputFormat.SCP
                                start_passage(current_passage, 'tags="{}"'.format(tags_str), current_html_block)
                                f_line = f_line[pm.end() :]
                                if not f_line.strip():
                                    # Ignore blank line or break after passage header.
                                    continue
                            else:
                                current_passage = html.escape(filepath_in.stem)
                                current_html_block = "tw-passagedata"
                                input_format = InputFormat.PLAIN
                                start_passage(current_passage, 'tags="{}"'.format(tags_str), current_html_block)
                        if current_html_block not in ["style", "script"]:
                            f_out.write(html.escape(f_line, quote=False))
                        else:
                            f_out.write(f_line)
                if current_passage:
                    close_passage(current_html_block)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
