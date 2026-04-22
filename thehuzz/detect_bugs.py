"""
- TODOs: 
    - Handle dont cares when converting hex to int
"""

import subprocess, os, re, json, sys
from tqdm import tqdm
import copy, multiprocessing as mp
from string import Template
from pprint import pprint

import thehuzz_utils as TU

"""
Global variables related to the trace files
"""
rtl_start_line_re = { 'boom': f"^3 0x0000000080000000 \(0x00000093\) x 1 0x0000000000000000"\
                    , 'rc'  : f"^C0:[ ]+\d+ \[1\] pc=\[0000000080000000\](.*)inst=\[00000093\] DASM\(00000093\)"\
                    , 'cva6': f"^[ ]+1837ns[ ]+1056 M 0000000080000000 0 ([\da-z]+) [c\.]*li[ ]+ra, 0[ ]+ra  :0000000000000000"\
                    , 'boomp': f"^3 0x0000000080000000 \(0x00000093\) x 1 0x0000000000000000" }
emu_start_line_re = { 'spike':f"^core   0: 0x0000000080000000 \(0x[\da-z]+\) [c\.]*li[ ]+ra, 0" } # this can be compressed or normal inst
ex_handle_start_inst_inst_hex = int("ff810113", 16) # from riscv software
ex_handle_start_inst = int("800000e0", 16) # from riscv software
ex_handle_mcause_inst = int("342020f3", 16) # from riscv software 
ex_handle_mcause_inst_i = 3 # from riscv software
ex_handle_mepc_inst = int("341020f3", 16) # from riscv software
ex_handle_mepc_inst_i = 4 # from riscv software
float_csr_regs = ["fcsr", "fflags", "frm"] # from riscv isa
load_insts = ["ld", "c.ld", "c.lw", "lbu", "c.fld", "lb", "lhu", "lw"] # from riscv isa
store_insts = ["sb", "sd", "sw", "c.sw", "c.sd", "c.fsd", "fsw"] # from riscv isa
amo_load_insts = [f"amo{i}.{j}" for i in ['swap', 'add', 'xor', 'and', 'or', 'min', 'max', 'minu', 'maxu'] for j in ['d', 'w']]
amo_store_insts = [f"amo{i}.{j}" for i in ['swap', 'add', 'xor', 'and', 'or', 'min', 'max', 'minu', 'maxu'] for j in ['d', 'w']]
csr_read_insts = ["csrrs", "csrrw", "csrrwi", "csrrc"] # from riscv isa
csr_insts = ["csrrs", "csrrw", "csrrwi", "csrrc", "csrs", "csrw"] # from riscv isa
mult_insts = ["mulw"] # from riscv isa
div_insts = ["div"] # from riscv isa
float_rm_insts = [f"f{i}m{j}.{k}" for i in ['', 'n'] for j in ['add', 'sub'] for k in ['d', 's']] # from riscv isa
ex_no_tval_spike = ["trap_machine_ecall"] 
spike_no_3_0x_line_insts = ["wfi"]
boom_throw_ex_insts = [int("9002",16), int("100073",16), int("73",16)]
boom_rand_regs = ["scounteren"]
boom_0_regs = ["tdata1"]
rc_end_of_nops_inst_no = 77
exception_types = { 'trap_instruction_address_misaligned': 0\
                 , 'trap_instruction_access_fault': 1\
                 , 'trap_illegal_instruction': 2\
                 , 'trap_load_address_misaligned': 4\
                 , 'trap_load_access_fault': 5\
                 , 'trap_store_address_misaligned': 6\
                 , 'trap_store_access_fault': 7\
                 , 'trap_instruction_page_fault': 12\
                 , 'trap_load_page_fault': 13\
                 , 'trap_store_page_fault': 15\
        }


# from boootrom/arine.dts file
#reg = <0x0 0x80000000 0x0 0x10000000>;
#reg = <0x0 0x2000000 0x0 0xc0000>;
#//   reg = <0x0 0xc000000 0x0 0x4000000>; --> this is commented out
#reg = <0x0 0x0 0x0 0x1000>;
#reg = <0x0 0x10000000 0x0 0x1000>;
# 363_29: ariane throws page fault fr outside range!!
# 82_100: ariane works fine outside range!!!
ariane_valid_addr_ranges = [[int("80000000", 16),int("8fffffff", 16)]\
                          , [int("02000000", 16),int("020bffff", 16)]\
                          , [int("00000000", 16),int("00000fff", 16)]\
                          , [int("10000000", 16),int("10000fff", 16)] ]

# from encoding.h file
#define DEFAULT_RSTVEC     0x00001000
#define CLINT_BASE         0x02000000
#define CLINT_SIZE         0x000c0000
#define EXT_IO_BASE        0x40000000
#define DRAM_BASE          0x80000000
spike_valid_addr_ranges = [[int("00001000", 16),int("00001fff", 16)]\
                         , [int("02000000", 16),int("020bffff", 16)]\
                         , [int("40000000", 16),int("4fffffff", 16)]\
                         , [int("80000000", 16),int("8fffffff", 16)] ]

rtl_inst_data_template = {"priv_lvl"        : ""    , "pc"      : ""\
                        , "inst_hex"        : -1    , "rest"    : ""\
                        , "trace_file_line_no": -1  , "ex"      : False\
                        , "ex_pc"           : ""    , "ex_cause": None\
                        , "ex_tval"         : None  , "ex_cause_string": None\
                        , "wreg"            : -1    , "wdata"   : None\
                        , "wreg_type"       : ""    , "write_en": None\
                        , "op1_reg"         : -1    , "op1_data": None\
                        , "op1_reg_type"    : ""\
                        , "op2_reg"         : -1    , "op2_data": None\
                        , "op2_reg_type"    : ""\
                        , "got_end_of_inst" : False , "core_no" : None\
                        , "reg_data"        : {}}

emu_inst_data_template = {"priv_lvl"        : ""    , "pc"      : ""\
                        , "inst_hex"        : -1    , "inst"    : ""\
                        , "rest_1"          : ""    , "rest_2"  : ""\
                        , "line_types"      : []    , "ex"      : False\
                        , "ex_type"         : ""    , "ex_tval" : None\
                        , "ex_pc"           : ""    , "ex_cause": None\
                        , "trace_file_line_no": -1\
                        , "wreg"            : -1    , "wdata"   : None\
                        , "wreg_type"       : ""\
                        , "mem_addr"        : ""    , "mem_data": ""\
                        , "got_end_of_inst" : False }

comp_inst_data_template = {"rtl_data"       : ""    , "emu_data"    : ""\
                         , "has_mm"         : False , "mms"         : []\
                         , "inst_no"        : False}

# regular expression shortcuts
br = "([01])" # binary field
nr = "(\d+)" # number 
hr = "([\da-f]+)" # hex num
ar = "([A-Za-z_\.]*)"  # instr name, * bcz sometimes there is no inst name
rr = "([A-Za-z0-9,: \-\(\)]*)" # all??
fr = "([a-zA-Z_0-9]+)" # name of func


"""
"""
def reg_no_to_id(reg_no, reg_type):
    x_mapping = ['zero', 'ra', 'sp', 'gp', 'tp', 't0', 't1', 't2', 's0', 's1'] 
    x_mapping += [f"a{i}" for i in range(8)]
    x_mapping += [f"s{i}" for i in range(2,12)]
    x_mapping += [f"t{i}" for i in range(3,7)]
    f_mapping = []
    f_mapping += [f"ft{i}" for i in range(8)]
    f_mapping += [f"fs{i}" for i in range(2)]
    f_mapping += [f"fa{i}" for i in range(8)]
    f_mapping += [f"fs{i}" for i in range(2,12)]
    f_mapping += [f"ft{i}" for i in range(8,12)]

    if reg_type == 'x': return x_mapping[reg_no]
    else: return f_mapping[reg_no]

"""
"""
def check_equal(val1, val2, assert_str):
    assert val1 == val2, f"{assert_str}, {val1}, {val2}"


"""
"""
def in_addr_range(addr, addr_ranges): 
    return any([((addr >= min_addr) and (addr <= max_addr)) for min_addr, max_addr in addr_ranges])


"""
Parses a line from rtl trace
 ===== MemorySystem 0 =====
 CH. 0 TOTAL_STORAGE : 4096MB | 1 Ranks | 16 Devices per rank
 DRAMSi
 ---------------------------------------------------------------------------
 VCS Coverage Metrics: during simulation line, cond, FSM, branch, tgl was monitored
 ---------------------------------------------------------------------------
            V C S   S i m u l a t i o n   R e p o r t 
Time: 3400000 ps
CPU Time:      9.420 seconds;       Data structure size:   6.8Mb
Mon May  9 21:10:53 2022
0010058 (0x00028463)
3 0x000000000001005c (0x30301073)
3 0x0000000000010060 (0x00800513) x10 0x0000000000000008
3 0x0000000000010064 (0x30451073)
"""
def parse_boom_rtl_trace_line(rtl_trace_file_name, line, inst_data, line_i):
    nr = "(\d+)" # number of reg expre at the begin of the line
    hr = "([\da-f]+)" # hex num reg expr
    ar = "([A-Za-z_\.]*)"  # sometimes there is no inst name
    rr = "([A-Za-z0-9,: \-\(\)]*)"
    line_type_1_re = [ "^Command: "\
                    , f"^ VCS Coverage Metrics Release"\
                    , f"^[UART] UART0"\
                    , f"^testing \$random"\
                    , f"^== Loading "\
                    , f"^===== MemorySystem 0"\
                    , f"^CH. 0 TOTAL_STORAGE"\
                    , f"^DRAMSi", "^-------------", "^VCS Coverage Metrics: "\
                    , "[ ]+V C S   S i m", "^Time: ", "^CPU Time: "\
                    , "^Thu ", "^Mon ", "^ 0x00000000"\
                    , "^$", " Coverage status: ", "\*\*\* PASSED"\
                    , "simv-chipyard-SmallBoomConfig", "\*\*\* FAILED"\
                    , "Assertion failed: ", "at (.*) assert"\
                    , "^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)"] 

    line_type_2_re = f"^{nr} 0x{hr} \(0x{hr}\)(.*)"
    line_type_2_1_re = f"^{nr} 0x{hr} \(0x{hr}\) ([xf])[ ]*{hr} 0x{hr}"

    # filter out unwanted lines
    if any([re.search(re_string, line) for re_string in line_type_1_re]):
        return inst_data

    elif (re.search(line_type_2_re, line)): 
        line_data = re.search(line_type_2_re, line)
        inst_data["priv_lvl"] = line_data.group(1)
        inst_data["pc"] = line_data.group(2)
        inst_data["inst_hex"] = int(line_data.group(3), 16)
        inst_data["rest"] = line_data.group(4)

        inst_data["got_end_of_inst"] = True # since this is not exception instrn, this is the end fr this inst

        if (re.search(line_type_2_1_re, line)):
            line_data = re.search(line_type_2_1_re, line)
            inst_data["wreg_type"] = line_data.group(4)
            inst_data["wreg"] = int(line_data.group(5))
            inst_data["wdata"] = int(line_data.group(6), 16)
        else: 
            check_equal(inst_data["rest"], ""\
              , f"{rtl_trace_file_name}: found new rest of inst in rtl trace, {line_i}")

    else: 
        assert 0, f"{rtl_trace_file_name}: found new rtl trace line pattern, {line}"

    return inst_data


"""
Parses a line from rocket core rtl trace
C0:       1052 [1] pc=[0000000080000000] W[r 1=0000000000000000][1] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[00000093] DASM(00000093)
C0:       1053 [1] pc=[0000000080000004] W[r 2=0000000000000000][1] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[00000113] DASM(00000113)

C0:       1379 [0] pc=[00000000800025c8] W[r29=0000000000000000][0] R[r28=0000000000000000] R[r 0=0000000000000000] inst=[9ace4e83] DASM(9ace4e83)
C0:       1384 [1] pc=[00000000800000e0] W[r 2=0000000080022918][1] R[r 2=0000000080022920] R[r 0=0000000000000000] inst=[ff810113] DASM(ff810113)
C0:       1410 [1] pc=[00000000800000e4] W[r 0=0000000000000000][0] R[r 2=0000000080022918] R[r 1=0000000080002228] inst=[00113423] DASM(00113423)
C0:       1411 [1] pc=[00000000800000e8] W[r 1=0000000000000005][1] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[342020f3] DASM(342020f3)
C0:       1414 [1] pc=[00000000800000ec] W[r 1=00000000800025c8][1] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[341020f3] DASM(341020f3)
C0:       1417 [1] pc=[00000000800000f0] W[r 1=00000000800025cc][1] R[r 1=00000000800025c8] R[r 0=0000000000000000] inst=[00408093] DASM(00408093)
C0:       1418 [1] pc=[00000000800000f4] W[r 0=00000000800025c8][1] R[r 1=00000000800025cc] R[r 0=0000000000000000] inst=[34109073] DASM(34109073)
C0:       1419 [1] pc=[00000000800000f8] W[r 1=0000000080002228][1] R[r 2=0000000080022918] R[r 0=0000000000000000] inst=[00813083] DASM(00813083)
C0:       1420 [1] pc=[00000000800000fc] W[r 2=0000000080022920][1] R[r 2=0000000080022918] R[r 0=0000000000000000] inst=[00810113] DASM(00810113)
C0:       1452 [1] pc=[0000000080000100] W[r 0=0000000000000000][0] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[30200073] DASM(30200073)
 1         2    3           4              5 6    7              8    9 10        11         12 13   14                       15             16
"""
def parse_rc_rtl_trace_line(rtl_trace_file_name, line, inst_data, line_i):
    line_type_1_re = [ "^-------------", "^VCS Coverage Metrics: "\
                    , "^$", " Coverage status: ", "\*\*\* PASSED"\
                    , "simv-chipyard-SmallBoomConfig", "\*\*\* FAILED"\
                    , "Assertion failed: ", "at (.*) assert"\
                    ,  "^testing $random "\
                    , f"^== Loading "\
                    , f"^===== MemorySystem 0"\
                    , f"^CH. 0 TOTAL_STORAGE"\
                    , f"^DRAMSi"\
                    , "^[ ]+V C S", "^Time:", "^CPU Time:"\
                    , "^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)"] # unwanted lines in trace file

    reg_re = f"\[([rf])[ ]*{nr}={hr}\]" # register field regex
    line_type_2_re = f"^C{nr}:[ ]+{nr} \[{br}\] pc=\[{hr}\] W{reg_re}\[{br}\] R{reg_re} R{reg_re} inst=\[{hr}\] DASM\({hr}\)"

    # filter out unwanted lines
    if any([re.search(re_string, line) for re_string in line_type_1_re]):
        return inst_data

    elif (re.search(line_type_2_re, line)): 
        line_data = re.search(line_type_2_re, line)
        inst_data["core_no"] = line_data.group(1)
        inst_data["ex"] = (line_data.group(3) == "0")
        inst_data["pc"] = line_data.group(4)
        inst_data["inst_hex"] = int(line_data.group(15), 16)

        inst_data["write_en"] = (line_data.group(8) == "1")
        if inst_data["write_en"]: 
            inst_data["wreg_type"] = "x" if (line_data.group(5) == "r") else line_data.group(5) # emu uses x instead of r
            inst_data["wreg"] = int(line_data.group(6))
            inst_data["wdata"] = int(line_data.group(7), 16)

        inst_data["op1_reg_type"] = line_data.group(9)
        inst_data["op1_reg"] = int(line_data.group(10))
        inst_data["op1_data"] = int(line_data.group(11), 16)

        inst_data["op2_reg_type"] = line_data.group(12)
        inst_data["op2_reg"] = int(line_data.group(13))
        inst_data["op2_data"] = int(line_data.group(14), 16)

        inst_data["got_end_of_inst"] = True # trace for all instrs is only 1 line for rc

    else: 
        assert 0, f"{rtl_trace_file_name}: found new rtl trace line pattern, {line}"

    return inst_data


"""
    1053ns      272 M 0000000000010040 0 00000517 auipc          a0, 0x0               a0  :0000000000010040
    1063ns      282 M 0000000000010044 0 fc050513 addi           a0, a0, -64           a0  :0000000000010000 a0  :0000000000010040
    1073ns      292 M 0000000000010048 0 30551073 csrw           a0, mtvec             a0  :0000000000010000

    1153ns      372 M 0000000000010068 0 30052073 csrrs          a0, mstatus           a0  :0000000000000008
Exception @   1172000, PC: 000000000001006c, Cause: Machine Software Interrupt
    1193ns      412 M 0000000000010000 0 020005b7 lui            a1, 0x2000            a1  :0000000002000000

    3321ns     2540 M 000000008000027c 0 03ce5cb3 divu           s9, t3, t3            s9  :ffffffffffffffff t3  :0000000000000000 t3  :0000000000000000
    3323ns     2542 M 0000000080000280 0 d5988e23 sb             s9, -676(a7)          s9  :ffffffffffffffff a7  :0000000000000000 VA: fffffffffffffd5c PA: fffffffffffd5c

    3370ns     2589 M 0000000080000294 0 140c1a73 csrrw          s4, s8, sscratch      s4  :0000000000000000 s8  :0000000000000000
Exception @   3372000, PC: 0000000080000298, Cause: Store Address Misaligned, 
                tval: 000000008000020e
    3399ns     2618 M 0000000080000140 0 34011073 csrw           sp, mscratch          sp  :0000000080028ff0

    ... fsw            x0, 0(x0)             VA: xxxxxxxxxxxxxxxx PA: 00000000000000
"""
def parse_cva6_rtl_trace_line(rtl_trace_file_name, line, inst_data, line_i):
    br = "([01])" # binary field
    nr = "(\d+)" # number of reg expre at the begin of the line
    hr = "([\da-fx]+)" # hex num reg expr # hex value can sometomes be xxxxxx
    ar = "([A-Za-z_\.]*)"  # sometimes there is no inst name
    sp = "[ \t]+" # space
    tr = "([a-zA-Z ]+)" # text
    rr = "([A-Za-z0-9,: \-\(\)]*)"
    line_type_1_re = []  # re of unwanted lines

    reg_re = f"[ ]+([a-zA-Z0-9]+)[ ]*:[ ]*{hr}" # re for reg and its data in the log
    line_type_2_re = f"{sp}{nr}ns{sp}{nr} ([MUS]) {hr} {br} {hr}(.*)"
    line_type_3_re = f"^Exception"
    line_type_3_1_re = f"^Exception @{sp}{hr}, PC:{sp}{hr},{sp}Cause:{sp}{tr}(,*)"
    line_type_4_re = f"^{sp}tval:{sp}{hr}"

    # there could be 0 to 4 reg values per inst in the log
    max_regs_per_line = 4
    rest_inst_log_re = {}
    for i in range(max_regs_per_line+1): 
        rest_inst_log_re[i] = f"^([^:]*){reg_re*i}(.*)"
    #print(rest_inst_log_re); exit()

    # filter out unwanted lines
    if any([re.search(re_string, line) for re_string in line_type_1_re]):
        return inst_data

    elif (re.search(line_type_2_re, line)): 
        line_data = re.search(line_type_2_re, line)
        inst_data["priv_lvl"] = line_data.group(3) 
        inst_data["ex"] = False # inst are only logged if they are not ex
        inst_data["pc"] = line_data.group(4)
        inst_data["inst_hex"] = int(line_data.group(6), 16)

        rest_inst_log = line_data.group(7)

        # extract any reg data from rest of inst log
        for i in range(max_regs_per_line, -1, -1): # need to go from max regs bcz regex matches lower
                                   # reg count also
            rest_inst_data = re.search(rest_inst_log_re[i], rest_inst_log)
            if rest_inst_data: 
                break
        assert rest_inst_data, f"{rtl_trace_file_name}: new reg format found in reg log line, \n{line}\n{rest_inst_log}\n{i}"
        assert rest_inst_data.group(1+(i*2)+1)=="", f"{rtl_trace_file_name}: new reg format found in reg log line, \n{line}\n{rest_inst_log}\n{i}"
        #print(rest_inst_log, i, rest_inst_data)
       
        inst_data["rest"] = rest_inst_data.group(1) # this is dasm of inst
 
        for reg_i in range(i):  
            reg_id = rest_inst_data.group(1+(reg_i*2)+1)
            reg_value_hex = rest_inst_data.group(1+(reg_i*2)+2)
            if not 'x' in reg_value_hex:  # handle dontcares
                reg_value = int(reg_value_hex, 16)
            else: 
                reg_value = -1
            # there can be same reg two times as source and dest reg, handle 
            # that case by recording both values
            # ex: addi  t0, t0, 144  t0  :00000000800000d4 t0  :0000000080000044
            #  {'t0': ['00000000800000d4', '0000000080000044']}
            if reg_id in inst_data["reg_data"].keys():
                inst_data["reg_data"][reg_id].append(reg_value)
            else: 
                inst_data["reg_data"][reg_id] = [reg_value]

        #print(rest_inst_log, i, inst_data["reg_data"])

        inst_data["got_end_of_inst"] = True # since this is not exception instrn, this is the end fr this inst

    elif (re.search(line_type_3_re, line)): 
        inst_data["ex"] = True

        if (re.search(line_type_3_1_re, line)):
            line_data = re.search(line_type_3_1_re, line)
            inst_data["pc"] = line_data.group(2)
            inst_data["ex_pc"] = line_data.group(2)
            inst_data["ex_cause_string"] = line_data.group(3)
            inst_data["got_end_of_inst"] = (line_data.group(4) != ',')
        else: 
            assert 0, f"{rtl_trace_file_name}: found new ex rtl trace line pattern,\n{line}"

    elif (re.search(line_type_4_re, line)): 
        assert inst_data["ex"], f"{rtl_trace_file_name}, got tval line before exception line\n{line_i}:{line} "
        line_data = re.search(line_type_4_re, line)
        inst_data["ex_tval"] = line_data.group(1)
        inst_data["got_end_of_inst"] = True

    else: 
        assert 0, f"{rtl_trace_file_name}: found new rtl trace line pattern,\n{line}"

    return inst_data


"""
Parses the rtl trace log file
"""
def parse_rtl_trace_file(rtl_trace_file, core): 
    
    with open(rtl_trace_file, 'r') as fp: lines = fp.readlines()

    rtl_trace_file_name = os.path.basename(rtl_trace_file)
    rtl_inst_data = []
    inst_data = copy.deepcopy(rtl_inst_data_template)
    line_i = 0

    # ignore the lines till we jump to dram
    while not re.search(rtl_start_line_re[core], lines[line_i]): 
        line_i += 1
        assert line_i < len(lines), f"{rtl_trace_file_name}: reached rtl trace end of file before jumping to dram, {line_i}, {len(lines)}"
    
    # parse each line
    for line_j, line in enumerate(lines[line_i:], line_i+1): # +1 bcz line nos start with 1 in the file
        inst_data["trace_file_line_no"] = line_j
        if core in ["boom", "boomp"]: 
            inst_data = parse_boom_rtl_trace_line(rtl_trace_file_name, line, inst_data, line_j)
        elif core == "rc": 
            inst_data = parse_rc_rtl_trace_line(rtl_trace_file_name, line, inst_data, line_j)
        elif core == "cva6": 
            inst_data = parse_cva6_rtl_trace_line(rtl_trace_file_name, line, inst_data, line_j)
        else: assert 0, f'unknown core: {core} found' 

        if inst_data["got_end_of_inst"]: # trace for current instruction is over
            rtl_inst_data.append(copy.deepcopy(inst_data)) # save instruction data
            inst_data = copy.deepcopy(rtl_inst_data_template) # create a new instruction template for next instr

    return rtl_inst_data


"""
Parses a line from emu trace
core   0: 0x0000000080000000 (0x00000093) li      ra, 0
core   0: 3 0x0000000080000000 (0x00000093) x 1 0x0000000000000000

core   0: 0x000000008000223c (0x00893683) ld      a3, 8(s2)
core   0: 3 0x000000008000223c (0x00893683) x13 0x00007fc1bb000000 mem 0x0000000080002970
core   0: 3 0x00000000800025c8 (0x02ad8853) c768_mstatus 0x8000000a00006000 f16 0x7ff8000000000000

core   0: >>>>  _start

- exception0: 
    core   0: 0x00000000800025d6 (0xc709a673) csrrs   a2, unknown_c70, s3
    core   0: exception trap_illegal_instruction, epc 0x00000000800025d6
    core   0:           tval 0x0000000000000000
- exception1
    core   0: exception trap_instruction_access_fault, epc 0x0000000000006000
    core   0:           tval 0x0000000000006000
Note: 
    - inst hex value can have extra 0's in string, so, using int fr it
        core   0: 0x00000000800025cc (0x0000c709) c.beqz  a4, pc + 10
        core   0: 3 0x00000000800025cc (0xc709)
"""
def parse_emu_trace_line(emu_trace_file_name, line, inst_data, line_i, prev_inst_data):
    csr = "([a-z_0-9]+)" # ex: c768_mstatus
    line_type_0_re = [f"^core   0: >>>>  {fr}"]
    line_type_1_re = f"^core   0: 0x{hr} \(0x{hr}\) {ar}(.*)"
    line_type_2_re = f"^core\s+0:\s{nr} 0x{hr} \(0x{hr}\)(.*)"
    line_type_2_0_re = f"^core\s+0:\s{nr} 0x{hr} \(0x{hr}\) ([xf])[ ]*{hr}\s+0x{hr} mem 0x{hr}"
    line_type_2_1_re = f"^core\s+0:\s{nr} 0x{hr} \(0x{hr}\) ([xf])[ ]*{hr}\s+0x{hr}"
    line_type_2_2_re = f"^core\s+0:\s{nr} 0x{hr} \(0x{hr}\) mem 0x{hr} 0x{hr}"
    line_type_2_3_re = f"^core\s+0:\s{nr} 0x{hr} \(0x{hr}\) mem 0x{hr}"
    line_type_2_4_re = f"^core\s+0:\s{nr} 0x{hr} \(0x{hr}\) {csr}\s+0x{hr} ([xf])[ ]*{hr}\s+0x{hr} mem 0x{hr}"
    line_type_2_5_re = f"^core\s+0:\s{nr} 0x{hr} \(0x{hr}\) {csr}\s+0x{hr} ([xf])[ ]*{hr}\s+0x{hr}"
    line_type_2_6_re = f"^core\s+0:\s{nr} 0x{hr} \(0x{hr}\) {csr}\s+0x{hr}"
    line_type_3_1_re = f"^core   0: exception {ar}, epc 0x{hr}"
    line_type_3_2_re = f"^core   0:[ ]+tval 0x{hr}" 

    # filter out unwanted lines
    if any([re.search(re_string, line) for re_string in line_type_0_re]):
        return inst_data

    elif (re.search(line_type_1_re, line)): 
        line_data = re.search(line_type_1_re, line)
        inst_data["line_types"].append("1")

        # check that this is the first line in the inst
        assert inst_data["line_types"] == ["1"]\
              , f"{emu_trace_file_name}: core 0 inst line appeared after some other line in emu trace, {line_i}, {inst_data['line_types']}"

        inst_data["pc"] = line_data.group(1)
        inst_data["inst_hex"] = int(line_data.group(2), 16)
        inst_data["inst"] = line_data.group(3)
        inst_data["rest_1"] = line_data.group(4)

        if inst_data["inst"] in spike_no_3_0x_line_insts: 
            inst_data["got_end_of_inst"] = True # fr some insts, there will be no 3 0x ... line
        else: 
            inst_data["got_end_of_inst"] = False # since this is core line, there will be 3 0x ... line

    elif (re.search(line_type_2_re, line)): 
        line_data = re.search(line_type_2_re, line)
        inst_data["line_types"].append("2")

        if prev_inst_data and (prev_inst_data["pc"] == line_data.group(2)): 
            # if we are stuck in loop, then spike may not have the core 0: 0x... line
            assert inst_data["line_types"] in [["1",'2'],["2"]]\
                  , f"{emu_trace_file_name}: 3 0x... inst line appeared in wrong time in emu trace, {line_i}, {inst_data['line_types']}"
        else: 
            # check that this line is after core 0 inst line
            check_equal(inst_data["line_types"], ["1", "2"]\
                  , f"{emu_trace_file_name}: 3 0x... inst line appeared in wrong time in emu trace, {line_i}")

        if prev_inst_data and (prev_inst_data["pc"] == line_data.group(2)): 
            inst_data["pc"] = line_data.group(2)
            inst_data["inst_hex"] = int(line_data.group(3), 16)

        inst_data["priv_lvl"] = line_data.group(1)
        check_equal(line_data.group(2), inst_data["pc"], f"{emu_trace_file_name}: pc mismatch in emu trace, {line_i}")
        check_equal(int(line_data.group(3),  16), inst_data["inst_hex"], f"{emu_trace_file_name}: inst_hex mismatch in emu trace, {line_i}")
        inst_data["rest_2"] = line_data.group(4)

        inst_data["got_end_of_inst"] = True # since this is 3 0x ... line, the inst is over
        
        if (re.search(line_type_2_0_re, line)):
            line_data = re.search(line_type_2_0_re, line)
            inst_data["wreg_type"] = line_data.group(4)
            inst_data["wreg"] = int(line_data.group(5))
            inst_data["wdata"] = int(line_data.group(6), 16)
            inst_data["mem_addr"] = line_data.group(7)
        elif (re.search(line_type_2_1_re, line)):
            line_data = re.search(line_type_2_1_re, line)
            inst_data["wreg_type"] = line_data.group(4)
            inst_data["wreg"] = int(line_data.group(5))
            inst_data["wdata"] = int(line_data.group(6), 16)
        elif (re.search(line_type_2_2_re, line)):
            line_data = re.search(line_type_2_2_re, line)
            inst_data["mem_addr"] = line_data.group(4)
            inst_data["mem_data"] = line_data.group(5)
        elif (re.search(line_type_2_3_re, line)):
            line_data = re.search(line_type_2_3_re, line)
            inst_data["mem_addr"] = line_data.group(4)
        elif (re.search(line_type_2_4_re, line)):
            line_data = re.search(line_type_2_4_re, line)
            inst_data["wreg_type"] = line_data.group(6)
            inst_data["wreg"] = int(line_data.group(7))
            inst_data["wdata"] = int(line_data.group(8), 16)
            inst_data["mem_addr"] = line_data.group(9)
        elif (re.search(line_type_2_5_re, line)):
            line_data = re.search(line_type_2_5_re, line)
            inst_data["wreg_type"] = line_data.group(6)
            inst_data["wreg"] = int(line_data.group(7))
            inst_data["wdata"] = int(line_data.group(8), 16)
        elif (re.search(line_type_2_6_re, line)): # no useful value from rtl
            t = 1
        else: 
            check_equal(inst_data["rest_2"], ""\
              , f"{emu_trace_file_name}: found new rest of inst in emu trace, {line_i}")

    elif (re.search(line_type_3_1_re, line)): 
        line_data = re.search(line_type_3_1_re, line)
        inst_data["line_types"].append("3_1")
        if line_data.group(1) in exception_types.keys(): 
            inst_data["ex_cause"] = exception_types[line_data.group(1)]
        else: 
            assert 0, f"{emu_trace_file_name}: unknown exception type {line_data.group(1)}, {line_i}"

        # check that this is the first line in the inst
        # there is a case where ex handler address is corrupted and we keep getting illegal inst exception, handle that case: 
        if (line_data.group(1) == "trap_illegal_instruction") and (inst_data["line_types"] == ["3_1"]) \
          and prev_inst_data["ex"] and (prev_inst_data["ex_type"] == line_data.group(1))\
          and (prev_inst_data["ex_pc"] == int(line_data.group(2),16)): 
            exp_line_order = ["3_1"]
        # similar issue can also happen with trap_load_access_fault TODO
        elif (line_data.group(1) in ["trap_load_access_fault", "trap_load_address_misaligned"]) and (inst_data["line_types"] == ["3_1"]) \
          and prev_inst_data["ex"] and (prev_inst_data["ex_type"] == line_data.group(1))\
          and (prev_inst_data["ex_pc"] == int(line_data.group(2),16)): 
            exp_line_order = ["3_1"]
        else: 
            exp_line_order = ["3_1"] if "trap_instruction_access_fault" in line else ["1","3_1"]
        check_equal(inst_data["line_types"], exp_line_order\
              , f"{emu_trace_file_name}: core 0 ex line appeared in wrong time in emu trace, {line_i}")

        inst_data["ex"] = True
        inst_data["ex_type"] = line_data.group(1)
        inst_data["ex_pc"] = int(line_data.group(2), 16)

        if inst_data["ex_type"] in ex_no_tval_spike: 
            inst_data["got_end_of_inst"] = True # for some exceptions, spike doesnt have tval line

    elif (re.search(line_type_3_2_re, line)): 
        line_data = re.search(line_type_3_2_re, line)
        inst_data["line_types"].append("3_2")

        # check that this line is after core 0: ex line
        # in this case, just check that the ex line is there before this line
        exp_line_order_last = "3_1"
        assert len(inst_data['line_types']) > 1, f"{emu_trace_file_name}: core 0 tval line appeared in wrong time in emu trace, {line_i}"
        check_equal(inst_data["line_types"][-2], exp_line_order_last\
              , f"{emu_trace_file_name}: core 0 tval line appeared in wrong time in emu trace, {line_i}")

        inst_data["ex_tval"] = line_data.group(1)

        inst_data["got_end_of_inst"] = True # since this is core 0: ex tval line

    else: 
        assert 0, f"{emu_trace_file_name}: found new emu trace line pattern, {line}"

    return inst_data


"""
Parses the emu trace log file
We only need the no of insts equal to the number of insts in the rtl (bcz spike runs fr a very long time), 
    so, stopping after max_insts no of insts
"""
def parse_emu_trace_file(emu_trace_file, emu, max_insts): 
    
    with open(emu_trace_file, 'r') as fp: lines = fp.readlines()

    emu_trace_file_name = os.path.basename(emu_trace_file)
    emu_inst_data = []
    no_insts = 0
    inst_data = copy.deepcopy(emu_inst_data_template)
    line_i = 0

    assert len(lines) > 0, f"{emu_trace_file_name}: emu trace file is empty"

    # ignore the lines till we jump to dram
    while not re.search(emu_start_line_re[emu], lines[line_i]): 
        line_i += 1
        assert line_i < len(lines), f"{emu_trace_file_name}: reached end of file before jumping to dram, {line_i}, {len(lines)}"
    
    # parse each line
    # ignore the last line since it could be incomplete based on when we stop the spike
    prev_inst_data = None
    for line_j, line in enumerate(lines[line_i:-1], line_i+1): # +1 bcz line nos start with 1 in the file 
        inst_data["trace_file_line_no"] = line_j
        inst_data = parse_emu_trace_line(emu_trace_file_name, line, inst_data, line_j, prev_inst_data)

        if inst_data["got_end_of_inst"]: # trace for current instruction is over
            emu_inst_data.append(copy.deepcopy(inst_data))
            no_insts += 1
            if no_insts == max_insts: # we only need max_insts no insts from spike
                break
            prev_inst_data = inst_data
            inst_data = copy.deepcopy(emu_inst_data_template)

    return emu_inst_data


"""
This functions runs any preprocessing before comparing the rtl and emu data. It can also be used to 
generate data that will help make ignoring mismatches easier (another function called analyse data also 
serves a similar purpose)
"""
def preprocess_data(rtl_trace_file_name, rtl_inst_data, emu_inst_data, core, emu): 
    new_rtl_inst_data = []
    new_emu_inst_data = []


    # if there are no enough lines in the rtl trace after 1st ex inst, then ignore those lines
    if core in ['rc', 'boom', 'boomp']: # cva6 doesnt need this as we dont use ex handler to get
                              # info abt exception
        for rtl_d_i, rtl_d in enumerate(rtl_inst_data): 
            if ( (int(rtl_d["pc"],16) == ex_handle_start_inst) ): 
                if rtl_d_i + ex_handle_mepc_inst_i - 1 >= len(rtl_inst_data): 
                    break
        rtl_inst_data = rtl_inst_data[:rtl_d_i-1]

    if core in ["boom", "boomp"]: 
        # rtl does not throw exception insts in some cases and does in other cases
        # add a dummy rtl inst with ex=True when rtl doesnt throw ex and change ex value to true 
        # when rtl does throw ex
        rtl_d_i = 0
        resolved_rtl_ex_insts = []
        for emu_d_i in range(len(emu_inst_data)): 
            
            # check if we need to insert the dummy rtl inst here 
            use_dummy_rtl_data = False
            is_prev_ex = False
            if ( (int(rtl_inst_data[rtl_d_i]["pc"],16) == ex_handle_start_inst)\
                    and (not rtl_d_i in resolved_rtl_ex_insts) ):
                # if the ex_mepc is same as prev inst and prev inst_hex is one of insts fr which boom throws ex, then no need
                # to add dummy ex, also no need if we already added dummy inst
                # note: ex_handle_mepc_inst_i is dist frm ex inst, but rtl_d_i here is inst after ex inst
                if (rtl_d_i + ex_handle_mepc_inst_i - 1 < len(rtl_inst_data)) and (rtl_d_i > 0):
                    rtl_d_mepc = rtl_inst_data[rtl_d_i + ex_handle_mepc_inst_i-1]
                    if ( rtl_d_mepc["wdata"] == int(rtl_inst_data[rtl_d_i-1]["pc"],16)\
                            and (rtl_inst_data[rtl_d_i-1]["inst_hex"] in boom_throw_ex_insts) ):
                        use_dummy_rtl_data = False
                        is_prev_ex = True
                    else: 
                        use_dummy_rtl_data = True
                else: 
                    use_dummy_rtl_data = True

            resolved_rtl_ex_insts.append(rtl_d_i)

            if use_dummy_rtl_data: 
                rtl_d = copy.deepcopy(rtl_inst_data_template)
                rtl_d["ex"] = True
                rtl_d["trace_file_line_no"] = rtl_inst_data[rtl_d_i]["trace_file_line_no"]
                emu_d = emu_inst_data[emu_d_i]
                # no need to increment rtl_d_i since we did not use it
            else: 
                rtl_d = rtl_inst_data[rtl_d_i]
                if is_prev_ex: 
                    new_rtl_inst_data[-1]["ex"] = True
                emu_d = emu_inst_data[emu_d_i]
                rtl_d_i += 1

            new_rtl_inst_data.append(rtl_d)
            new_emu_inst_data.append(emu_d)

            if rtl_d_i == len(rtl_inst_data): 
                break

    elif core == "rc": 
        new_rtl_inst_data = rtl_inst_data
        new_emu_inst_data = emu_inst_data

    elif core == 'cva6': 
        new_rtl_inst_data = rtl_inst_data
        new_emu_inst_data = emu_inst_data

    for inst_no, (rtl_d, emu_d) in enumerate(zip(new_rtl_inst_data, new_emu_inst_data)): 

        # get the ex cause and pc fr rtl exceptions
        if core in ['rc', 'boom', 'boomp']: # cva6 uses a diff ex handler which doesnt have this info
            if rtl_d["ex"]: 
                if inst_no + ex_handle_mcause_inst_i < len(new_rtl_inst_data):
                    rtl_d_mcause = new_rtl_inst_data[inst_no + ex_handle_mcause_inst_i]
                    if (rtl_d_mcause["inst_hex"] == ex_handle_mcause_inst): 
                        rtl_d["ex_cause"] = rtl_d_mcause["wdata"]
                    elif True in [new_rtl_inst_data[inst_no+i+1]["ex"] for i in range(ex_handle_mcause_inst_i)]: 
                        # another exception happeneded, cannot get the cause for the original exception
                        t = 1
                    elif (new_rtl_inst_data[inst_no+1]["inst_hex"] != ex_handle_start_inst_inst_hex) \
                            or (new_rtl_inst_data[inst_no+1]["pc"] != ex_handle_start_inst): 
                        # exception handler addr or data is changed, so, cannot get exception details anymore
                        t = 1
                    else: assert 0, f"{rtl_trace_file_name}: unable to find ex cause inst,\n{inst_no},{rtl_d['trace_file_line_no']},{rtl_d_mcause['inst_hex']},{ex_handle_mcause_inst} "

                if inst_no + ex_handle_mepc_inst_i < len(new_rtl_inst_data):
                    rtl_d_mepc = new_rtl_inst_data[inst_no + ex_handle_mepc_inst_i]
                    if (rtl_d_mepc["inst_hex"] == ex_handle_mepc_inst): 
                        if rtl_d["ex_pc"]:
                            assert rtl_d["ex_pc"] == rtl_d_mepc["wdata"], f"i{rtl_trace_file_name}: ex_pc not matching,\n{inst_no},{rtl_d['trace_file_line_no']},{rtl_d['ex_pc']},{rtl_d_mepc['wdata']}"
                        else: rtl_d["ex_pc"] = rtl_d_mepc["wdata"]
                    elif True in [new_rtl_inst_data[inst_no+i+1]["ex"] for i in range(ex_handle_mcause_inst_i)]: 
                        # another exception happeneded, cannot check the ex pc for the original exception
                        t = 1
                    elif (new_rtl_inst_data[inst_no+1]["inst_hex"] != ex_handle_start_inst_inst_hex) \
                            or (new_rtl_inst_data[inst_no+1]["pc"] != ex_handle_start_inst): 
                        # exception handler addr or data is changed, so, cannot get exception details anymore
                        t = 1
                    else: assert 0, f"{rtl_trace_file_name}: unable to find ex pc inst,\n{inst_no},{rtl_d['trace_file_line_no']},{rtl_d_mcause['inst_hex']},{ex_handle_mepc_inst} "

        # get the ex cause fr emu exception
        if 1: # TODO: handle this better, new spike doesnt use this handler
            if emu_d["ex"]: 
                if inst_no + ex_handle_mcause_inst_i < len(new_emu_inst_data):
                    emu_d_mcause = new_emu_inst_data[inst_no + ex_handle_mcause_inst_i]
                    if (emu_d_mcause["inst_hex"] == ex_handle_mcause_inst): 
                        if emu_d["ex_cause"] != None: 
                            assert emu_d["ex_cause"] == emu_d_mcause["wdata"], f"{rtl_trace_file_name}: exception type not matching\n{inst_no},{emu_d},{emu_d_mcause} "
                        emu_d["ex_cause"] = emu_d_mcause["wdata"]

    return new_rtl_inst_data, new_emu_inst_data


"""
"""
def is_inst_field_equal(field, rtl_val, emu_val): 
    is_equal = (rtl_val == emu_val)
    return is_equal

"""
Compare all data in one inst of rtl and emu
"""
def compare_rtl_emu_one_inst(rtl_trace_file_name, rtl_d, emu_d, comp_d, core): 
    is_equal = True

    for field, rtl_val in rtl_d.items(): 

        if field in ["priv_lvl", "rest", "trace_file_line_no", "ex_cause_string"\
                   , "core_no"\
                   , "write_en", "op1_reg", "op1_data", "op1_reg_type"\
                   , "op2_reg", "op2_data", "op2_reg_type"]:   # these wont be same fr rtl and emu for all cores # TODO
            continue

        if core in ["boom", "boomp"]: # boom specific stuff
            if field in ['reg_data']: # these fields are not there in boom trace
                continue
            if rtl_d["ex"] and (not field in ["ex","ex_cause","ex_pc"]): # rtl ex insts are dummy since rtl trace doesnt record ex insts
                continue

            if rtl_d["ex"] and (field in ["ex_cause","ex_pc"]) and (rtl_d[field] in ["",None]): # rtl doesnt have ex data in this case
                continue

            if emu_d["ex"]: 
                if field in ["priv_lvl"]: # these data wont be there fr rtl or emu when ex happens or is diff
                    continue
        
        if core == "rc": # rocket core specific stuff
            if field in ['reg_data']: # these fields are not there in rc trace
                continue
            if emu_d["inst"] in csr_insts: # emu prints updated csr value while rc prints updated reg value
                if field in ["wreg", "wdata", "wreg_type"]: 
                    continue

            if rtl_d["ex"] and (field in ["ex_cause","ex_pc"]) and (rtl_d[field] in ["",None]): # rtl doesnt have ex data in this case
                continue

        if core == 'cva6': # cva6 specific stuff
            cva6_fields = ['pc', 'inst_hex', 'ex', 'ex_pc', 'ex_tval', 'got_end_of_inst', 'reg_data']
            if not field in cva6_fields: 
                continue
            if field == 'reg_data': 
                if emu_d['wreg'] == -1: # emu doesnt have reg data
                    continue
                else: 
                    emu_reg_id = reg_no_to_id(emu_d['wreg'], emu_d['wreg_type'])
                    if not emu_reg_id in rtl_val.keys(): 
                        is_equal = False
                        field = 'wreg'
                    else: 
                        rtl_val = rtl_val[emu_reg_id][0] # rtl_val has multiple  values per reg but dest
                                                    # reg value is printed first and that is what we want
                        field = 'wdata'

        if is_equal: # dint find any mismatch so far
            is_equal = is_inst_field_equal(field, rtl_val, emu_d[field])
        if not is_equal: 
            comp_d["has_mm"] = True
            comp_d["mms"].append([f"ERROR:{rtl_d['trace_file_line_no']},{emu_d['trace_file_line_no']}", field, rtl_val, emu_d[field]])

    return comp_d

"""
Compares the inst data of rtl and emu
"""
def compare_rtl_emu_inst_data(rtl_trace_file_name, rtl_inst_data, emu_inst_data, comp_log_file, ign_mm_after_first, core, emu):
    comp_inst_data = []
    mm_insts = []
    inst_no = 0

    #check_equal(len(rtl_inst_data), len(emu_inst_data), f"{rtl_trace_file_name}: rtl and emu are having diff no of insts") # TODO

    # comp each inst
    for rtl_d, emu_d in zip(rtl_inst_data, emu_inst_data):
        comp_d = copy.deepcopy(comp_inst_data_template)
        
        comp_d["rtl_data"] = rtl_d
        comp_d["emu_data"] = emu_d
        comp_d = compare_rtl_emu_one_inst(rtl_trace_file_name, rtl_d, emu_d, comp_d, core)
        comp_d["inst_no"] = inst_no
        comp_inst_data.append(comp_d)
        if comp_d["has_mm"]: 
            mm_insts.append(inst_no)
        inst_no += 1

    # convert the data to dict
    comp_inst_data = {"comp_inst_data": comp_inst_data, "mm_insts": mm_insts}
    TU.update_json_file(comp_log_file, comp_inst_data)

    return comp_inst_data


"""
Analyses the inst data of each rtl and emu trace
This function is used to create any additonal info abt the mismatches in the file
    so that it makes ignoring easier
"""
def analyze_inst_data(rtl_trace_file_name, comp_inst_data, ign_mm_after_first, core, emu): 

    # remove some mismatches from rc bcz they happen before the nop inst
    if core == "rc":
        mm_insts = comp_inst_data["mm_insts"]
        new_mm_insts = []

        for mm_inst in mm_insts: 
            check_equal(comp_inst_data["comp_inst_data"][mm_inst]["has_mm"], True\
                       ,  f"{rtl_trace_file_name} instr without mm listed in mm_insts, {mm_inst}")
            ign_mm = False
            rtl_d = comp_inst_data["comp_inst_data"][mm_inst]["rtl_data"]
            emu_d = comp_inst_data["comp_inst_data"][mm_inst]["emu_data"]
            comp_d = comp_inst_data["comp_inst_data"][mm_inst]
            mms_d = comp_inst_data["comp_inst_data"][mm_inst]["mms"]

            #filter condn: no exceptions, inst no is before end of nops, emu doesnt show write to reg, rtl writes to r0 reg
            if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (comp_d["inst_no"] <= rc_end_of_nops_inst_no)\
                and (emu_d["wreg"] == -1) and (rtl_d["wreg"] == 0) and (rtl_d["wreg_type"] == "x") ): 
                ign_mm = True

            if not ign_mm: 
                new_mm_insts.append(mm_inst)

        comp_inst_data["mm_insts"] = new_mm_insts

    return comp_inst_data


"""
"""
def handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst): 
    if not mm in ign_itr_mm:
        found_mms.append(mm)
        new_mm_insts.append(mm_inst)
        ign_mm = False
    else:
        ign_mms.append(mm)
        ign_mm = True

    return found_mms, new_mm_insts, ign_mms, ign_mm


"""
This function is used to ignore mismatches
"""
def ignore_mismatches(rtl_trace_file_name, comp_inst_data, ign_itr_mm, ign_mm_after_first, core, emu, debug=False): 
    ign_mms = []
    found_mms = []
    new_mm_insts = []
    mm_insts = comp_inst_data["mm_insts"]

    if ign_mm_after_first and len(mm_insts) > 1: 
        mm_insts = [mm_insts[0]]

    for mm_inst in mm_insts: 
        check_equal(comp_inst_data["comp_inst_data"][mm_inst]["has_mm"], True\
                   ,  f"{rtl_trace_file_name} instr without mm listed in mm_insts, {mm_inst}")
        ign_mm = False
        rtl_d = comp_inst_data["comp_inst_data"][mm_inst]["rtl_data"]
        emu_d = comp_inst_data["comp_inst_data"][mm_inst]["emu_data"]
        mms_d = comp_inst_data["comp_inst_data"][mm_inst]["mms"]
        if debug: pprint(comp_inst_data["comp_inst_data"][mm_inst])

        """
        mm1: When loading from within dram range, spike loads random data while boom loads 0. 
            This is probably because of how memory is initialized in spike and boom. when spike was run 
            again with the same mem file, it loaded diff value proving that spike initializes mem randomly.
        filter condn: no exception, inst is load, mem addr is within dram, spike wdata is random while 
                        boom data is 0
        """
        mm = "1"
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in load_insts+amo_load_insts) \
            and (int(emu_d["mem_addr"],16) >= int("80000000",16)) and (int(emu_d["mem_addr"],16) < int("8fffffff",16))
            and (rtl_d["wdata"] == 0) and (emu_d["wdata"] != 0) ): 
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm1_1: When jumping to an addr inside dram range, spike reads random
            data as inst while boom reads 0 as the inst. hence, spike might run
            normally (if the rand text is a valid inst) but boom throws exception
        filter condn: boom throws illegal inst ex, spike doesnt, addr is in dram range
        """
        mm = "1_1"
        if ( (rtl_d["ex"]) and (not emu_d["ex"])\
            and (int(emu_d["pc"],16) >= int("80000000",16)) and (int(emu_d["pc"],16) < int("8fffffff",16))
            and (rtl_d["ex_cause"] == 2) ): 
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm1_2: When jumping to an addr inside dram range, spike reads random
            data as inst while boom reads 0 as the inst. hence, spike and boom may throw
            different exceptions.
        filter condn: boom throws illegal inst ex, spike throws exception 5, addr is in dram range
        """
        mm = "1_2"
        if ((rtl_d["ex"]) and (emu_d["ex"]) and (emu_d["inst"] in load_insts) \
            and (int(emu_d["pc"],16) >= int("80000000",16)) and (int(emu_d["pc"],16) < int("8fffffff",16)) \
            and (rtl_d["ex_cause"] == 2) and (emu_d["ex_cause"] == 5)): 
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue        

        """
        mm2: When storing to location outside spike mem range but inside boom range, spike throws 
            store access fault exception but boom runs normally
        filter condn: boom doesnt throw ex, spike thorws store access fault ex, inst is store, 
            mem_addr outside spike range 
        """
        mm = "2"
        if ( (not rtl_d["ex"]) and (emu_d["ex"]) and (emu_d["ex_type"] == "trap_store_access_fault")\
            and (emu_d["inst"] in store_insts+amo_store_insts)\
            and (not in_addr_range(int(emu_d["ex_tval"],16), spike_valid_addr_ranges)) ):
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm2_1: same as mm2, except fr load
        filter condn: boom doesnt throw ex, spike thorws store access fault ex, inst is store, 
            mem_addr outside spike range 
        """
        mm = "2_1"
        if ( (not rtl_d["ex"]) and (emu_d["ex"]) and (emu_d["ex_type"] == "trap_load_access_fault")\
            and (emu_d["inst"] in load_insts)\
            and (not in_addr_range(int(emu_d["ex_tval"],16), spike_valid_addr_ranges)) ):
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm20: When reading from fflags reg, spike is returning 0 while boom is returning 1a. There is no float inst before, 
            so, boom should not have enabled any of its flags. 
        filter condn: inst is csr read, reg is fflags. boom value and spike value r diff in bits 4, 3, and 1
        """
        mm = "20"
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in csr_read_insts) and ("fflags" in emu_d["rest_1"])\
            and (rtl_d["wdata"] != emu_d["wdata"]) and ( (rtl_d["wdata"] & int("ffffffffffffffe5",16)) == emu_d["wdata"] ) ):
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm20_1: Same as mm20 except boom now returns value d while spike returns 0, also there was a float inst before 
            this inst in this case
        filter condn: inst is csr read, reg is fflags. boom value and spike value r diff in bits 4, 3, and 1
        """
        mm = "20_1"
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in csr_read_insts) and ("fflags" in emu_d["rest_1"])\
            and (rtl_d["wdata"] != emu_d["wdata"]) and ( (rtl_d["wdata"] & int("fffffffffffffff2",16)) == emu_d["wdata"] ) ):
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm21: When reading from misa reg, boom and spike values are diff since 23rd bit in boom is enabled. that bit means there
            are non-standard extensions present in the design.
        filter condn: inst is csr read, reg is misa. boom value and spike value r diff in bit 23
        """
        mm = "21"
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in csr_read_insts) and ("misa" in emu_d["rest_1"])\
            and (rtl_d["wdata"] != emu_d["wdata"]) and ( (rtl_d["wdata"] & int("ffffffffff7fffff",16)) == emu_d["wdata"] ) ):
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm22: When reading from stvec, boom is returning a random value where as spike is returning 0. 
        filter condn: inst is csr read, reg is misa. boom value and spike value r diff in bit 23
        """
        mm = "22"
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in csr_read_insts) and ("stvec" in emu_d["rest_1"])\
            and (rtl_d["wdata"] != emu_d["wdata"]) and (emu_d["wdata"] == 0) ):
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm23: boom is assigning random values to some registers, if we are accessing those registers, then boom returns a 
            random value mismatching with the value returned by spike.
        filter condn: inst is csr, reg is one of regs fr which boom assigns rand val, wdata is mismatching, spike data is 0, 
            no exception
        """
        mm = "23"
        boom_rand_reg_in_inst = any([(i in emu_d["rest_1"]) for i in boom_rand_regs])
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in csr_read_insts) and boom_rand_reg_in_inst\
            and (rtl_d["wdata"] != emu_d["wdata"]) and (emu_d["wdata"] == 0) ):
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm24: Boom is giving 0 value while spike is giving non-zero value to some csr registers like tdata (debug/trace) register.
        filter condn: inst is csr, reg is one of regs fr which boom assigns 0 val, wdata is mismatching, spike data is non 0, 
            boom data is 0, no exception
        """
        mm = "24"
        boom_0_reg_in_inst = any([(i in emu_d["rest_1"]) for i in boom_0_regs])
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in csr_read_insts) and boom_0_reg_in_inst\
            and (rtl_d["wdata"] != emu_d["wdata"]) and (rtl_d["wdata"] == 0) ):
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mm40: Floating point instrn which has invalid rm field does not raise exception in boom while spike throws exception
        filter condn: inst is fnmadd.s, spike throw illegal inst ex, booom doesnt throw ex, inst bits 12 to 14 are 5 or 6
        """
        mm = "40"
        if ( (not rtl_d["ex"]) and (emu_d["ex"]) and (emu_d["ex_cause"] == 2) and (emu_d["inst"] in float_rm_insts)\
            and ( (emu_d["inst_hex"] & int("7000",16)) in [int("5000",16),int("6000",16)] )  ): 
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mmrc_1: When running a jump instruction, rc is writing to ro register while spike is not.
        filter condn: no exceptions, inst is jump, emu doesnt write to reg, rtl writes to r0 reg
        """
        mm = "rc_1"
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in ["j"]) and (emu_d["wreg"] == -1)\
            and (rtl_d["wreg"] == 0) and (rtl_d["wreg_type"] == "x") ): 
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue

        """
        mmrc_1.1: When running multiply instrn, rc is not writing to the dest reg while emu is
        filter condn: no exceptions, inst is mult, emu writes to reg, rtl doesnt write to reg
        """
        mm = "rc_1.1"
        if ( (not rtl_d["ex"]) and (not emu_d["ex"]) and (emu_d["inst"] in mult_insts+div_insts) and (emu_d["wreg"] != -1)\
            and (not rtl_d["write_en"]) ): 
            found_mms, new_error_insts, ign_mms, ign_mm = handle_mm(mm, ign_itr_mm, found_mms, new_mm_insts, ign_mms, mm_inst)
            continue


        # this is not any of the known mismatch
        if not ign_mm: 
            new_mm_insts.append(mm_inst)
           
    comp_inst_data["new_mm_insts"] = new_mm_insts

    return ign_mms, found_mms, comp_inst_data


"""
Summarizes data for each comp log file
"""
def summarize_inst_data(rtl_trace_file_name, emu_trace_file_name\
                        , comp_inst_data, ign_mms, found_mms): 
   
    summary_data = ""

    # print the ignored mismatches
    if ign_mms != []: 
        summary_data += f"mismtaches ignored: {ign_mms}\n"
        summary_data += "-------\n"

    # print the found mismatches
    if found_mms != []: 
        summary_data += f"mismtaches found: {found_mms}\n"
        summary_data += "-------\n"

    # print the error data fr mismtaches 
    mm_insts = comp_inst_data["new_mm_insts"]
    for mm_inst in mm_insts: 
        mms_d = comp_inst_data["comp_inst_data"][mm_inst]["mms"]
        for mm_d in mms_d: 
            summary_data += f"[{rtl_trace_file_name}][{emu_trace_file_name}][{mm_inst}][{mm_d}] \n"
        summary_data += "-------\n"

    if len(mm_insts) == 0: 
        summary_data += f"No mms found in {rtl_trace_file_name}\n"

    summary_data += "-----------------------------------------------------------------------\n"

    return summary_data


"""
This function summarizes mismatches in all the comp_log files 
"""
def summarize_all_files(summary_file_data, summary_fp):

    tot_no_files = len(summary_file_data)
    no_files_mms = 0
    ign_mms_data = {}
    found_mms_data = {}

    # calculate summary data
    for filename, ign_mms, found_mms, new_mm_insts in summary_file_data: 
        # get no of files with errors
        if len(new_mm_insts) > 0: 
            no_files_mms += 1

        # get no of times each mismatch is ignored
        for ign_mm in ign_mms: 
            if not ign_mm in ign_mms_data.keys(): 
                ign_mms_data[ign_mm] = 1
            else: 
                ign_mms_data[ign_mm] += 1

        # get no of times each mismatch is found
        for found_mm in found_mms: 
            if not found_mm in found_mms_data.keys(): 
                found_mms_data[found_mm] = 1
            else: 
                found_mms_data[found_mm] += 1

    summary_fp.write("-----------------------------------------------------------------------\n")
    summary_fp.write("-----------------------------------------------------------------------\n")
    summary_fp.write(f"Total files = {tot_no_files}, No of files with mms = {no_files_mms}\n")
    summary_fp.write(f"No of mismatches ignored: {ign_mms_data}\n")
    summary_fp.write(f"No of mismatches found: {found_mms_data}\n")
    summary_fp.write("-----------------------------------------------------------------------\n")
    summary_fp.write("-----------------------------------------------------------------------\n")

    return
   
rsd_registers = {
    "inst_hex": "",
    "trace_file_line_no": "",
    "pc": "",
    "trap_exception": "",
    "fcsr": "",
    "mstatus": "",
    "mip": "",
    "mie": "",
    "mcause": "",
    "mtvec": "",
    "mtval": "",
    "mepc": "",
    "mscratch": "",
    "minstret": "",
    "frm": "",
    "zero": "",
    "ra": "",
    "sp": "",
    "gp": "",
    "tp": "",
    "t0": "",
    "t1": "",
    "t2": "",
    "t3": "",
    "t4": "",
    "t5": "",
    "t6": "",
    "s0": "",
    "s1": "",
    "s2": "",
    "s3": "",
    "s4": "",
    "s5": "",
    "s6": "",
    "s7": "",
    "s8": "",
    "s9": "",
    "s10": "",
    "s11": "",
    "a0": "",
    "a1": "",
    "a2": "",
    "a3": "",
    "a4": "",
    "a5": "",
    "a6": "",
    "a7": "",
    "ft0": "",
    "ft1": "",
    "ft2": "",
    "ft3": "",
    "ft4": "",
    "ft5": "",
    "ft6": "",
    "ft7": "",
    "ft8": "",
    "ft9": "",
    "ft10": "",
    "ft11": "",
    "fs0": "",
    "fs1": "",
    "fs2": "",
    "fs3": "",
    "fs4": "",
    "fs5": "",
    "fs6": "",
    "fs7": "",
    "fs8": "",
    "fs9": "",
    "fs10": "",
    "fs11": "",
    "fa0": "",
    "fa1": "",
    "fa2": "",
    "fa3": "",
    "fa4": "",
    "fa5": "",
    "fa6": "",
    "fa7": ""
}


def parse_rsd_file(rtl_trace_file_name, rtl_instr_file_name):
    instruction_dict = {}
    with open(rtl_trace_file_name, "rt") as f:
        trace = f.read().split('\n')
    with open(rtl_instr_file_name, "rt") as f:
        for line in f.readlines():
            if line[0] == "L":
                values = line.split()
                instruction_dict[values[-2]] = values[-1]
    total_trace = []

    trace_blocks = [trace[x:x+5] for x in range(0,len(trace),5)][:-1]
    for i, trace_block in enumerate(trace_blocks):
        log = copy.deepcopy(rsd_registers)

        log["trace_file_line_no"] = i * 5 + 1

        # Assuming line 1 has format: "pc,inst_hex,..."
        fields = trace_block[1].split(',')[:-1]
        log["pc"] = fields[0]
        log["inst_hex"] = instruction_dict[f'{int(log["pc"],16):08x}']

        # GPRs: from line 1 (after pc, inst_hex) — assume 32 GPRs
        gpr_keys = list(log.keys())[15:15+32]
        gpr_values = trace_block[1].split(',')[:-1]
        for key, value in zip(gpr_keys, gpr_values):
            log[key] = value

        # FPRs: from line 2 — assume 32 FPRs
        fpr_keys = list(log.keys())[15+32:15+32+32]
        fpr_values = trace_block[2].split(',')[:-1]
        for key, value in zip(fpr_keys, fpr_values):
            log[key] = value

        flags = {
            "fflags.NV": 0,
            "fflags.DZ": 0,
            "fflags.OF": 0,
            "fflags.UF": 0,
            "fflags.NX": 0,
            "frm" : 0, 
        }   

        # CSR updates from line 4 (key:value format)
        for keypair in trace_block[4].split(','):
            if ':' in keypair:
                key, value = keypair.split(':')
                key = key.strip()
                value = value.strip()
                if key in log:
                    log[key] = value
                if key in flags:
                    flags[key] = int(value,16)

        fflags = (flags["fflags.NV"] << 4) | (flags["fflags.DZ"] << 3) | (flags["fflags.OF"] << 2) | (flags["fflags.UF"] << 1) | flags["fflags.NX"]
        fcsr = (flags["frm"] << 5) | fflags
        log["fcsr"] = f"0x{fcsr:08x}"
        log["frm"] = f"0x{flags['frm']:08x}"
        
        #print(log)
        total_trace.append(log)
                
    return total_trace 

def parse_spike_rsd_file(spike_trace_file_name):
    with open(spike_trace_file_name,"rt") as f:
        content = f.read().split('\n')
    i = 0
    total_trace = []
    while i < len(content):
        log = copy.deepcopy(rsd_registers)
        while "core" in content[i]:
            match = re.search(r'(0x[0-9a-fA-F]+) \((0x[0-9a-fA-F]+)\)', content[i])
            if match:
                log["pc"] = match.group(1)
                log["inst_hex"] = match.group(2)
            if "trap" in content[i]:
                log["trap_exception"] = 1
            i += 1
        
        
        log["trace_file_line_no"] = i
        spike_keys = list(log.keys())[4:]
        spike_values = content[i:i+75]
        for key, value in zip(spike_keys, spike_values):
            log[key] = value
        i += 75 
        total_trace.append(log) 
    return total_trace[:-1]

def is_equal(key, rsd_value, spike_value):
    if key in ["trace_file_line_no", "pc", "mstatus", "mcause", "mtvec", "mepc", "minstret", "zero", "ra", "sp", "gp", "tp", "t0"]:
        return True
    if key in ["trap_exception"]:
        return rsd_value == spike_value
    return f"{str(rsd_value)[-8:]}" == f"{str(spike_value)[-8:]}"

def compare_rsd_spike(rtl_data, spike_data, comp_log_file):
    rtl_start = 0
    while rtl_data[rtl_start]["inst_hex"] != "00000013":
        rtl_start += 1
    rtl_start += 1
    spike_start = 0
    while spike_data[spike_start]["inst_hex"] != "0x00000013":
        spike_start += 1
    spike_start += 1
    total_mismatches = []
    for rtl, spike in zip(rtl_data[rtl_start:], spike_data[spike_start:]):
        mismatch = {}
        mismatch["pc"] = rtl["pc"]
        mismatch["instruction"] = rtl["inst_hex"]
        for key in list(rtl.keys()):
            if not is_equal(key, rtl[key], spike[key]):
        #        mismatch.append((key, rtl[key], spike[key]))
                mismatch[key] = (rtl[key], spike[key])
        total_mismatches.append(mismatch)
    result = ""
    for i in total_mismatches: 
        result += json.dumps(i)+'\n'
        
    with open(comp_log_file,'w') as f:
        f.write(result)
    return result

"""
Parses the rtl trace log files, compares with emu trace to find
mismatches, ignores the known mismatches, and returns summary info
"""
def detect_bugs_in_file(arg):
        
    rtl_trace_file, emu_trace_file, comp_log_file\
        , ign_mm_after_first, ign_itr_mm, core, emu, debug = arg

    print(rtl_trace_file)
    rtl_trace_file_name = os.path.basename(rtl_trace_file)

    print(rtl_trace_file_name)
    if core == "rsd":
        rtl_instr_file = rtl_trace_file.replace("trace", "instr")
        rtl_inst_data = parse_rsd_file(rtl_trace_file, rtl_instr_file)
        emu_inst_data = parse_spike_rsd_file(emu_trace_file)
        if not os.path.exists(comp_log_file):
            results = compare_rsd_spike(rtl_inst_data, emu_inst_data, comp_log_file)
            return results
        return
        

    if not os.path.exists(comp_log_file): # compare traces and generate comp log file
        try: 
            # parse rtl simulation trace file
            rtl_inst_data = parse_rtl_trace_file(rtl_trace_file, core)
            
            # parse emulation trace file
            emu_inst_data = parse_emu_trace_file(emu_trace_file, emu, len(rtl_inst_data)+100)
                                                # +100 bcz we dont know how many rtl exception insts are missing in rtl trace
   
            # do any modifications needed to improve mismatch detection
            rtl_inst_data, emu_inst_data = preprocess_data(rtl_trace_file_name, rtl_inst_data, emu_inst_data, core, emu)

            comp_inst_data = compare_rtl_emu_inst_data(rtl_trace_file_name, rtl_inst_data, emu_inst_data, comp_log_file, ign_mm_after_first, core, emu)
        except: 
            return [os.path.basename(rtl_trace_file), [], [], [],  "ERROR occured\n--------\n"]

    else: # if comp log already exists, skip generating it
        with open(comp_log_file, 'r') as fp: comp_inst_data = json.load(fp)

    comp_inst_data = analyze_inst_data(rtl_trace_file_name, comp_inst_data, ign_mm_after_first, core, emu)
    
    ign_mms, found_mms, comp_inst_data = ignore_mismatches(rtl_trace_file_name, comp_inst_data, ign_itr_mm, ign_mm_after_first, core, emu, debug)
    
    summary_data = summarize_inst_data(rtl_trace_file_name, os.path.basename(emu_trace_file), comp_inst_data, ign_mms, found_mms)
    
    return [os.path.basename(rtl_trace_file), ign_mms, found_mms, comp_inst_data["new_mm_insts"], summary_data]


"""
Gets the filelist we want to detect bugs in 
"""
def get_trace_filelist(mode, rtl_log_dir, emu_log_dir, comp_log_dir\
                    , rtl_trace_file_name_re, rtl_trace_file_name_t\
                    , emu_trace_file_name_t, comp_log_file_name_t, debug_file_nos=[]):

    rtl_trace_log_filelist = TU.get_files_in_dir(rtl_log_dir, rtl_trace_file_name_re)
    filelist = []
    # files are named with pattern using numbers
    for rtl_trace_file in tqdm(rtl_trace_log_filelist, desc="[       ] ---- Getting filelist"):
        file_no = re.search(rtl_trace_file_name_re, os.path.basename(rtl_trace_file)).group(1)
        if (mode == 'debug') and (int(file_no) not in debug_file_nos): # only check debug files if in debug mode
            continue
        emu_trace_file_name = emu_trace_file_name_t.substitute(fno=file_no)
        emu_trace_file = os.path.join(emu_log_dir, emu_trace_file_name)
        comp_log_file = os.path.join(comp_log_dir, comp_log_file_name_t.substitute(fno=file_no))
        filelist.append([rtl_trace_file, emu_trace_file, comp_log_file])

    return filelist 


"""
Main function that detects mismatches
"""
def detect_mismatches(mode, debug_file_nos, core, emu, ign_mm_after_first, ign_itr_mm\
                      , summary_file, no_threads, *trace_filelist_args):

    # get a list of all the trace files
    trace_filelist = get_trace_filelist(mode, *trace_filelist_args, debug_file_nos)
    if mode == 'debug': 
        print(trace_filelist) #; exit()
        #delete the comp files
        for files in trace_filelist: TU.delete_file(files[2], True)
        summary_fp = open(f"{summary_file}_debug", "w") # file to store summary of mismatches
    else: 
        summary_fp = open(summary_file, "w") # file to store summary of mismatches

    # analyze all trace files for mismatches and create a consolidated log file
    summary_file_data = []

    args = []
    for rtl_trace_file, emu_trace_file, comp_log_file in trace_filelist: # create arg list
        args.append([rtl_trace_file, emu_trace_file, comp_log_file\
                  , ign_mm_after_first, ign_itr_mm, core, emu, False])

    chunk_size = max(int((len(trace_filelist)/no_threads)/8), 1) # so if there are 1000 files 
                  # & 10 processes, chunk is 12. if we have less no of files, then just do one at a time
    with mp.Pool(processes=no_threads) as pool: 
        return_data = pool.imap_unordered(detect_bugs_in_file, args, chunksize=chunk_size)
        for data in tqdm(return_data, total=len(args), desc="[       ] ---- Parsing trace files"):  
            summary_fp.write(data[-1]) # write summary of individual file to log file
            summary_file_data.append(data[:-1])
        pool.close() 
        pool.join()
    if core != "rsd":
        # create a summary of all the mismatch data
        summarize_all_files(summary_file_data, summary_fp)

    summary_fp.close()


###############
# depreciated #
###############
#line_type_1_re = [ "^testing $random "    , f"^== Loading "\
#                , f"^===== MemorySystem 0", f"^CH. 0 TOTAL_STORAGE"\
#                , f"^DRAMSi", "^-------------", "^VCS Coverage Metrics: "\
#                , "^$", " Coverage status: ", "\*\*\* PASSED"\
#                , "simv-chipyard-SmallBoomConfig", "\*\*\* FAILED"\
#                , "Assertion failed: ", "at (.*) assert"]  # unwanted lines in trace file
    #for arg in args: 
    #    data = detect_bugs_in_file(arg)
    #    summary_fp.write(data[-1]) # write summary of individual file to log file
    #    summary_file_data.append(data[:-1])

def debug_rsd_bug_detection(rsd_trace_log, rsd_instr_log, spike_trace_log):
    rsd = parse_rsd_file(rsd_trace_log, rsd_instr_log)
    with open("rtl_data.log", 'w') as f:
        for i in rsd:
            f.write(json.dumps(i)+'\n')
    spike = parse_spike_rsd_file(spike_trace_log)
    with open("emu_data.log", 'w') as f:
        for i in spike:
            f.write(json.dumps(i)+'\n')
    compare_rsd_spike(rsd, spike, "comp.log")

if __name__ == "__main__":
    debug_rsd_bug_detection("/mnt/shared-scratch/Rajendran_J/jkohhokj/TheHuzz_USENIX_22/outputs_all/rsd_thehuzz_25_06_17_15_46_28/sim_out/rtl_trace_out_0.log", "/mnt/shared-scratch/Rajendran_J/jkohhokj/TheHuzz_USENIX_22/outputs_all/rsd_thehuzz_25_06_17_15_46_28/sim_out/rtl_instr_out_0.log","/mnt/shared-scratch/Rajendran_J/jkohhokj/TheHuzz_USENIX_22/outputs_all/rsd_thehuzz_25_06_17_15_46_28/sim_out/emu_trace_out_0.log")
