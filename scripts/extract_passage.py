#!/bin/python
import argparse
from html.parser import HTMLParser
from pathlib import Path


class PassageExtractor(HTMLParser):
    def __init__(self, passage: str):
        super().__init__()
        self.passage = passage
        self.collect_started = False
        self.collect_finished = False
        self.collected_data = ""

    def handle_starttag(self, tag, attrs):
        if tag == "tw-passagedata" and (("name", self.passage) in attrs):
            self.collect_started = True

    def handle_endtag(self, tag):
        if self.collect_started and tag == "tw-passagedata":
            self.collect_finished = True

    def handle_data(self, data):
        if self.collect_started:
            if not self.collected_data:
                # At first non-blank line, add passage header.
                if data.strip():
                    self.collected_data += f"/* PASSAGE: {self.passage} */\n" + data
            else:
                self.collected_data += data


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
        prog="extract_passage",
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
        required=True,
        help="Sugarcube story's HTML file",
    )
    parser.add_argument("-p", "--passage", type=str, required=True, help="Sugarcube passage to extract")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="stdout",
        help="Output Sugarcube passage file (.scp)",
    )
    args = parser.parse_args()

    parser = PassageExtractor(args.passage)
    with open(args.input, "r") as h_file:
        for h_line in h_file:
            parser.feed(h_line)
            if parser.collect_finished:
                break

    if args.output == "stdout":
        print(parser.collected_data)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(parser.collected_data)


if __name__ == "__main__":
    main()
