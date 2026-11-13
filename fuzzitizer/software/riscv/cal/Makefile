# Caliptra RV32 bare-metal program build.

TOP_ROOT = ${FUZZITIZER_ROOT}
SOFTWARE_ROOT = $(TOP_ROOT)/software
RISCV_ROOT = $(SOFTWARE_ROOT)/riscv/cal
CALIPTRA_ROOT ?= $(TOP_ROOT)/benchmarks/cal

C_DIR ?= inst_files_all

C_LIST = $(patsubst %.c, %, $(wildcard $(C_DIR)/*.c))
HEX_LIST = $(addsuffix .cal, $(C_LIST))
DUMP_LIST = $(addsuffix .riscv.dump, $(C_LIST))
RISCV_LIST = $(addsuffix .riscv, $(C_LIST))

GCC_PREFIX ?= riscv64-unknown-elf
RISCV_GCC = $(GCC_PREFIX)-gcc
RISCV_OBJDUMP = $(GCC_PREFIX)-objdump
RISCV_OBJCOPY = $(GCC_PREFIX)-objcopy

ABI = -mabi=ilp32 -march=rv32ima_zicsr_zifencei
CFLAGS = -g -O3 $(ABI) -nostdlib
LINK = $(CALIPTRA_ROOT)/src/integration/test_suites/libs/riscv_hw_if/link.ld
CRT0 = $(RISCV_ROOT)/crt0.o

%.o: %.c
	@$(RISCV_GCC) $(CFLAGS) -c $< -o $@

%.riscv: %.o $(CRT0) $(LINK)
	@$(RISCV_GCC) $(ABI) -Wl,-Map=$*.map -lgcc -T$(LINK) -o $@ $(CRT0) $< -nostartfiles

%.riscv.dump: %.riscv
	@$(RISCV_OBJDUMP) -S $< > $@

%.cal: %.riscv
	@$(RISCV_OBJCOPY) -O verilog -R .data_iccm0 -R .data_iccm1 -R .data_iccm2 -R .iccm -R .dccm -R .eh_frame --pad-to 0xC000 --no-change-warnings $< $@

compile_all: $(HEX_LIST) $(DUMP_LIST)

compile_all_with_dumps: compile_all

clean:
	rm -f $(HEX_LIST) $(DUMP_LIST) $(RISCV_LIST) $(addsuffix .o, $(C_LIST)) $(addsuffix .map, $(C_LIST))

.PHONY: clean compile_all compile_all_with_dumps
.SECONDARY: $(RISCV_LIST)
