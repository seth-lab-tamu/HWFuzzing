#=======================================================================
# UCB VLSI FLOW: Makefile for riscv-bmarks
#-----------------------------------------------------------------------
# Yunsup Lee (yunsup@cs.berkeley.edu)
#


TOP_ROOT			= ${FUZZITIZER_ROOT}
SOFTWARE_ROOT	    = $(TOP_ROOT)/software
UTILS_ROOT	        = $(TOP_ROOT)/utils
RISCV_ROOT			= $(SOFTWARE_ROOT)/riscv/opn

C_DIR 			?= inst_files_all

.DEFAULT_GOAL := compile_all


########################################
# All lists here
########################################
RUNTIME_SRC_DIR = $(RISCV_ROOT)/common
RUNTIME_OBJ_DIR = $(C_DIR)/.opn_runtime
RUNTIME_HEADERS = $(wildcard $(RUNTIME_SRC_DIR)/*.h) $(wildcard $(RISCV_ROOT)/env/*.h)
RUNTIME_C_SRC = $(wildcard $(RUNTIME_SRC_DIR)/*.c)
RUNTIME_ASM_SRC = $(wildcard $(RUNTIME_SRC_DIR)/*.S)
RUNTIME_C_OBJS = $(patsubst $(RUNTIME_SRC_DIR)/%.c,$(RUNTIME_OBJ_DIR)/%.c.o,$(RUNTIME_C_SRC))
RUNTIME_ASM_OBJS = $(patsubst $(RUNTIME_SRC_DIR)/%.S,$(RUNTIME_OBJ_DIR)/%.S.o,$(RUNTIME_ASM_SRC))
RUNTIME_OBJS = $(RUNTIME_C_OBJS) $(RUNTIME_ASM_OBJS)

C_LIST    	= $(patsubst %.c, %, $(wildcard $(C_DIR)/*.c))
HEX_LIST  	= $(addsuffix .opn, $(C_LIST))
DUMP_LIST 	= $(addsuffix .riscv.dump, $(C_LIST))
RISCV_LIST 	= $(addsuffix .riscv, $(C_LIST))
BIN_LIST 	= $(addsuffix .bin, $(C_LIST))

junk += $(HEX_LIST) $(DUMP_LIST) $(BIN_LIST) $(RISCV_LIST)

########################################
# Variables
########################################
XLEN ?= 64
RISCV_PREFIX 		?= riscv$(XLEN)-unknown-elf-
RISCV_GCC 			?= $(RISCV_PREFIX)gcc
RISCV_GCC_OPTS 		?= -DPREALLOCATE=1 -mcmodel=medany -static -std=gnu99 -O4 -ffast-math -fno-common -fno-builtin-printf -march=rv64imafd_zifencei
RISCV_LINK 			?= $(RISCV_GCC) -T $(RISCV_ROOT)/common/test.ld $(incs)
RISCV_LINK_OPTS 	?= -static -nostdlib -nostartfiles -lm -lgcc -T $(RISCV_ROOT)/common/test.ld
RISCV_OBJCPY_BIN 	?= $(RISCV_PREFIX)objcopy
RISCV_OBJDUMP 		?= $(RISCV_PREFIX)objdump -D
RISCV_SIM 			?= spike --isa=rv$(XLEN)gc

incs 	= -I$(RISCV_ROOT)/env -I$(RISCV_ROOT)/common 

########################################
# Rules
########################################
$(RUNTIME_OBJ_DIR):
	@mkdir -p $@

$(RUNTIME_OBJ_DIR)/%.c.o: $(RUNTIME_SRC_DIR)/%.c $(RUNTIME_HEADERS) | $(RUNTIME_OBJ_DIR)
	@$(RISCV_GCC) $(incs) $(RISCV_GCC_OPTS) -c -o $@ $<

$(RUNTIME_OBJ_DIR)/%.S.o: $(RUNTIME_SRC_DIR)/%.S $(RUNTIME_HEADERS) | $(RUNTIME_OBJ_DIR)
	@$(RISCV_GCC) $(incs) $(RISCV_GCC_OPTS) -c -o $@ $<

%.riscv: %.c $(RUNTIME_OBJS)
	@$(RISCV_GCC) $(incs) $(RISCV_GCC_OPTS) -o $@ $< $(RUNTIME_OBJS) $(RISCV_LINK_OPTS)

%.bin: %.riscv
	@$(RISCV_OBJCPY_BIN) $< -O binary $@

%.riscv.dump: %.riscv
	@$(RISCV_OBJDUMP) $< >  $@

%.opn: %.bin
	@printf "\n@0000000080000000\t// Section '.RED_SEC', segment 'text'\n" >$@
	@./make_hex.bash $^ $@ > /dev/null 2>&1

########################################
# Commands
########################################

# to compile all c files in the C_DIR dir
compile_all: $(HEX_LIST)

compile_all_with_dumps: $(HEX_LIST) $(DUMP_LIST)

########################################
# Clean up
########################################
clean:
	rm -f $(C_DIR)/*.riscv $(C_DIR)/*.opn $(C_DIR)/*.riscv.dump $(C_DIR)/*.bin
	rm -rf $(RUNTIME_OBJ_DIR)

.PHONY: clean compile_all compile_all_with_dumps

.SECONDARY: $(RISCV_LIST) $(BIN_LIST) $(RUNTIME_OBJS)
