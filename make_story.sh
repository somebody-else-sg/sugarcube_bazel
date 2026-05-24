#!/bin/bash

story_title=$1
shift
inner_storydata_file=$1
shift
format_template_file=$1
shift
output_path=$1
shift

# Escape the & for the sed substitution pattern.
esc2_story_title=$(echo "${story_title}" | sed 's/&/\\\&/g')
cat "${format_template_file}" | \
  sed -e "s/{{STORY_NAME}}/${esc2_story_title}/g" | \
  sed -e '/{{STORY_DATA}}/ {' -e "r ${inner_storydata_file}" -e 'd' -e '}' > "${output_path}"
