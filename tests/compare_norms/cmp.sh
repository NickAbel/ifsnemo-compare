#!/bin/bash

function parse_yaml {
   local prefix=$2
   local s='[[:space:]]*' w='[a-zA-Z0-9_]*' fs=$(echo @|tr @ '\034')
   echo "$1" | sed -ne "s|,$s\]$s\$|]|" \
        -e ":1;s|^\($s\)\($w\)$s:$s\[$s\(.*\)$s,$s\(.*\)$s\]|\1\2: [\3]\n\1  - \4|;t1" \
        -e "s|^\($s\)\($w\)$s:$s\[$s\(.*\)$s\]|\1\2:\n\1  - \3|;p" | \
   sed -ne "s|,$s}$s\$|}|" \
        -e ":1;s|^\($s\)-$s{$s\(.*\)$s,$s\($w\)$s:$s\(.*\)$s}|\1- {\2}\n\1  \3: \4|;t1" \
        -e    "s|^\($s\)-$s{$s\(.*\)$s}|\1-\n\1  \2|;p" | \
   sed -ne "s|^\($s\):|\1|" \
        -e "s|^\($s\)-$s[\"']\(.*\)[\"']$s\$|\1$fs$fs\2|p" \
        -e "s|^\($s\)-$s\(.*\)$s\$|\1$fs$fs\2|p" \
        -e "s|^\($s\)\($w\)$s:$s[\"']\(.*\)[\"']$s\$|\1$fs\2$fs\3|p" \
        -e "s|^\($s\)\($w\)$s:$s\(.*\)$s\$|\1$fs\2$fs\3|p" | \
   awk -F$fs '{
      indent = length($1)/2;
      vname[indent] = $2;
      for (i in vname) {if (i > indent) {delete vname[i]; idx[i]=0}}
      if(length($2)== 0){  vname[indent]= ++idx[indent] };
      if (length($3) > 0) {
         vn=""; for (i=0; i<indent; i++) { vn=(vn)(vname[i])("_")}
         printf("%s%s%s=\"%s\"\n", "'$prefix'",vn, vname[indent], $3);
      }
   }'
}

function find_result_yaml() {
    local DIR=$1
    NF=$(ls -1 $DIR/result.*.yaml 2>/dev/null | wc -l)
    [ "$NF" != 1 ] && { echo "FATAL: pattern $DIR/result.*.yaml doesn't give a single yaml-result file" 1>&2; return 1; }
    ls -1 $DIR/result.*.yaml
    return 0
}

function compare() {
    local a=$1
    local b=$2
    local label=$3
    local bcscript=$(echo "$a $b" | gawk '{print "scale=20; " $1*100000000000000000 "-" $2*100000000000000000}')
    local diff=$(echo $bcscript | bc)
    if [ "$diff" != "0" ]; then 
        echo "diff: $label: $diff"
    fi
}

[ -z "$1" -o -z "$2" ] && { echo "FATAL: Two result directory names are required as args"; exit 1; }

YAML=$(find_result_yaml $1)
[ -z "$YAML" ] && exit 1
eval $(parse_yaml "$(cat $YAML | sed 's/---//')" "first__")

YAML=$(find_result_yaml $2)
[ -z "$YAML" ] && exit 1
eval $(parse_yaml "$(cat $YAML | sed 's/---//')" "second__")


[ "$first__execution__success" != "true" ] && { echo "FATAL: In directory $1: execution result is not success"; exit 1;}
[ "$second__execution__success" != "true" ] && { echo "FATAL: In directory $2: execution result is not success"; exit 1;}

[ "$first__model__last_step" != "$second__model__last_step" ] && { echo "FATAL: Not matching number of time steps: $first__model__last_step and $second__model__last_step"; exit 1; } 

NSTEPS=$first__model__last_step
for i in $(seq 0 1 $NSTEPS); do
    for var in ssh_norm_max U_norm_max S_min S_max; do
        eval compare \$first__model__${var}_${i} \$second__model__${var}_${i} "${var}[${i}]"
    done
done
