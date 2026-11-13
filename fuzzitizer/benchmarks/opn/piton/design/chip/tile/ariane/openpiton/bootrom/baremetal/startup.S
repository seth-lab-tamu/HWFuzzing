# start sequence of the bootloader
#
#
#define DRAM_BASE 0x80000000

  .section .text.init
  .option norvc
  .globl _prog_start
_prog_start:
  li tp, 1
  sll tp, tp, 31
  csrr a0, mhartid
  li sp, 1
  sll sp, sp, 17
  sll sp, sp, a0
  add sp, sp, tp
  call main
  csrr a0, mhartid
  la a1, _dtb
  li s1, DRAM_BASE
  jr s1

  .section .text.hang, "ax", @progbits
  .globl _hang
_hang:
  csrr a0, mhartid
  la a1, _dtb
1:
  wfi
  j 1b

  .section .dtb
  .globl _dtb
  .align 4, 0
_dtb:
  .incbin "ariane.dtb"
