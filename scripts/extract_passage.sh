#!/bin/bash

# This script extracts passages from a Sugarcube / Twine story.
# Usage:
#  - Take the index.html (or whatever the top-level html page is called) and
#    extract the html element 'tw-storydata' which contains all the story data
#    of the story/game.
#  - With an html file starting with <tw-storydata ..> and ending in </tw-storydata>,
#    invoke the script like this:
#    $ extract_passage.sh my_story_data.html "PassageName" passage_name.scp
#  - The script looks for the passage named "PassageName" and extracts its body
#    into a sugarcube passage file containing the unescaped content of the passage.
#  - The script can also be invoked from bazel, as 'bazel run //scripts:extract_passage',
#    but note that it will require using absolute paths for the input and output files.
#    Running with bazel might help it work in Windows.

set -e

html_path=$1
shift
passage_name=$1
shift
output_file=$1
shift

echo "/* PASSAGE: $passage_name */" > "$output_file"
xmllint --xpath "/tw-storydata/tw-passagedata[@name = '${passage_name}']/text()" "$html_path" | sed 's/\&amp;/&/g; s/\&lt;/</g; s/\&gt;/>/g; s/\&quot;/"/g; s/\&#39;/'"'"'/g' >> "$output_file"
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    rm "$output_file"
fi
