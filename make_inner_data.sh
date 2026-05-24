#!/bin/bash

set -e

all_args=( "$@" )
num_args=${#all_args[@]}
if [ "$num_args" -eq 0 ]; then
  echo "No arguments to command! Usage: $0 arg1 [arg2 ...] output_path" >&2
  exit 1
fi
input_paths=("${all_args[@]:0:$(($num_args - 1))}")
output_path=${all_args[$num_args-1]}

cat "${input_paths[@]}" > "${output_path}"

if command -v hxselect >/dev/null 2>&1; then
  duplicate_names=$(cat "${output_path}" | hxselect -c -s '\n' 'tw-passagedata::attr(name)' | sort | uniq -d)
  if [ -n "$duplicate_names" ]; then
    echo "ERROR: Duplicate passage names found!" >&2
    echo "ERROR: >>>> Passages:" >&2
    echo "$duplicate_names" >&2
    echo "ERROR: <<<<" >&2
    exit 2
  fi
fi
