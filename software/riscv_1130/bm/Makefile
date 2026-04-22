#=======================================================================
# UCB VLSI FLOW: Makefile for riscv-bmarks
#-----------------------------------------------------------------------
# Yunsup Lee (yunsup@cs.berkeley.edu)
#


TOP_ROOT			= ${THEHUZZ_ROOT}
SOFTWARE_ROOT	    = $(TOP_ROOT)/software
UTILS_ROOT	        = $(TOP_ROOT)/utils
RISCV_ROOT			= $(SOFTWARE_ROOT)/riscv_1130/bm

C_DIR 			?= inst_files_all


########################################
# All lists here
########################################
BAREMETAL_SRC = $(wildcard $(RISCV_ROOT)/common/*.c) $(wildcard $(RISCV_ROOT)/common/*.S)

C_LIST    	= $(patsubst %.c, %, $(wildcard $(C_DIR)/*.c))
HEX_LIST  	= $(addsuffix .hex, $(C_LIST))
DUMP_LIST 	= $(addsuffix .riscv.dump, $(C_LIST))
RISCV_LIST 	= $(addsuffix .riscv, $(C_LIST))
BIN_LIST 	= $(addsuffix .bin, $(C_LIST))

C_FILE  ?= test.c
HEX_FILE   = $(patsubst %.c, %.hex, $(C_FILE))
DUMP_FILE  = $(patsubst %.c, %.riscv.dump, $(C_FILE))
BIN_FILE  = $(patsubst %.c, %.bin, $(C_FILE))
RISCV_FILE  = $(patsubst %.c, %.riscv, $(C_FILE))

junk += $(HEX_LIST) $(DUMP_LIST) $(BIN_LIST) $(RISCV_LIST)

########################################
# Variables
########################################
XLEN ?= 64
RISCV_PREFIX 		?= riscv$(XLEN)-unknown-elf-
RISCV_GCC 			?= $(RISCV_PREFIX)gcc
RISCV_GCC_OPTS 		?= -DPREALLOCATE=1 -mcmodel=medany -static -std=gnu99 -O4 -ffast-math -fno-common -fno-builtin-printf -march=rv64imafd_zifencei #add zifencei for fence.i instructions
RISCV_GCC_OPTS      += -Wl,--no-warn-rwx-segments # disable rwx warning for baremetal simulation
RISCV_LINK 			?= $(RISCV_GCC) -T $(RISCV_ROOT)/common/test.ld $(incs)
RISCV_LINK_OPTS 	?= -static -nostdlib -nostartfiles -lm -lgcc -T $(RISCV_ROOT)/common/test.ld
#RISCV_OBJCPY_BIN 	?= $(RISCV_PREFIX)objcopy
RISCV_OBJDUMP 		?= $(RISCV_PREFIX)objdump -D
RISCV_SIM 			?= spike --isa=rv$(XLEN)gc

BIN_TO_HEX 			?= python3 $(UTILS_ROOT)/freedom-bin2hex.py

incs 	= -I$(RISCV_ROOT)/env -I$(RISCV_ROOT)/common 

########################################
# Rules
########################################
%.riscv: %.c  $(BAREMETAL_SRC)
	$(RISCV_GCC) $(incs) $(RISCV_GCC_OPTS) -o $@ $^ $(RISCV_LINK_OPTS)

#%.bin: %.riscv
#	$(RISCV_OBJCPY_BIN) $< -O binary $@

%.riscv.dump: %.riscv
	$(RISCV_OBJDUMP) $< >  $@

%.hex: %.riscv
	$(BIN_TO_HEX) --bit-width 128 -itype bin -otype hex $< $@

########################################
# Commands
########################################

# to compile all c files in the C_DIR dir
compile_all: $(HEX_LIST) $(DUMP_LIST)

# to compile one single c file
compile: $(HEX_FILE) $(DUMP_FILE)

########################################
# Clean up
########################################
clean:
	rm  $(junk)/ *.riscv *.hex *.riscv.dump *.bin

.PHONY: all clean compile_all

.SECONDARY: $(RISCV_LIST) $(BIN_LIST)
