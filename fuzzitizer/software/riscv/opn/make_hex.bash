in_file=$1
out_file=$2
xxd -g 8 -c 32 $in_file | awk '{printf("%s %s %s %s\n", $2, $3, $4, $5);}' >> $out_file
