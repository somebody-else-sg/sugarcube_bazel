#!/bin/bash

story_format_path=$1
shift
format_name_file=$1
shift
format_version_file=$1
shift
format_template_file=$1
shift

format_json_file=$(mktemp) || { echo "ERROR: Failed to create temp file"; exit 1; }

cleanup_temps() {
    rm -f "${format_json_file}"
}

trap cleanup_temps EXIT

# Extract json. (why is this not already json file?)
cat "${story_format_path}" | sed -E 's|window\.storyFormat\((.*)\);|\1|g' > "${format_json_file}"

cat "${format_json_file}" | jq -r '.name' | tr -d '\n' > "${format_name_file}"
cat "${format_json_file}" | jq -r '.version' | tr -d '\n' > "${format_version_file}"
cat "${format_json_file}" | jq -r '.source' > "${format_template_file}"
