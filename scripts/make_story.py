#!/bin/python
import argparse
import json
import re
import sys
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path


class PassageNameChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.passages = dict()
        self.current_filename = ""

    def handle_starttag(self, tag, attrs):
        if tag == "tw-passagedata":
            for attr_nm, attr_data in attrs:
                if attr_nm == "name":
                    passage_name = unescape(attr_data)
                    if passage_name in self.passages:
                        raise SyntaxError(
                            "Duplicate passage names found! Passage '{}' in '{}' was already defined in '{}'.".format(
                                passage_name, self.current_filename, self.passages[passage_name]
                            )
                        )
                    self.passages[passage_name] = self.current_filename
                    break


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
        prog="make_story",
        description="Compile an html file containing a Sugarcube story from a format "
        + "file and a set of html files containing any number of <tw-passagedata> "
        + "elements for Sugarcube passages. This assembles the Sugarcube story. "
        + "Additional information must be provided such at the title and IFID. "
        + "Moreover, passage names are checked duplicates.",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=require_file_exists,
        nargs="+",
        help="Sugarcube passages in HTML files. Each containing one or more <tw-passagedata> elements",
    )
    parser.add_argument(
        "-x",
        "--extra_html",
        type=require_file_exists,
        nargs="*",
        default=[],
        help="Extra HTML files to concatenate next to the passage elements (e.g., user scripts or styles)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="Output combined html file with all passages concatenated together",
    )
    parser.add_argument(
        "-t",
        "--title",
        type=str,
        required=True,
        help="The title of the story as it will appear in places such as the title-bar of the browser's tab.",
    )
    parser.add_argument(
        "-n",
        "--ifid",
        type=str,
        required=True,
        help="The IFID (Interactive Fiction IDentifier) number assigned to this SugarCube game.",
    )
    parser.add_argument(
        "-f",
        "--format_file",
        type=require_file_exists,
        required=True,
        help="The SugarCube format file.",
    )

    args = parser.parse_args()

    js_embedded_json = re.compile(rf"^\s*window\.storyFormat\((.*)\);\s*$", re.IGNORECASE)
    format_data = {}
    with open(args.format_file, "r", encoding="utf-8") as f_in:
        content = f_in.read()
        if jm := js_embedded_json.fullmatch(content):
            try:
                format_data = json.loads(jm.group(1))
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print("ERROR: Sugarcube format file is ill formed!", file=sys.stderr)
            sys.exit(1)

    name_marker = "{{STORY_NAME}}"
    data_marker = "{{STORY_DATA}}"
    checker = PassageNameChecker()
    try:
        with open(args.output, "w", encoding="utf-8") as f_out:
            begin_i = 0
            data_i = 0
            name_i = 0
            while True:
                if name_i <= begin_i:
                    name_i = format_data["source"].find(name_marker, begin_i)
                    if name_i < 0:
                        name_i = len(format_data["source"])
                if data_i <= begin_i:
                    data_i = format_data["source"].find(data_marker, begin_i)
                    if data_i < 0:
                        data_i = len(format_data["source"])

                if name_i < data_i:
                    f_out.write(format_data["source"][begin_i:name_i])
                    f_out.write(escape(args.title))
                    begin_i = name_i + len(name_marker)
                    continue

                f_out.write(format_data["source"][begin_i:data_i])
                if data_i == len(format_data["source"]):
                    break

                if checker.passages:
                    print("ERROR: Sugarcube format file has multiple {{STORY_DATA}} template tags!", file=sys.stderr)
                    sys.exit(1)

                f_out.write(
                    '<tw-storydata name="{}" startnode="1" ifid="{}" format="{}" format-version="{}" hidden>\n'.format(
                        escape(args.title), escape(args.ifid), format_data["name"], format_data["version"]
                    )
                )

                for filepath_in in args.extra_html:
                    with open(filepath_in, "r") as f_in:
                        for f_line in f_in:
                            f_out.write(f_line)
                for filepath_in in args.input:
                    checker.current_filename = filepath_in
                    with open(filepath_in, "r") as f_in:
                        for f_line in f_in:
                            checker.feed(f_line)
                            f_out.write(f_line)

                f_out.write("</tw-storydata>\n")
                begin_i = data_i + len(data_marker)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
