#!/bin/python
import argparse
import json
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path


class OutputFormat(Enum):
    TWEE = 1
    SCP = 2
    PLAIN = 3


# Twee-3 specs require \-escaping []{}\ characters
_TWEE_ESCAPES = str.maketrans({"\\": r"\\", "[": r"\[", "]": r"\]", "{": r"\{", "}": r"\}"})


class PassageExtractor(HTMLParser):
    def __init__(self, passage: str, output_format: str):
        super().__init__()
        self.passage = passage
        self.passage_tags = ""
        self.passage_other_attrs = []
        self.collect_started = False
        self.collect_finished = False
        self.collected_data = ""
        self.output_format = OutputFormat.PLAIN
        if output_format == "twee":
            self.output_format = OutputFormat.TWEE
        elif output_format == "scp":
            self.output_format = OutputFormat.SCP

    def handle_starttag(self, tag, attrs):
        if tag == "tw-passagedata" and (("name", self.passage) in attrs):
            self.collect_started = True
            tags_fields = [val for nm, val in attrs if nm == "tags"]
            if tags_fields:
                self.passage_tags = " ".join(tags_fields)
            self.passage_other_attrs = [(nm, val) for nm, val in attrs if (nm not in ["tags", "name", "pid"])]

    def handle_endtag(self, tag):
        if self.collect_started and tag == "tw-passagedata":
            self.collect_finished = True

    def handle_data(self, data):
        if self.collect_started:
            if not self.collected_data:
                # At first non-blank line, add passage header.
                if not data.strip():
                    return
                if self.output_format == OutputFormat.TWEE:
                    self.collected_data += f":: {self.passage.translate(_TWEE_ESCAPES)}"
                    if self.passage_tags:
                        self.collected_data += " [" + self.passage_tags.translate(_TWEE_ESCAPES) + "]"
                    if self.passage_other_attrs:
                        self.collected_data += " " + json.dumps({nm: val for nm, val in self.passage_other_attrs})
                    self.collected_data += "\n"
                elif self.output_format == OutputFormat.SCP:
                    self.collected_data += f"/* PASSAGE: {self.passage} */\n"
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
    parser.add_argument("-f", "--format", type=str, default="twee", help="Output format: 'twee', 'scp', or 'plain'")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="stdout",
        help="Output Sugarcube passage file (.tw)",
    )
    args = parser.parse_args()

    extractor = PassageExtractor(args.passage, args.format)
    with open(args.input, "r", encoding="utf-8") as h_file:
        for h_line in h_file:
            extractor.feed(h_line)
            if extractor.collect_finished:
                break

    if args.output == "stdout":
        print(extractor.collected_data)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(extractor.collected_data)


if __name__ == "__main__":
    main()
