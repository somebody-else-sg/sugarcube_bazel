#!/bin/python
import argparse
import html
import json
import re
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path


class OutputFormat(Enum):
    TWEE = 1
    SCP = 2
    PLAIN = 3


# Twee-3 specs require \-escaping []{}\ characters
_TWEE_ESCAPES = str.maketrans({"\\": r"\\", "[": r"\[", "]": r"\]", "{": r"\{", "}": r"\}"})


class PassageInfo:
    def __init__(self, name: str, tags: str, other_attrs: list):
        self.name = name
        self.tags = tags
        self.other_attrs = other_attrs
        self.content = ""

    def make_header(self, output_format):
        if output_format == OutputFormat.TWEE:
            self.content += f":: {self.name.translate(_TWEE_ESCAPES)}"
            if self.tags:
                self.content += " [" + self.tags.translate(_TWEE_ESCAPES) + "]"
            if self.other_attrs:
                self.content += " " + json.dumps({nm: val for nm, val in self.other_attrs})
            self.content += "\n"
        elif output_format == OutputFormat.SCP:
            self.content += f"/* PASSAGE: {self.name} */\n"


class PassageExtractor(HTMLParser):
    def __init__(self, output_format: str):
        super().__init__()
        self.passages = []
        self.in_passage = False
        self.extras = []
        self.in_extra = False
        self.story_started = False
        self.story_finished = False
        self.output_format = OutputFormat.PLAIN
        if output_format == "twee":
            self.output_format = OutputFormat.TWEE
        elif output_format == "scp":
            self.output_format = OutputFormat.SCP

    def handle_starttag(self, tag, attrs):
        if tag == "tw-storydata":
            self.story_title = [val for nm, val in attrs if nm == "name"][0]
            self.story_ifid = [val for nm, val in attrs if nm == "ifid"][0]
            self.story_started = True
            return
        if not self.story_started or self.story_finished:
            return
        if tag == "tw-passagedata":
            self.passages.append(
                PassageInfo(
                    [val for nm, val in attrs if nm == "name"][0],
                    [val for nm, val in attrs if nm == "tags"][0],
                    [(nm, val) for nm, val in attrs if (nm not in ["tags", "name", "pid"])],
                )
            )
            self.in_passage = True
        else:
            self.extras.append([tag, attrs, ""])
            self.in_extra = True

    def handle_endtag(self, tag):
        if tag == "tw-storydata":
            self.story_finished = True
            return
        if not self.story_started or self.story_finished:
            return
        if tag == "tw-passagedata":
            self.in_passage = False
        else:
            self.in_extra = False

    def handle_data(self, data):
        if not self.story_started or self.story_finished:
            return
        if self.in_passage:
            if not self.passages[-1].content:
                # At first non-blank line, add passage header.
                if not data.strip():
                    return
                self.passages[-1].make_header(self.output_format)
            self.passages[-1].content += data
        elif self.in_extra:
            self.extras[-1][2] += data


def require_file_exists(filepath):
    """Verifies that the provided path points to a file that actually exists."""
    path = Path(filepath)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"'{filepath}' does not exist.")
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"'{filepath}' is a directory, not a file.")
    return path


def require_dir_exists(filepath):
    """Verifies that the provided path points to a directory that actually exists."""
    path = Path(filepath)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"'{filepath}' does not exist.")
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"'{filepath}' is not a directory!")
    return path


_CAMEL_CASE_WITH_NUM = re.compile(r"(?<!^)([^_0-9])(?=[A-Z0-9])")


class FileNameMaker:
    def __init__(self, case_style: str, output_format: OutputFormat):
        if case_style == "snake_case":
            self.style = 1
        elif case_style == "CamelCase":
            self.style = 2
        else:
            self.style = 3
        self.default_ext = ""
        if output_format == OutputFormat.TWEE:
            self.default_ext = ".tw"
        elif output_format == OutputFormat.SCP:
            self.default_ext = ".scp"

    def _to_snake_case(self, cleaner_name: str):
        return _CAMEL_CASE_WITH_NUM.sub(r"\1_", cleaner_name).lower()

    def _to_camel_case(self, cleaner_name: str):
        components = re.split(r"_\s", cleaner_name)
        return components[0][0].upper() + components[0][1:] + "".join((x[0].upper() + x[1:]) for x in components[1:])

    def to_file_name(self, passage_name: str, extension: str = "default"):
        forbidden_chars = [",", "!", "?", "*", ">", "<", "|", "(", ")", "{", "}", "[", "]", "/"]
        space_like_chars = [" ", ".", "-"] if self.style == 1 else []
        bad_chars_mapping = str.maketrans({c: "_" for c in space_like_chars + forbidden_chars})
        cleaner_name = passage_name.translate(bad_chars_mapping)
        if extension == "default":
            extension = self.default_ext
        if self.style == 1:
            return self._to_snake_case(cleaner_name) + extension
        elif self.style == 2:
            return self._to_camel_case(cleaner_name) + extension
        else:
            return cleaner_name + extension


def main():
    parser = argparse.ArgumentParser(
        prog="extract_story",
        description="Extract all Sugarcube passages and other html elements from a complete "
        + "(compiled) html file. The script looks at each passage name and creates a file with "
        + "a corresponding name (e.g., lower-case, spaces and dots replaced with underscores). "
        + "Then, it extracts its body into a sugarcube passage file (.tw/.scp) containing the "
        + "unescaped contents of the passage. The script can also be invoked from bazel, as "
        + "'bazel run //scripts:extract_story', but note that it will require absolute paths "
        + "for the input and output files.",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=require_file_exists,
        required=True,
        help="Sugarcube story's HTML file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=require_dir_exists,
        required=True,
        help="Output directory for the Sugarcube passage files (.tw/.scp)",
    )
    parser.add_argument("-f", "--format", type=str, default="twee", help="Output format: 'twee', 'scp', or 'plain'")
    parser.add_argument("-b", "--build_file", action="store_true", help="Generate a BUILD.bazel file")
    parser.add_argument(
        "-a",
        "--assets_dir",
        nargs="*",
        default=[],
        help="Top-level asset directories (e.g. 'images'), as relative paths to the destination, "
        + "used for the build file generation",
    )
    parser.add_argument(
        "-c",
        "--filename_case",
        choices=["snake_case", "CamelCase", "identity"],
        default="snake_case",
        help="Case style to use for when creating file names",
    )
    args = parser.parse_args()

    extractor = PassageExtractor(args.format)
    with open(args.input, "r", encoding="utf-8") as h_file:
        for h_line in h_file:
            extractor.feed(h_line)
            if extractor.story_finished:
                break

    scp_files_by_tags = {}
    user_styles = []
    user_scripts = []
    fn_maker = FileNameMaker(args.filename_case, extractor.output_format)

    for p in extractor.passages:
        p_fname = fn_maker.to_file_name(p.name)
        if p.tags not in scp_files_by_tags:
            scp_files_by_tags[p.tags] = [p_fname]
        else:
            scp_files_by_tags[p.tags].append(p_fname)
        with open(args.output / p_fname, "w", encoding="utf-8") as f:
            f.write(p.content)

    for p in extractor.extras:
        extra_id = [val for nm, val in p[1] if nm == "id"][0]
        p_fname = fn_maker.to_file_name(extra_id, extension=".html")
        if p[0] == "style":
            user_styles.append(p_fname)
        else:
            user_scripts.append(p_fname)
        with open(args.output / p_fname, "w", encoding="utf-8") as f:
            f.write("<{} {}>".format(p[0], " ".join([f'{nm}="{html.escape(val)}"' for nm, val in p[1]])))
            f.write(p[2])
            f.write("</{}>".format(p[0]))

    if args.build_file:
        with open(args.output / "BUILD.bazel", "w", encoding="utf-8") as f:
            f.write("load('@sugarcube_bazel//:defs.bzl', 'sugarcube_library', 'sugarcube_story')\n")
            f.write(
                R"""
filegroup(
    name = "user_scripts",
    srcs = ["""
                + ", ".join([f'\n        "{s}"' for s in user_scripts])
                + R"""
    ],
)

filegroup(
    name = "user_stylesheet",
    srcs = ["""
                + ",".join([f'\n        "{s}"' for s in user_styles])
                + R"""
    ],
)
"""
            )
            if args.assets_dir:
                f.write(
                    R"""
filegroup(
    name = "assets",
    srcs = [] + """
                    + " + ".join([f'glob(["{s}/**"], allow_empty=True)' for s in args.assets_dir])
                    + R""",
)
"""
                )

            deps = []
            for tags, files in scp_files_by_tags.items():
                target_name = "_".join(tags.split(" ")) if tags else "passages"
                deps.append(f'\n        ":{target_name}"')
                f.write(
                    R"""
sugarcube_library(
    name = """
                    + f'"{target_name}"'
                    + (
                        R""",
    data = [":assets"]"""
                        if (target_name == "passages" and args.assets_dir)
                        else ""
                    )
                    + R""",
    tags = ["""
                    + ",".join([f'\n        "{s}"' for s in tags.split(" ")])
                    + R"""
    ],
    srcs = ["""
                    + ",".join([f'\n        "{s}"' for s in files])
                    + R"""
    ],
)
"""
                )
            f.write(
                R"""
sugarcube_story(
    name = """
                + f'"{FileNameMaker("snake_case", OutputFormat.PLAIN).to_file_name(extractor.story_title)}"'
                + R""",
    title = """
                + f'"{extractor.story_title}"'
                + R""",
    ifid = """
                + f'"{extractor.story_ifid}"'
                + R""",
    user_stylesheet = [":user_stylesheet"],
    user_script = [":user_scripts"],
    deps = ["""
                + ",".join(deps)
                + R"""
    ],
)
"""
            )


if __name__ == "__main__":
    main()
