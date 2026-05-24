#!/bin/bash

output_path=$1
shift
tags_str=$1
shift

for input_file in "$@"
do
    # Get passage name from top line as /* PASSAGE: My passage name */
    # Yielding: My passage name
    passage_name=$(head -1 "${input_file}" | sed 's|/\*.*PASSAGE:\s*\(\S.*\S\)\s*\*/.*|\1|g')
    if [[ "${passage_name}" == "Start" ]]; then
        echo "<tw-passagedata name=\"Start\" pid=\"1\" tags=\"${tags_str}\">" >> "${output_path}"
    else
        echo "<tw-passagedata name=\"${passage_name}\" tags=\"${tags_str}\">" >> "${output_path}"
    fi
    # Escape special characters for html
    tail -n +2 "${input_file}" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'"'"'/\&#39;/g' >> "${output_path}"
    echo "" >> "${output_path}"
    echo "</tw-passagedata>" >> "${output_path}"
done
