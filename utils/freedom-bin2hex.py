# Copyright 2018 SiFive, Inc
# SPDX-License-Identifier: Apache-2.0

import argparse, re
import sys


try:
# Python 3
    from itertools import zip_longest
except ImportError:
# Python 2
    from itertools import izip_longest as zip_longest


# Copied from https://docs.python.org/3/library/itertools.html
def grouper(iterable, n, fillvalue=None):
    """Collect data into fixed-length chunks or blocks"""
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)

def write_line(outfile, output_type, hex_row, line_count):
    #if output file type is mem, then write the line directly
    if output_type == 'mem':
        outfile.write(hex_row + '\n')
    #if output file type is hex, write after converting to hex
    else:
        hex_addr = hex(line_count)
        hex_addr = hex_addr[2:]
        hex_addr = hex_addr.zfill(8)
        #reformats important info so that the fuzzer can parse it
        inst1 = hex_row[24:32]
        inst2 = hex_row[16:24]#[::-1]
        inst3 = hex_row[8:16]#[::-1]
        inst4 = hex_row[0:8]#[::-1]
        formated_line = "@" + hex_addr + " " + inst1 + " " + inst2 + " " + inst3 + " " + inst4 + "\n"
        outfile.write(formated_line)


def convert(bit_width, infile, outfile, input_type, output_type):
    if input_type == 'bin':
        byte_width = bit_width // 8
        line_count = 0 # to keep track address in case of hex file
        if sys.version_info >= (3, 0):
            for row in grouper(infile.read(), byte_width, fillvalue=0):
                # Reverse because in Verilog most-significant bit of vectors is first.
                hex_row = ''.join('{:02x}'.format(b) for b in reversed(row))
                write_line(outfile, output_type, hex_row, line_count)
                line_count = line_count + 1
        else:
            for row in grouper(infile.read(), byte_width, fillvalue='\x00'):
                # Reverse because in Verilog most-significant bit of vectors is first.
                hex_row = ''.join('{:02x}'.format(ord(b)) for b in reversed(row))
                write_line(outfile, output_type, hex_row, line_count)
                line_count = line_count + 1
    if input_type == 'mem': #mem file => output file has to be hex
        #repoen the file as normal file
        infile = open(infile.name, 'r')
        line_count = 0 # to keep track address in case of hex file
        for line in infile: 
            line = line[0:32]
            write_line(outfile, output_type, line, line_count)
            line_count = line_count + 1

def main():
    parser = argparse.ArgumentParser(
        description='Convert a binary file to a format that can be read in '
                    'verilog via $readmemh(). By default read from stdin '
                    'and write to stdout.'
    )
    if sys.version_info >= (3, 0):
        parser.add_argument('infile',
                            nargs='?',
                            type=argparse.FileType('rb'),
                            default=sys.stdin.buffer)
    else:
        parser.add_argument('infile',
                            nargs='?',
                            type=argparse.FileType('rb'),
                            default=sys.stdin)
    parser.add_argument('outfile',
                        nargs='?',
                        type=argparse.FileType('w'),
                        default=sys.stdout)
    parser.add_argument('--bit-width', '-w',
                        type=int,
                        required=False,
                        help='How many bits per row. Default is 8')
    parser.add_argument('--input-type', '-itype',
                        required=False,
                        help='Specify the input file type?(bin or mem). Selects from input file name by default. Set to bin if no input file')
    parser.add_argument('--output-type', '-otype',
                        required=False,
                        help='Specify the output file type?(mem or hex). Selects from output file name by default. Set to mem if no output file')
    args = parser.parse_args()

    #set the bit width
    if args.bit_width == None:  #if bit width not set already
        args.bit_width = 8

    #set the input file type
    if args.input_type == None:  #if input type not set already
        if args.infile.name != "<stdin>": #if a input file name is given, extract type from it
            args.input_type = re.search("(.*)\.(.*)", args.infile.name).group(2)
            if args.input_type != 'bin' and args.input_type != 'mem': #if cannot extract from file name, use default type
                args.input_type = 'bin'
        else: #if no input file name given, then use default type
            args.input_type = 'bin'
    elif args.input_type != 'bin' and args.input_type != 'mem': #if a valid type is not mentined, abort the program
        sys.exit("Input type has to be 'bin' or 'mem'.")

    #set the output file type
    if args.output_type == None:  #if output type not set already
        if args.outfile.name != "<stdout>": #if a output file name is given, extract type from it
            args.output_type = re.search("(.*)\.(.*)", args.outfile.name).group(2)
            if args.output_type != 'mem' and args.output_type != 'hex': #if cannot extract from file name, use default type
                args.output_type = 'mem'
        else: #if no output file name given, then use default type
            args.output_type = 'mem'
    elif args.output_type != 'mem' and args.output_type != 'hex': #if a valid type is not mentined, abort the program
        sys.exit("Input type has to be 'mem' or 'hex'.")

    if args.bit_width % 8 != 0:
        sys.exit("Cannot handle non-multiple-of-8 bit width yet.")
    if args.bit_width != 128 and args.output_type == hex:
        sys.exit("Cannot generate hex file if bitwidth is not 128.")
    #if args.input_type == 0 and args.output_type == 1:
    #    sys.exit("Input and out are both mem files.Nothing to convert")
    convert(args.bit_width, args.infile, args.outfile, args.input_type,args.output_type)


if __name__ == '__main__':
    main()