#!/usr/bin/env bash

source "$(dirname "${BASH_SOURCE[0]}")/../../colors.sh"

# Global array to store selected YAML paths.
declare -a YAML_PATHS


# Select the newest .yaml file in each result folder; warn if their lengths differ.
function parse_args {
    local yaml_path=""
    local yaml_length=-1
    local cur_yaml_length=0
    local idx=0

    for path in $@; do
        # Check if first dir exist.
        [ ! -d $path ] && fatal "$path does not exist"

        # Check if dir has .yaml files.
        NF=$(ls -1 $path/result.*.yaml 2>/dev/null | wc -l)
        [ "$NF" == 0 ] && fatal "$path does not have .yaml files"

        # If multiple YAML files found, pick the highest-numbered one.
        yaml_path=$(ls "$path"/result.*.yaml 2>/dev/null | sort -V | tail -n 1)
        [ "$NF" -gt 1 ] && echo "Multiple YAML files found in $path, using highest-numbered: $(basename "$yaml_path")" 1>&2

        # Store the selected yaml path in global array.
        YAML_PATHS[$idx]=$yaml_path
        idx=$((idx + 1))

        # Overwrite stored .yaml file length if not stored yet.
        cur_yaml_length=$(wc -l < "$yaml_path")
        [ "$yaml_length" == -1 ] && yaml_length=$cur_yaml_length

        # Warn if .yaml files differ in length (e.g. timing section present in one but not the other).
        [ "$cur_yaml_length" != "$yaml_length" ] && warn "$path's .yaml file is of different length ($yaml_length != $cur_yaml_length)"
    done


}

# Compare two strings and print difference in color.
function compare_strings {
    local val1=$1
    local val2=$2
    local line="                                "

    # Check if strings are equal.
    if [ "$val1" == "$val2" ]; then
        printf "\t%s %s %s\n" $val1 "${line:${#val2}}" $val2
    else
        # Find point till when the characters are equal, then print.
        # NOTE: Couldn't find anything more efficient, maybe change in future.
        for (( i=0; i<${#val1}; i++ )); do
            if [ "${val1:i:1}" != "${val2:i:1}" ]; then
                # Print equal part in black, and difference in red for both.
                printf "\t${val1::i}$RED${val1:i}$NC ${line:${#val2}} ${val2::i}$RED${val2:i}$NC\n"
                break
            fi
        done
    fi
}

# Compare the output of the .yaml files, given as arguments.
function compare_yaml {
    local model_reached=0
    local varname
    local val1
    local val2
    local array1
    local array2

    # Go line by line over yaml files and print difference.
    while read line1 <&3 && read line2 <&4; do
        # Pass till model section is reached.
        if [ $model_reached == 0 ]; then
            [ "$line1" == "model:" ] && model_reached=1
            continue
        fi

        # Stop when timing section is reached.
        [ "$line1" == "timing:" ] && break 

        # Extract values from the lines.
        varname=${line1%: *}
        val1=${line1#*: }
        val2=${line2#*: }

        # Print current variable.
        echo "$varname:"

        # Parse data type for check.
        if [ "${val1:0:1}" = "[" ]; then
            # Convert values to arrays.
            val1=${val1:2:-2}
            array1=(${val1//, / })
            val2=${val2:2:-2}
            array2=(${val2//, / })

            # Parse variables as arrays.
            for i in "${!array1[@]}"; do
                compare_strings "${array1[i]}" "${array2[i]}"
            done

            # join into strings
            A="${array1[*]}"
            B="${array2[*]}"

            # compute L2 norm via awk
            l2norm=$(awk -v X="$A" -v Y="$B" '
              BEGIN {
                split(X, x)
                split(Y, y)
                sum = 0
                for (i = 1; i <= length(x); i++) {
                  d = x[i] - y[i]       # works with 1.23e-4 just fine
                  sum += d*d
                }
                # change "%.6f" to "%.6e" if you want scientific output
                printf "%.6e\n", sqrt(sum)
              }')

          echo "L_2($varname) = $l2norm"

        else
            # Parse variables as strings.
            compare_strings $val1 $val2
        fi
        
        # Print empty line for readability.
        echo ""
    done 3<"${YAML_PATHS[0]}" 4<"${YAML_PATHS[1]}"
}

# Entry point.
function main {
    # On entry, parse given paths to results.
    path1=$1
    path2=$2
    parse_args $path1 $path2
    compare_yaml $path1 $path2
}

main $@
