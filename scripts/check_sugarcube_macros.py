#!/bin/python
import argparse
import json
import re
import sys
from typing import List, Tuple, Dict


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


class SugarcubeMacroChecker:
    def __init__(self, macros_files: List[str]):
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
                                m_fields.get("user_path", filepath),
                                m_fields.get("user_line", 0),
                            )
                            for m_name, m_fields in data.items()
                        }
                    )
                else:
                    raise ValueError(f"Expected dict, got {type(data)}")
            except FileNotFoundError:
                raise FileNotFoundError(f"Keywords file not found: {filepath}")
        self.macro_tags = {}
        for m_name, m_fields in self.macros.items():
            for tag in m_fields.tags:
                if tag not in self.macro_tags:
                    self.macro_tags[tag] = [m_name]
                else:
                    self.macro_tags[tag].append(m_name)
        self.user_widgets = {}

        # Regex for opening tag: <<keyword args..>>
        self._opening_pattern = re.compile(
            # This is a tricky regex. The first part with the capture group is trivial, just
            # capturing the first legal identifier for the macro, i.e., doesn't start with '/',
            # and doesn't contain spaces or '<' or '>', as specified in sugarcube docs.
            # The second part is tricky because we want to get to the next '>>', but there
            # could be quoted strings, and isolated '>' characters. So, we match quoted strings
            # all together (accepting whatever inside) and we only match isolated '>' characters
            # or any non-'>' characters.
            r"""<<\s*([^\s<>\/][^\s<>]*)(?:"[^"]*"|'[^']*'|[^>]|[^>]>[^>])*>>""",
            re.IGNORECASE,
        )
        # Regex for closing tag: <</keyword>>
        self._closing_pattern = re.compile(rf"<<\s*/\s*([^\s<>]+)\s*>>", re.IGNORECASE)

        # Regex for user-defined widget: <<widget widgetName[ container]>>
        self._widget_pattern = re.compile(rf"<<\s*widget\s+([^\s<>]+)\s*([^\s<>]*)\s*>>", re.IGNORECASE)

        self._comment_pattern = re.compile(rf"(/\*|\*/|/%|%/|<!--|-->)", re.IGNORECASE)

        self._twee_header_pattern = re.compile(r"^::\s*(\S.*\S)\n?$")

        self.error_list: List[Dict] = []

    def _parse_user_widget(self, widget_call: str, filepath: str, line_num: int):
        wm = self._widget_pattern.search(widget_call)
        w_name = wm.group(1).strip(' "')
        if w_name in self.macros:
            self.error_list.append(
                {
                    "location": f"{filepath}:{line_num}:0",
                    "message": "User-defined widget name '{}' is already a built-in macro defined in '{}'!".format(
                        w_name, self.macros[w_name].user_path
                    ),
                }
            )
            return
        if w_name in self.user_widgets:
            self.error_list.append(
                {
                    "location": f"{filepath}:{line_num}:0",
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
                    filepath,
                    line_num,
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

    def check(self, passages_files: List[str], extract_widgets: bool, ignore_unknown: bool) -> List[Dict]:
        """Parse the text and return invalid, missing_closing, and corrupted tag info."""

        for passage in passages_files:
            p_line_num = 0
            macro_calls = []
            with open(passage, "r") as p_file:
                in_comment = [False, False, False]
                for p_line in p_file:
                    p_line_num += 1
                    uncomment_ln = ""
                    col_offsets = [(0, 0)]
                    last_valid_col = 0
                    for comment_match in self._comment_pattern.finditer(p_line):
                        if comment_match.group(1) in ["/*", "/%", "<!--"]:
                            if not any(in_comment):
                                uncomment_ln += p_line[last_valid_col : comment_match.start()]
                                last_valid_col = comment_match.start()
                            in_comment[["/*", "/%", "<!--"].index(comment_match.group(1))] = True
                        elif comment_match.group(1) in ["*/", "%/", "-->"]:
                            in_comment[["*/", "%/", "-->"].index(comment_match.group(1))] = False
                            if not any(in_comment):
                                next_valid_col = comment_match.start() + len(comment_match.group(1))
                                col_offsets.append(
                                    (
                                        len(uncomment_ln),
                                        col_offsets[-1][1] + next_valid_col - last_valid_col,
                                    )
                                )
                                last_valid_col = next_valid_col
                    if not any(in_comment):
                        uncomment_ln += p_line[last_valid_col:]

                    def map_to_orig_col(col):
                        last_offset = 0
                        for col_start, offset in col_offsets:
                            if col >= col_start:
                                last_offset = offset
                            else:
                                break
                        return col + last_offset

                    if tm := self._twee_header_pattern.fullmatch(uncomment_ln):
                        macro_calls.append(
                            SugarcubeMacroCall(
                                "<<<< TWEE FILE HEADER >>>>",
                                p_line_num,
                                map_to_orig_col(tm.start()),
                                True,
                            )
                        )
                        continue

                    macro_calls_ln = []
                    for open_match in self._opening_pattern.finditer(uncomment_ln):
                        macro_calls_ln.append(
                            SugarcubeMacroCall(
                                open_match.group(1),
                                p_line_num,
                                map_to_orig_col(open_match.start()),
                                True,
                            )
                        )
                        if extract_widgets and open_match.group(1) == "widget":
                            self._parse_user_widget(
                                uncomment_ln[open_match.start() : open_match.end()].strip(),
                                passage,
                                p_line_num,
                            )
                    for close_match in self._closing_pattern.finditer(uncomment_ln):
                        macro_calls_ln.append(
                            SugarcubeMacroCall(
                                close_match.group(1),
                                p_line_num,
                                map_to_orig_col(close_match.start()),
                                False,
                            )
                        )
                    macro_calls.extend(sorted(macro_calls_ln, key=lambda m: m.col))

            open_stack = []

            def find_last_idx_in_open_stack(kw):
                try:
                    return len(open_stack) - 1 - open_stack[::-1].index(kw)
                except ValueError:
                    return -1

            for m_call in macro_calls:
                # After encountering a twee file header, make sure open-stack is empty
                if m_call.keyword == "<<<< TWEE FILE HEADER >>>>":
                    for open_kw in open_stack[::-1]:
                        self.error_list.append(
                            {
                                "location": "{}:{}:{}".format(passage, m_call.line, 0),
                                "message": "Cannot find a closing tag for macro '<<{}>>'! Reached the end of the passage.".format(
                                    open_kw
                                ),
                            }
                        )
                    # Start fresh on next passage.
                    open_stack = []
                    continue

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
                            if ignore_unknown:
                                continue
                            self.error_list.append(
                                {
                                    "location": "{}:{}:{}".format(passage, m_call.line, m_call.col),
                                    "message": "Closing tag '<</{}>>' does not match any known macro!".format(
                                        closing_keyword
                                    ),
                                }
                            )
                        else:
                            self.error_list.append(
                                {
                                    "location": "{}:{}:{}".format(passage, m_call.line, m_call.col),
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
                                "location": "{}:{}:{}".format(passage, m_call.line, m_call.col),
                                "message": "Cannot find a closing tag for macro '<<{}>>'! Parent context for '<<{}>>' is closing here.".format(
                                    open_stack[i], closing_keyword
                                ),
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
                        if ignore_unknown:
                            continue
                        self.error_list.append(
                            {
                                "location": "{}:{}:{}".format(passage, m_call.line, m_call.col),
                                "message": "Macro '<<{}>>' does not exist!".format(m_call.keyword),
                            }
                        )
                        continue
                    if called_macro.deprecated_for:
                        self.error_list.append(
                            {
                                "location": "{}:{}:{}".format(passage, m_call.line, m_call.col),
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
                        "location": "{}:{}:{}".format(passage, p_line_num, 0),
                        "message": "Cannot find a closing tag for macro '<<{}>>'! Reached the end of the file.".format(
                            open_kw
                        ),
                    }
                )

        return self.error_list

    def dump_results(self, extract_widgets: bool, f):
        if extract_widgets:
            json.dump(self.user_widgets, f, default=_serialize_macro_defs, indent=2)
        else:
            json.dump(self.error_list, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        prog="check_sugarcube_macros",
        description="Check Sugarcube passages for correct closing and nesting of macros",
    )
    parser.add_argument(
        "-m",
        "--macros",
        nargs="+",
        type=str,
        help="Json files with dictionaries of macros (see sugarcube_macro_list.json)",
    )
    parser.add_argument("-p", "--passages", nargs="+", type=str, help="Sugarcube passages to check")
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

    checker = SugarcubeMacroChecker(args.macros)
    checker.check(args.passages, args.extract_widgets, args.ignore_unknown)

    if args.output == "stdout":
        checker.dump_results(args.extract_widgets, sys.stdout)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            checker.dump_results(args.extract_widgets, f)

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
