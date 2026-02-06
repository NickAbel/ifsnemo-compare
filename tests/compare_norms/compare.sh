#!/usr/bin/env bash

# Global color definitions.
NC='\033[0m'
RED='\033[1;31m'
GREEN='\033[1;32m'


# Display fatal styled message with given argument.
function fatal {
    echo -e "$RED \u274c FATAL: $1$NC" 1>&2
    return 1
}

# Display success styled message with given argument.
function success {
    echo -e "$GREEN \u2714 ~ $1$NC" 1>&2
}

# See if arguments point to result folders with .yaml files of equal length.
function parse_args {
    local yaml_path=""
    local yaml_length=-1
    local cur_yaml_length=0
    
    for path in $@; do
        # Check if first dir exist.
        [ ! -d $path ] && fatal "$path does not exist"
        yaml_path=$path/result.*.yaml

        # Check if first dir has .yaml files.
        NF=$(ls -1 $yaml_path 2>/dev/null | wc -l)
        [ "$NF" != 1 ] && fatal "$path does not have .yaml files"
    
        # Overwrite stored .yaml file length if not stored yet.
        cur_yaml_length=$(wc -l < $yaml_path)
        [ $yaml_length == -1 ] && yaml_length=$cur_yaml_length

        # Check if .yaml file has same length.
        [ $cur_yaml_length != $yaml_length ] && fatal "$path's .yaml file is of different length ($yaml_length != $cur_yaml_length)"
    done

    success "Both result files exist and have .yaml files of equal length."
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
    done 3<$1/result.*.yaml 4<$2/result.*.yaml
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
