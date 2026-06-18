#!/bin/python
import argparse
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Tuple, Dict


class PassageInfo:
    def __init__(self, name: str, tags: List[str], filepath: str, line_num: int):
        self.name = name
        self.tags = tags
        self.filepath = filepath
        self.line_num = line_num


def check_duplicates(passages):
    sorted_passages = sorted(passages, key=lambda x: x.name)
    error_list: List[Dict] = []
    for i in range(len(sorted_passages) - 1):
        if sorted_passages[i].name == sorted_passages[i + 1].name:
            error_list.append(
                {
                    "location": "{}:{}:0: '{}'".format(
                        sorted_passages[i + 1].filepath, sorted_passages[i + 1].line_num, sorted_passages[i].name
                    ),
                    "message": "Passage name '{}' appears multiple times!\n\tAt {}:{}\n\tAt {}:{}".format(
                        sorted_passages[i].name,
                        sorted_passages[i].filepath,
                        sorted_passages[i].line_num,
                        sorted_passages[i + 1].filepath,
                        sorted_passages[i + 1].line_num,
                    ),
                }
            )
    return error_list


class PassageExtractor(HTMLParser):
    def __init__(self, parent, filepath: str):
        super().__init__()
        self.parent = parent
        self.filepath = filepath
        self.passages = []
        self.in_passage = False
        self.story_started = False
        self.story_finished = False

    def handle_starttag(self, tag, attrs):
        if tag == "tw-storydata":
            self.story_started = True
            return
        if not self.story_started or self.story_finished:
            return
        if tag == "tw-passagedata":
            tags_vals = [val for nm, val in attrs if nm == "tags"]
            if tags_vals:
                tags_val = tags_vals[0]
            else:
                tags_val = ""
            self.parent.start_passage(
                [val for nm, val in attrs if nm == "name"][0],
                tags_val.split(" "),
                self.filepath,
                self.getpos()[0],
                (self.parent.extract_widgets and ("widget" not in tags_val)),
            )
            self.in_passage = True

    def handle_endtag(self, tag):
        if tag == "tw-storydata":
            self.story_finished = True
            return
        if not self.story_started or self.story_finished:
            return
        if tag == "tw-passagedata":
            self.parent.finish_passage()
            self.in_passage = False

    def handle_data(self, data):
        if not self.story_started or self.story_finished:
            return
        if self.in_passage:
            self.parent.process_line(data)


class SugarcubeMacroCall:
    def __init__(self, keyword: str, line: int, col: int, is_open: bool):
        self.keyword = keyword
        self.line = line
        self.col = col
        self.is_open = is_open


class SugarcubeMacroDef:
    def __init__(
        self,
        keyword: str,
        tags: List[str],
        is_container: bool,
        deprecated_for: str,
        user_path: str,
        user_line: int,
    ):
        self.keyword = keyword
        self.tags = tags
        self.is_container = is_container
        self.deprecated_for = deprecated_for
        self.user_path = user_path
        self.user_line = user_line


def _serialize_macro_defs(obj):
    if isinstance(obj, SugarcubeMacroDef):
        return obj.__dict__
    raise TypeError(f"Type {type(obj)} not serializable")


def _twee_unescape(nm: str):
    return re.sub(r"\\(.)", "\1", nm)


class SugarcubeMacroChecker:
    def __init__(self, macros_files: List[Path], extract_widgets: bool, ignore_unknown: bool):
        self.macros = {}
        for filepath in macros_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.macros.update(
                        {
                            m_name: SugarcubeMacroDef(
                                m_name,
                                m_fields.get("tags", []),
                                m_fields.get("is_container", False),
                                m_fields.get("deprecated_for", ""),
                                m_fields.get("user_path", str(filepath)),
                                m_fields.get("user_line", 0),
                            )
                            for m_name, m_fields in data.items()
                        }
                    )
                else:
                    raise ValueError(f"Expected dict, got {type(data)}")
            except FileNotFoundError:
                raise FileNotFoundError(f"Macros file not found: {filepath}")
        self.macro_tags = {}
        for m_name, m_fields in self.macros.items():
            for tag in m_fields.tags:
                if tag not in self.macro_tags:
                    self.macro_tags[tag] = [m_name]
                else:
                    self.macro_tags[tag].append(m_name)
        self.user_widgets = {}
        self.extract_widgets = extract_widgets
        self.ignore_unknown = ignore_unknown
        self.passages = []

        # Regex for opening tag: <<keyword args..>>
        self._macro_call_pattern = re.compile(
            # This is a tricky regex. The first part with the capture group is trivial, just
            # capturing the first legal identifier for the macro, i.e., doesn't start with '/',
            # and doesn't contain spaces or '<' or '>', as specified in sugarcube docs.
            # The second part is tricky because we want to get to the next '>>', but there
            # could be quoted strings, and isolated '>' characters. So, we match quoted strings
            # all together (accepting whatever inside) and we only match isolated '>' characters
            # or any non-'>' characters.
            r"""<<\s*([^\s<>]+)(?:"[^"]*"|'[^']*'|[^>]|[^>]>[^>])*>>""",
            re.IGNORECASE,
        )

        # Regex for user-defined widget: <<widget widgetName[ container]>>
        self._widget_pattern = re.compile(rf"<<\s*widget\s+([^\s<>]+)\s*([^\s<>]*)\s*>>", re.IGNORECASE)

        self._comment_pattern = re.compile(rf"(/\*|\*/|/%|%/|<!--|-->)", re.IGNORECASE)

        self._scp_header_pattern = re.compile(r"/\*\s*PASSAGE:\s*(\S.*\S)\s*\*/", re.IGNORECASE)
        self._twee_header_pattern = re.compile(r"^::\s*(\S.*\S)\n?$")
        self._twee_name_tags_pattern = re.compile(r"^(.*?[^\\])\[(.*?[^\\])\]\s*(.*)?$")
        self._twee_name_notags_pattern = re.compile(r"^(.*?[^\\])(\{.*)?$")

        self._cur_filepath = ""
        self._cur_line_num = 0
        self._in_comment = [False, False, False]
        self._macro_calls = []
        self._macro_call_started = ""
        self._macro_call_started_at = -1
        self._ignored_passage = False

        self._skip_ignored_passage = False

        self.error_list: List[Dict] = []

    def _parse_user_widget(self, widget_call: str):
        wm = self._widget_pattern.search(widget_call)
        w_name = wm.group(1).strip(' "')
        if w_name in self.macros:
            self.error_list.append(
                {
                    "location": "{}:{}:0: '{}'".format(self._cur_filepath, self._cur_line_num, self.passages[-1].name),
                    "message": "User-defined widget name '{}' is already a built-in macro defined in '{}'!".format(
                        w_name, self.macros[w_name].user_path
                    ),
                }
            )
            return
        if w_name in self.user_widgets:
            self.error_list.append(
                {
                    "location": "{}:{}:0: '{}'".format(self._cur_filepath, line_num, self.passages[-1].name),
                    "message": "User-defined widget name '{}' was already defined at '{}:{}'!".format(
                        w_name,
                        self.user_widgets[w_name].user_path,
                        self.user_widgets[wm.group(1)].user_line,
                    ),
                }
            )
            return
        self.user_widgets.update(
            {
                w_name: SugarcubeMacroDef(
                    w_name,
                    [],
                    (wm.group(2).strip() == "container"),
                    "",
                    self._cur_filepath,
                    self._cur_line_num,
                )
            }
        )

    def _find_macro(self, kw: str):
        if kw in self.macros:
            return self.macros[kw]
        elif kw in self.user_widgets:
            return self.user_widgets[kw]
        else:
            return None

    def start_passage(self, name: str, tags: List[str], filepath: str, start_line_num: int, ignored_passage: bool):
        if not ignored_passage:
            self.passages.append(PassageInfo(name, tags, filepath, start_line_num))
        self._cur_filepath = filepath
        self._cur_line_num = start_line_num
        self._in_comment = [False, False, False]
        self._macro_calls = []
        self._macro_call_started = ""
        self._macro_call_started_at = -1
        self._ignored_passage = ignored_passage

    def process_line(self, line: str):
        self._cur_line_num += 1
        if self._skip_ignored_passage and self._ignored_passage:
            # We completely skip over ignored passages if we don't even
            # need to look for a passage header (e.g., ":: MyPassage [tag1 tag2]").
            return
        uncomment_ln = ""
        col_offsets = [(0, 0)]
        last_valid_col = 0
        for comment_match in self._comment_pattern.finditer(line):
            if comment_match.group(1) in ["/*", "/%", "<!--"]:
                if not any(self._in_comment):
                    uncomment_ln += line[last_valid_col : comment_match.start()]
                    last_valid_col = comment_match.start()
                self._in_comment[["/*", "/%", "<!--"].index(comment_match.group(1))] = True
                if pm := self._scp_header_pattern.search(line[comment_match.start() :]):
                    self.finish_passage()
                    self.start_passage(
                        pm.group(1),
                        ["widget"] if self.extract_widgets else [],
                        self._cur_filepath,
                        self._cur_line_num,
                        False,
                    )
            elif comment_match.group(1) in ["*/", "%/", "-->"]:
                self._in_comment[["*/", "%/", "-->"].index(comment_match.group(1))] = False
                if not any(self._in_comment):
                    next_valid_col = comment_match.start() + len(comment_match.group(1))
                    col_offsets.append(
                        (
                            len(uncomment_ln),
                            col_offsets[-1][1] + next_valid_col - last_valid_col,
                        )
                    )
                    last_valid_col = next_valid_col
        if not any(self._in_comment):
            uncomment_ln += line[last_valid_col:]

        def map_to_orig_col(col):
            last_offset = 0
            for col_start, offset in col_offsets:
                if col >= col_start:
                    last_offset = offset
                else:
                    break
            return col + last_offset

        if tm := self._twee_header_pattern.fullmatch(uncomment_ln):
            self.finish_passage()

            ttm = self._twee_name_tags_pattern.fullmatch(tm.group(1))
            tnm = self._twee_name_notags_pattern.fullmatch(tm.group(1))
            if not ttm or (len(tnm.group(1)) < len(ttm.group(1))):
                current_passage = _twee_unescape(tnm.group(1).strip())
                current_tags = []
            else:
                current_passage = _twee_unescape(ttm.group(1).strip())
                current_tags = _twee_unescape(ttm.group(2)).split(" ")
            if any(t in ["script", "stylesheet"] for t in current_tags) or (
                self.extract_widgets and "widget" not in current_tags
            ):
                ignored_passage = True
            else:
                ignored_passage = False
            self.start_passage(current_passage, current_tags, self._cur_filepath, self._cur_line_num, ignored_passage)
            return

        if self._ignored_passage:
            return

        uncomment_ln_offset = 0

        if self._macro_call_started:
            pos_close = uncomment_ln.find(">>")
            pos_open = uncomment_ln.find("<<")
            if pos_open >= 0 and (pos_close < 0 or pos_open < pos_close):
                self.error_list.append(
                    {
                        "location": "{}:{}:0: '{}'".format(
                            self._cur_filepath, self._macro_call_started_at, self.passages[-1].name
                        ),
                        "message": "Cannot find a closing '>>' for macro starting with '{}'! "
                        + "Reached the start of another macro call.".format(
                            self._macro_call_started[: self._macro_call_started.find("\n")]
                        ),
                    }
                )
                self._macro_call_started = ""
                self._macro_call_started_at = -1
                uncomment_ln_offset = pos_open
            elif pos_close >= 0:
                uncomment_ln = self._macro_call_started + uncomment_ln
                for _, offset in col_offsets:
                    offset -= len(self._macro_call_started)
                self._macro_call_started = ""
            else:
                # Skip regex matching if there isn't even a '>>' yet
                # The regex for macro call is very expensive for long calls
                self._macro_call_started += uncomment_ln
                return

        while uncomment_ln_offset < len(uncomment_ln):
            if call_match := self._macro_call_pattern.search(uncomment_ln, pos=uncomment_ln_offset):
                self._macro_call_started = ""
                self._macro_call_started_at = -1
                uncomment_ln_offset = call_match.end()
                if call_match.group(1).startswith("/"):
                    call_name = call_match.group(1).removeprefix("/").strip()
                    is_open = False
                else:
                    call_name = call_match.group(1)
                    is_open = True
                self._macro_calls.append(
                    SugarcubeMacroCall(
                        call_name,
                        self._cur_line_num,
                        map_to_orig_col(call_match.start()),
                        is_open,
                    )
                )
                if not is_open:
                    continue
                if self.extract_widgets and call_match.group(1) == "widget":
                    self._parse_user_widget(
                        uncomment_ln[call_match.start() : call_match.end()].strip(),
                    )
                if call_match.group(1) == "widget" and "widget" not in self.passages[-1].tags:
                    self.error_list.append(
                        {
                            "location": "{}:{}:0: '{}'".format(
                                self._cur_filepath, self._cur_line_num, self.passages[-1].name
                            ),
                            "message": "User-defined widget found in a passage not marked with the 'widget' tag! "
                            + "Tags: {}".format(
                                " ".join(self.passages[-1].tags) if self.passages[-1].tags else "<none>",
                            ),
                        }
                    )
            elif (call_start := uncomment_ln.find("<<", uncomment_ln_offset)) >= 0:
                self._macro_call_started = uncomment_ln[call_start:]
                if self._macro_call_started_at < 0:
                    self._macro_call_started_at = self._cur_line_num
                break
            else:
                break

    def finish_passage(self):
        if self._macro_call_started:
            self.error_list.append(
                {
                    "location": "{}:{}:0: '{}'".format(
                        self._cur_filepath, self._macro_call_started_at, self.passages[-1].name
                    ),
                    "message": "Cannot find a closing '>>' for macro starting with '{}'! ".format(
                        self._macro_call_started[: self._macro_call_started.find("\n")]
                    )
                    + "Reached the end of the passage.",
                }
            )

        open_stack = []

        def find_last_idx_in_open_stack(kw):
            try:
                return len(open_stack) - 1 - open_stack[::-1].index(kw)
            except ValueError:
                return -1

        for m_call in self._macro_calls:
            if not m_call.is_open:
                is_closing = True
                is_macro_tag = False
                closing_keyword = m_call.keyword
                last_match_idx = find_last_idx_in_open_stack(m_call.keyword)
            elif m_call.keyword in self.macro_tags:
                is_closing = True
                is_macro_tag = True
                last_match_idx = max([find_last_idx_in_open_stack(kw) for kw in self.macro_tags[m_call.keyword]])
                closing_keyword = (
                    open_stack[last_match_idx] if last_match_idx >= 0 else self.macro_tags[m_call.keyword][0]
                )
            else:
                is_closing = False
                is_macro_tag = False

            if is_closing:
                # Check match for closing tag
                if last_match_idx < 0:
                    if not self._find_macro(closing_keyword):
                        if self.ignore_unknown:
                            continue
                        self.error_list.append(
                            {
                                "location": "{}:{}:{}: '{}'".format(
                                    self._cur_filepath, m_call.line, m_call.col, self.passages[-1].name
                                ),
                                "message": "Closing tag '<</{}>>' does not match any known macro!".format(
                                    closing_keyword
                                ),
                            }
                        )
                    else:
                        self.error_list.append(
                            {
                                "location": "{}:{}:{}: '{}'".format(
                                    self._cur_filepath, m_call.line, m_call.col, self.passages[-1].name
                                ),
                                "message": "Child tag <<{}>> was found outside of a call to its parent macro <<{}>>!".format(
                                    ("" if is_macro_tag else "/") + m_call.keyword,
                                    closing_keyword,
                                ),
                            }
                        )
                    # We having a closing or inner tag without a matching parent, just skip it (after error report).
                    continue
                for i in range(len(open_stack) - 1, last_match_idx, -1):
                    # Error for every open parent context that hasn't been closed.
                    self.error_list.append(
                        {
                            "location": "{}:{}:{}: '{}'".format(
                                self._cur_filepath, m_call.line, m_call.col, self.passages[-1].name
                            ),
                            "message": "Cannot find a closing tag for macro '<<{}>>'! ".format(open_stack[i])
                            + "Parent context for '<<{}>>' is closing here.".format(closing_keyword),
                        }
                    )
                if is_macro_tag:
                    # Leave parent context open, tag is like a close/re-open of its parent.
                    open_stack = open_stack[: last_match_idx + 1]
                else:
                    # Close the parent, we have a matching closing tag.
                    open_stack = open_stack[:last_match_idx]
            else:
                # Find the macro.
                called_macro = self._find_macro(m_call.keyword)
                if not called_macro:
                    if self.ignore_unknown:
                        continue
                    self.error_list.append(
                        {
                            "location": "{}:{}:{}: '{}'".format(
                                self._cur_filepath, m_call.line, m_call.col, self.passages[-1].name
                            ),
                            "message": "Macro '<<{}>>' does not exist!".format(m_call.keyword),
                        }
                    )
                    continue
                if called_macro.deprecated_for:
                    self.error_list.append(
                        {
                            "location": "{}:{}:{}: '{}'".format(
                                self._cur_filepath, m_call.line, m_call.col, self.passages[-1].name
                            ),
                            "message": "Macro '<<{}>>' is deprecated!".format(m_call.keyword)
                            + (
                                " Use '<<{}>>' instead.".format(called_macro.deprecated_for)
                                if called_macro.deprecated_for != "unknown"
                                else " Please find an alternative way."
                            ),
                        }
                    )
                if not called_macro.is_container:
                    # Just skip it, no context to open, no closing tag expected.
                    continue
                open_stack.append(m_call.keyword)

        # After processing all close tags, any remaining open contexts are errors
        for open_kw in open_stack[::-1]:
            self.error_list.append(
                {
                    "location": "{}:{}:0: '{}'".format(self._cur_filepath, self._cur_line_num, self.passages[-1].name),
                    "message": "Cannot find a closing tag for macro '<<{}>>'! ".format(open_kw)
                    + "Reached the end of the passage.",
                }
            )

    def check(self, input_files: List[Path]) -> List[Dict]:
        for input_file in input_files:
            if input_file.suffix == ".html":
                self._skip_ignored_passage = True
                extractor = PassageExtractor(self, str(input_file))
                with open(input_file, "r", encoding="utf-8") as p_file:
                    for p_line in p_file:
                        extractor.feed(p_line)
                        if extractor.story_finished:
                            break
            else:
                self._skip_ignored_passage = False
                self.start_passage("root", [], str(input_file), 0, True)
                with open(input_file, "r", encoding="utf-8") as p_file:
                    for p_line in p_file:
                        self.process_line(p_line)
                self.finish_passage()
        self.error_list += check_duplicates(self.passages)
        return self.error_list

    def dump_results(self, f):
        if self.extract_widgets:
            json.dump(self.user_widgets, f, default=_serialize_macro_defs, indent=2)
        else:
            json.dump(self.error_list, f, indent=2)


def require_file_exists(filepath):
    """Verifies that the provided path points to a file that actually exists."""
    path = Path(filepath)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"'{filepath}' does not exist.")
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"'{filepath}' is a directory, not a file.")
    return path


def main():
    parser = argparse.ArgumentParser(
        prog="check_sugarcube_macros",
        description="Check Sugarcube passages for correct closing and nesting of macros",
    )
    parser.add_argument(
        "-m",
        "--macros",
        nargs="+",
        type=require_file_exists,
        help="Json files with dictionaries of macros (see sugarcube_macro_list.json)",
    )
    parser.add_argument(
        "-p",
        "--passages",
        nargs="*",
        type=require_file_exists,
        help="Sugarcube passages to check or the final HTML file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="stdout",
        help="Output JSON file with errors found",
    )
    parser.add_argument(
        "--extract_widgets",
        action="store_true",
        help="If set, passages are scanned for widgets and a list of user-defined macros is generated",
    )
    parser.add_argument(
        "--ignore_unknown",
        action="store_true",
        help="If set, unknown macro calls are ignored, which is useful when extracting widgets",
    )
    args = parser.parse_args()

    checker = SugarcubeMacroChecker(args.macros, args.extract_widgets, args.ignore_unknown)
    checker.check(args.passages)

    if args.output == "stdout":
        if checker.extract_widgets or not checker.error_list:
            checker.dump_results(sys.stdout)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            checker.dump_results(f)

    if checker.error_list:
        print("ERROR: There were errors while parsing the passages:", file=sys.stderr)
        for error_fields in checker.error_list:
            print(
                "ERROR: {}: {}".format(error_fields["location"], error_fields["message"]),
                file=sys.stderr,
            )
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
