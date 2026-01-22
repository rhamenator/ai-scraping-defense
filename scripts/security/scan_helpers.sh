#!/usr/bin/env bash
# Shared means to select wordlists and normalize report names.

safe_name() {
    echo "$1" | tr '/:' '_'
}

select_wordlist() {
    local override="$1"
    shift
    if [[ -n "$override" && -f "$override" ]]; then
        echo "$override"
        return 0
    fi
    for candidate in "$@"; do
        if [[ -f "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}
