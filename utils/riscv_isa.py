#this file lists all the RISC-V instructions and their formats

##instructions are grouped based on the structure of their  mnemonics
#inst_format_dict = { "r"  : 0, "r1" : 1, "r2" : 2
#                    ,"i"  : 3, "i1" : 4, "i2" : 5 
#                    ,"u"  : 6, "s"  : 7, "b"  : 8 
#                    ,"j"  : 9 }

##instruction types/names based on their functionality i
#    (should have called this name)
#inst_type_dict = { 
#        "Arithmetic" : 0,    "Jump & Link" : 1, "Branches" : 2,  "Loads" : 3\
#       ,"Stores" : 4,        "Compare" : 5,     "Logical" : 6,   "Shifts" : 7\
#       ,"Sync" : 8,          "System" : 9,      "CSR Access" : 10\
#       ,"Multiply" : 11,     "Divide" : 12,     "Remainder" : 13\
#       ,"Load Reserved" : 14,"Store Cond" : 15, "Swap Atomic":16\
#       ,"Add Atomic" : 17,   "Logical Atomic" : 18,    "Min/Max Atomic":19 }



#RV32I extension instructions and their formats:
#rv32i dict:
#  key: instruction in assembly language
#  value: [0:instrn type, 1:instrn format type, 2:bits[], 3:bits[], \
#          4:bits[],      5:extension,  \
#          6:single_inst_run/multi_inst_run(for profiling), \
#          7:clone_no(for profiling)]
#note: 
#  - fence .i wont match with table in spec, see section 2.7 
rv32i = {
        "LUI"    : [ "Arithmetic" , "u" , "xxxxxxx", "xxx", "0110111", "RV32I", "0", 300 ],
        "AUIPC"  : [ "Arithmetic" , "u" , "xxxxxxx", "xxx", "0010111", "RV32I", "0", 301 ],
        "JAL"    : [ "Jump & Link", "j" , "xxxxxxx", "xxx", "1101111", "RV32I", "1", 302 ],
        "JALR"   : [ "Jump & Link", "i" , "xxxxxxx", "000", "1100111", "RV32I", "1", 303 ],
        "BEQ"    : [ "Branches"   , "b" , "xxxxxxx", "000", "1100011", "RV32I", "1", 304 ],
        "BNE"    : [ "Branches"   , "b" , "xxxxxxx", "001", "1100011", "RV32I", "1", 305 ],
        "BLT"    : [ "Branches"   , "b" , "xxxxxxx", "100", "1100011", "RV32I", "1", 306 ],
        "BGE"    : [ "Branches"   , "b" , "xxxxxxx", "101", "1100011", "RV32I", "1", 307 ],
        "BLTU"   : [ "Branches"   , "b" , "xxxxxxx", "110", "1100011", "RV32I", "1", 308 ],
        "BGEU"   : [ "Branches"   , "b" , "xxxxxxx", "111", "1100011", "RV32I", "1", 309 ],
        "LB"     : [ "Loads"      , "i" , "xxxxxxx", "000", "0000011", "RV32I", "0", 310 ],
        "LH"     : [ "Loads"      , "i" , "xxxxxxx", "001", "0000011", "RV32I", "1", 311 ],
        "LW"     : [ "Loads"      , "i" , "xxxxxxx", "010", "0000011", "RV32I", "1", 312 ],
        "LBU"    : [ "Loads"      , "i" , "xxxxxxx", "100", "0000011", "RV32I", "0", 313 ],
        "LHU"    : [ "Loads"      , "i" , "xxxxxxx", "101", "0000011", "RV32I", "1", 314 ],
        "SB"     : [ "Stores"     , "s" , "xxxxxxx", "000", "0100011", "RV32I", "1", 315 ],
        "SH"     : [ "Stores"     , "s" , "xxxxxxx", "001", "0100011", "RV32I", "1", 316 ],
        "SW"     : [ "Stores"     , "s" , "xxxxxxx", "010", "0100011", "RV32I", "1", 317 ],
        "ADDI"   : [ "Arithmetic" , "i" , "xxxxxxx", "000", "0010011", "RV32I", "0", 318 ],
        "SLTI"   : [ "Compare"    , "i" , "xxxxxxx", "010", "0010011", "RV32I", "0", 319 ],
        "SLTIU"  : [ "Compare"    , "i" , "xxxxxxx", "011", "0010011", "RV32I", "0", 500 ],
        "XORI"   : [ "Logical"    , "i" , "xxxxxxx", "100", "0010011", "RV32I", "0", 501 ],
        "ORI"    : [ "Logical"    , "i" , "xxxxxxx", "110", "0010011", "RV32I", "0", 502 ],
        "ANDI"   : [ "Logical"    , "i" , "xxxxxxx", "111", "0010011", "RV32I", "0", 503 ],
        "SLLI"   : [ "Shifts"     , "r" , "0000000", "001", "0010011", "RV32I", "0", 504 ],
        "SRLI"   : [ "Shifts"     , "r" , "0000000", "101", "0010011", "RV32I", "0", 505 ],
        "SRAI"   : [ "Shifts"     , "r" , "0100000", "101", "0010011", "RV32I", "0", 506 ],
        "ADD"    : [ "Arithmetic" , "r" , "0000000", "000", "0110011", "RV32I", "0", 507 ],
        "SUB"    : [ "Arithmetic" , "r" , "0100000", "000", "0110011", "RV32I", "0", 508 ],
        "SLL"    : [ "Shifts"     , "r" , "0000000", "001", "0110011", "RV32I", "0", 509 ],
        "SLT"    : [ "Compare"    , "r" , "0000000", "010", "0110011", "RV32I", "0", 510 ],
        "SLTU"   : [ "Compare"    , "r" , "0000000", "011", "0110011", "RV32I", "0", 511 ],
        "XOR"    : [ "Logical"    , "r" , "0000000", "100", "0110011", "RV32I", "0", 512 ],
        "SRL"    : [ "Shifts"     , "r" , "0000000", "101", "0110011", "RV32I", "0", 513 ],
        "SRA"    : [ "Shifts"     , "r" , "0100000", "101", "0110011", "RV32I", "0", 514 ],
        "OR"     : [ "Logical"    , "r" , "0000000", "110", "0110011", "RV32I", "0", 515 ],
        "AND"    : [ "Logical"    , "r" , "0000000", "111", "0110011", "RV32I", "0", 516 ],
        "FENCE"  : [ "Sync"       , "i1", "0000xxx", "000", "0001111", "RV32I", "0", 517 ],
        "FENCE.I": [ "Sync"       , "i2", "xxxxxxx", "001", "0001111", "RV32I", "1", 118 ],
        "ECALL"  : [ "System"     , "i2", "0000000", "000", "1110011", "RV32I", "1", 119 ],
        "EBREAK" : [ "System"     , "i2", "0000000", "000", "1110011", "RV32I", "1", 100 ],
        "CSRRW"  : [ "CSR Access" , "i" , "xxxxxxx", "001", "1110011", "RV32I", "1", 101 ],
        "CSRRS"  : [ "CSR Access" , "i" , "xxxxxxx", "010", "1110011", "RV32I", "1", 102 ],
        "CSRRC"  : [ "CSR Access" , "i" , "xxxxxxx", "011", "1110011", "RV32I", "1", 103 ],
        "CSRRWI" : [ "CSR Access" , "i" , "xxxxxxx", "101", "1110011", "RV32I", "1", 104 ],
        "CSRRSI" : [ "CSR Access" , "i" , "xxxxxxx", "110", "1110011", "RV32I", "1", 105 ],
        "CSRRCI" : [ "CSR Access" , "i" , "xxxxxxx", "111", "1110011", "RV32I", "1", 106 ]
        }

rv64i = {
        "LWU"   : [ "Loads"     , "i" , "xxxxxxx", "110", "0000011", "RV64I", "1", 107 ],
        "LD"    : [ "Loads"     , "i" , "xxxxxxx", "011", "0000011", "RV64I", "1", 108 ],
        "SD"    : [ "Stores"    , "s" , "xxxxxxx", "011", "0100011", "RV64I", "1", 109 ],
        "SLLI"  : [ "Shifts"    , "r1", "000000x", "001", "0010011", "RV64I", "0", 600 ],
        "SRLI"  : [ "Shifts"    , "r1", "000000x", "101", "0010011", "RV64I", "0", 601 ],
        "SRAI"  : [ "Shifts"    , "r1", "010000x", "101", "0010011", "RV64I", "0", 602 ],
        "ADDIW" : [ "Arithmetic", "i" , "xxxxxxx", "000", "0011011", "RV64I", "0", 603 ],
        "SLLIW" : [ "Shifts"    , "r" , "0000000", "001", "0011011", "RV64I", "0", 604 ],
        "SRLIW" : [ "Shifts"    , "r" , "0000000", "101", "0011011", "RV64I", "0", 605 ],
        "SRAIW" : [ "Shifts"    , "r" , "0100000", "101", "0011011", "RV64I", "0", 606 ],
        "ADDW"  : [ "Arithmetic", "r" , "0000000", "000", "0111011", "RV64I", "0", 607 ],
        "SUBW"  : [ "Arithmetic", "r" , "0100000", "000", "0111011", "RV64I", "0", 608 ],
        "SLLW"  : [ "Shifts"    , "r" , "0000000", "001", "0111011", "RV64I", "0", 609 ],
        "SRLW"  : [ "Shifts"    , "r" , "0000000", "101", "0111011", "RV64I", "0", 610 ],
        "SRAW"  : [ "Shifts"    , "r" , "0100000", "101", "0111011", "RV64I", "0", 611 ]
        }                                                                             
rv32m = {                                                                             
        "MUL"   : [ "Multiply"  , "r", "0000001", "000", "0110011", "RV32M", "0", 612 ],
        "MULH"  : [ "Multiply"  , "r", "0000001", "001", "0110011", "RV32M", "0", 613 ],
        "MULHSU": [ "Multiply"  , "r", "0000001", "010", "0110011", "RV32M", "0", 614 ],
        "MULHU" : [ "Multiply"  , "r", "0000001", "011", "0110011", "RV32M", "0", 615 ],
        "DIV"   : [ "Divide"    , "r", "0000001", "100", "0110011", "RV32M", "0", 616 ],
        "DIVU"  : [ "Divide"    , "r", "0000001", "101", "0110011", "RV32M", "0", 617 ],
        "REM"   : [ "Remainder" , "r", "0000001", "110", "0110011", "RV32M", "0", 618 ],
        "REMU"  : [ "Remainder" , "r", "0000001", "111", "0110011", "RV32M", "0", 619 ]
        }
rv64m = {
        "MULW"  : [ "Multiply"  , "r", "0000001", "000", "0111011", "RV64M", "0", 800 ],
        "DIVW"  : [ "Divide"    , "r", "0000001", "100", "0111011", "RV64M", "0", 801 ],
        "DIVUW" : [ "Divide"    , "r", "0000001", "101", "0111011", "RV64M", "0", 802 ],
        "REMW"  : [ "Remainder" , "r", "0000001", "110", "0111011", "RV64M", "0", 803 ],
        "REMUW" : [ "Remainder" , "r", "0000001", "111", "0111011", "RV64M", "0", 804 ]
        }
rv32a = {
   "LR.W"     : [ "Load Reserved" , "r2", "00010xx", "010", "0101111", "RV32A", "1", 110 ],
   "SC.W"     : [ "Store Cond"    , "r2", "00011xx", "010", "0101111", "RV32A", "1", 111 ],
   "AMOSWAP.W": [ "Swap Atomic"   , "r2", "00001xx", "010", "0101111", "RV32A", "1", 112 ],
   "AMOADD.W" : [ "Add Atomic"    , "r2", "00000xx", "010", "0101111", "RV32A", "1", 113 ],
   "AMOXOR.W" : [ "Logical Atomic", "r2", "00100xx", "010", "0101111", "RV32A", "1", 114 ],
   "AMOAND.W" : [ "Logical Atomic", "r2", "01100xx", "010", "0101111", "RV32A", "1", 115 ],
   "AMOOR.W"  : [ "Logical Atomic", "r2", "01000xx", "010", "0101111", "RV32A", "1", 116 ],
   "AMOMIN.W" : [ "Min/Max Atomic", "r2", "10000xx", "010", "0101111", "RV32A", "1", 117 ],
   "AMOMAX.W" : [ "Min/Max Atomic", "r2", "10100xx", "010", "0101111", "RV32A", "1", 412 ],
   "AMOMINU.W": [ "Min/Max Atomic", "r2", "11000xx", "010", "0101111", "RV32A", "1", 413 ],
   "AMOMAXU.W": [ "Min/Max Atomic", "r2", "11100xx", "010", "0101111", "RV32A", "1", 400 ]
   }
rv64a = {
   "LR.D"     : [ "Load Reserved" , "r2", "00010xx", "011", "0101111", "RV64A", "1", 401 ],
   "SC.D"     : [ "Store Cond"    , "r2", "00011xx", "011", "0101111", "RV64A", "1", 402 ],
   "AMOSWAP.D": [ "Swap Atomic"   , "r2", "00001xx", "011", "0101111", "RV64A", "1", 403 ],
   "AMOADD.D" : [ "Add Atomic"    , "r2", "00000xx", "011", "0101111", "RV64A", "1", 404 ],
   "AMOXOR.D" : [ "Logical Atomic", "r2", "00100xx", "011", "0101111", "RV64A", "1", 405 ],
   "AMOAND.D" : [ "Logical Atomic", "r2", "01100xx", "011", "0101111", "RV64A", "1", 406 ],
   "AMOOR.D"  : [ "Logical Atomic", "r2", "01000xx", "011", "0101111", "RV64A", "1", 407 ],
   "AMOMIN.D" : [ "Min/Max Atomic", "r2", "10000xx", "011", "0101111", "RV64A", "1", 408 ],
   "AMOMAX.D" : [ "Min/Max Atomic", "r2", "10100xx", "011", "0101111", "RV64A", "1", 409 ],
   "AMOMINU.D": [ "Min/Max Atomic", "r2", "11000xx", "011", "0101111", "RV64A", "1", 410 ],
   "AMOMAXU.D": [ "Min/Max Atomic", "r2", "11100xx", "011", "0101111", "RV64A", "1", 411 ]
        }


#privileged register list
#priv_reg = [ "ustatus","uie","utvec","uscratch","uepc","ucause","utval","uip","fflags","frm","fcsr","cycle","time","instret","hpmcounter3","cycleh","timeh","instreth","hpmcounter3h","sstatus","sedeleg","sideleg","sie","stvec","scounteren","sscratch","sepc","scause","sip","satp","mvendorid","marchid","mimpid","mhartid","mstatus","misa","medeleg","mideleg","mie","mtvec","mcounteren","mscratch","mepc","mcause","mip","pmpcfg0","pmpcfg1","pmpcfg2","pmpcfg3","pmpaddr0","mcycle","minstret","mhpmcounter3","mcycleh","minstreth","mhpmcounter3h","mhpmevent3","tselect","tdata1","tdata2","tdata3","dcsr","dpc","dpc"] 
#list that doesnt cause exceptions:
priv_reg = [ "sstatus","sie","stvec","scounteren","sscratch","sepc","scause"\
            ,"sip","satp","mstatus","misa","medeleg","mideleg","mie","mtvec"\
            ,"mcounteren","mscratch","mepc","mcause","mip","mcycle","minstret"\
            ,"mhpmcounter3","tselect","tdata1","tdata2","tdata3" ]

#privileged registers not recognized by the toolchain: mtval, mcountinhibit, dscratch0, dscratch1, stval



#nop instrn
nop_inst_bin_32 = "{0:032b}".format(int("00000013",16))


inst_compile_issue = ['BEQ', 'BNE', 'BLT', 'BGE', 'BLTU', 'BGEU']
inst_sim_issue_0 = ['JAL', 'JALR'] # processor is jumping around when simulated
#inst_sim_issue_1 = ['LB', 'LH', 'LW', 'LBU', 'LHU', 'SB', 'SH', 'SW'] #exceptions
inst_sim_issue_1 = ['LH', 'LW', 'LHU', 'SH', 'SW', 'LWU', 'LD', 'SD', 'SB'] #exceptions
inst_sim_issue_2 = ['CSRRW', 'CSRRS', 'CSRRC', 'CSRRWI', 'CSRRSI', 'CSRRCI']
                                    #exceptions when simulated
inst_sim_issue_4 = ['FENCE.I', 'ECALL', 'EBREAK'] # couldnt include in prev itrn
amo_types = ['SWAP', 'ADD', 'XOR', 'AND', 'OR', 'MIN', 'MAX', 'MINU', 'MAXU']
amo_inst = ['LR', 'SC'] + ['AMO'+x for x in amo_types]
inst_sim_issue_3 = [x+'.W' for x in amo_inst] + [x+'.D' for x in amo_inst]
                                    #simulation getting stuck
inst_single_line = inst_compile_issue + inst_sim_issue_0 + inst_sim_issue_1   #instructions which are generated when create_prog_sing_inst=1
#inst_compile_issue = []
                                        #inst gets compiled as other multi inst


                                        
# select which extensions to include:
# inst_isa = { "rv32i": [rv32i,1], "rv64i": [rv64i,1]
#             ,"rv32m": [rv32m,1], "rv64m": [rv64m,1]
#             ,"rv32a": [rv32a,1], "rv64a": [rv64a,1]
#         }
inst_isa = { "rv32i": rv32i, "rv64i": rv64i
            ,"rv32m": rv32m, "rv64m": rv64m
            ,"rv32a": rv32a, "rv64a": rv64a
        }

#create the dict of instrns: 
#***make sure that rv64i overwrites rv32i fr instsns like SLLI***
# inst_list_all = {}
# inst_list_all_w_ext = {}
# inst_list_full = {}
# inst_list = {}
# for ext,ext_data in inst_isa.items():
#     if ext_data[1] == 0:  #skip this extension
#         continue
#     ext_dict = ext_data[0]
#     for inst, inst_data in ext_dict.items():
#         inst_list_all[inst] = inst_data
#         inst_list_all_w_ext[(inst, ext)] = inst_data

#inst_list_full = copy.deepcopy(inst_list_all)
#if rm_insts:
#    for inst in inst_compile_issue + inst_sim_issue_0 + inst_sim_issue_1\
#                                   + inst_sim_issue_2 + inst_sim_issue_3\
#                                   + inst_sim_issue_4: 
#        try:
#            del inst_list_full[inst]
#        except KeyError:
#            print(inst, " not there to delete")
