# Change log
The compilation is similar to software/riscv. Only difference is disabling the generation of bin files in Makefile as chipyard 1.13.0 receive elf/riscv files as input directly.

# RISC-V compiler
This repo is used to compile C files to riscv elf and hex formats (Please make sure that your `PATH` is set to the RISCV toolchain install directory.):
  * To compile all C files in a dir, run:
  ```
  $ make compile all C_DIR=<dir where the C files are>
  ```
   The output riscv and hex files are stored in the same directory as the C files.

  * To compile a single C file (make sure the file in this directory), run:
  ```
  $ make <name of the C file without extension>.hex
  ```

# Python script usage instructions
The python script, `freedom-bin2hex.py` can be used to perform bin or mem to mem or hex formats. Here, bin is the binary format from the compiler, mem is the pure binary data and hex is the addr & data format (@addr instr1 instr2 instr3 instr4).

  * The bit width argument has to be mentioned that specifies the size of mem file. A default value of 8 is assumed otherwise.

# Installing the RISCV toolchain
If you have already installed the toolchain in your computer, make sure that your `PATH` variable includes the installation directory:
```
$ export PATH=$PATH:<RISCV installation directory>/bin
```

If you do not have RISCV toolchain installed in your computer, follow the instructions below (does not require sudo access but disbles the gdb option):
```
$ cd <location where you want to install the toolchain>
$ export SOURCE_DIR=$PWD
$ git clone --recursive https://github.com/riscv/riscv-gnu-toolchain.git
$ cd riscv-gnu-toolchain
$ ./configure --prefix=$SOURCE_DIR --disable-gdb
$ make
$ export PATH=$PATH:$SOURCE_DIR/bin
$ export RISCV=$SOURCE_DIR
```

# About source
This repo is a modified version of [RISCV tests](https://github.com/riscv/riscv-tests) repo cloned on Nov 12, 2019.