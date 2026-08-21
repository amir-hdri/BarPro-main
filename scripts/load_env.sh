#!/usr/bin/env bash

# Load a dotenv file without eval/source expansion. Values such as bcrypt
# hashes contain '$' and must remain byte-for-byte unchanged.
load_dotenv() {
    local env_file="${1:-.env}"
    local line key value

    [ -f "$env_file" ] || return 0

    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        case "$line" in
            ''|[[:space:]]*'#'*) continue ;;
        esac

        line="${line#export }"
        [ "${line#*=}" != "$line" ] || continue

        key="${line%%=*}"
        value="${line#*=}"
        key="${key#${key%%[![:space:]]*}}"
        key="${key%${key##*[![:space:]]}}"

        case "$key" in
            ''|*[!A-Za-z0-9_]*)
                echo "ERROR: invalid environment key in $env_file: $key" >&2
                return 2
                ;;
        esac
        case "$key" in
            [0-9]*)
                echo "ERROR: invalid environment key in $env_file: $key" >&2
                return 2
                ;;
        esac

        value="${value#${value%%[![:space:]]*}}"
        value="${value%${value##*[![:space:]]}}"
        if [ "${#value}" -ge 2 ]; then
            case "$value" in
                \"*\") value="${value#\"}"; value="${value%\"}" ;;
                \'*\') value="${value#\'}"; value="${value%\'}" ;;
            esac
        fi

        export "$key=$value"
    done < "$env_file"
}
