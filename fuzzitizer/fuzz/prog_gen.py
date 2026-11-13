"""Generate FUZZItizer test programs."""

#Imports
import subprocess, os, random, re
import uuid
from tqdm import tqdm

import fuzz_utils
from peripheral_inputs import read_mmio_commands


def usedebugtrigger(percent):
    if percent == 0:
        return False
    if percent == 100:
        return True
    return random.randrange(100) < percent


def writedebugtrigger(core_os):
    if core_os == "opn":
        return (
            "*(volatile uint64_t *)0x000000fff1000ff8ULL = "
            "0x46555a5a44424701ULL;\n"
            'asm volatile("fence iorw, iorw" ::: "memory");\n'
        )
    if core_os == "cal":
        return (
            "*(volatile uint32_t *)0x300300CCU = 0xEFU;\n"
            'asm volatile("fence iorw, iorw" ::: "memory");\n'
        )
    raise ValueError(f"unsupported core OS: {core_os}")


def instructions_for_xlen(instructions, xlen):
    if xlen == 64:
        return dict(instructions)
    if xlen == 32:
        return {
            key: value
            for key, value in instructions.items()
            if key[1].startswith("rv32")
        }
    raise ValueError(f"unsupported RISC-V XLEN: {xlen}")


def compile_programs(
    sw_dir,
    inst_output_path,
    no_threads,
    debug_print=False,
    generate_dumps=False,
):
    command = ["make"]
    if not debug_print:
        command.append("-s")
    target = "compile_all_with_dumps" if generate_dumps else "compile_all"
    command.extend(
        ["-j", str(no_threads), target, f"C_DIR={inst_output_path}"]
    )
    subprocess.run(command, cwd=sw_dir, check=True)


def gen_multi_prog( del_repo, mode\
                        , no_threads, inst_output_path, sw_dir\
                        , num_progs, prog_gen_xargs, fuzzer_input_format\
                        , trash_dir='/tmp/', debug_print=False, input_test_files=[]):

    inst_output_path_name = os.path.basename(inst_output_path)
    generated_test_files = [] # record all generated test files

    if del_repo:
        fuzz_utils.delete_dir(inst_output_path, True, 'move', f"{trash_dir}/prog_gen_{uuid.uuid1()}")
    
    for i, prog_no in enumerate(range(num_progs)):
        file_name = f'inst_file_{prog_no}.c' 
        file_fullpath = os.path.join(inst_output_path, file_name)
        file_p = open(file_fullpath, 'w')
        generated_test_files.append(fuzz_utils.change_extension(file_fullpath, fuzzer_input_format))
   
        if (mode == 'random'):
            gen_random_prog(file_p, *prog_gen_xargs)
        elif (mode in ['fuzzitizer', 'thehuzz']):
            gen_fuzzer_prog(file_p, *prog_gen_xargs)
        elif (mode in ['gen1']):
            gen_peripheral_program(file_p, input_test_files[i], *prog_gen_xargs)
        else:
            print("Unknown mode received", mode)

    compile_programs(
        sw_dir,
        inst_output_path,
        no_threads,
        debug_print,
    )

    return generated_test_files

def gen_peripheral_program(file_p, input_test_file, num_inst_in_prog, opcode_list, inst_list_all_w_ext\
                    , num_nops_at_start, num_nops_at_end, first_opcode_list\
                    , syscall_prob, max_syscall_prob, core_os, syscall_ids\
                    , perif_addresses, per_safe_insts_in_prog
                    , peripheral_specs=(), mmio_settings=None
                    , allow_privilege_switch=True, emit_initial_mmio_store=True
                    , peripheral_replay="compressed-mmio", debug_program_percent=0):

    peripheral_identifier = None
    input_path = input_test_file
    if isinstance(input_test_file, dict):
        input_path = input_test_file["path"]
        peripheral_identifier = input_test_file["peripheral"]
    commands = read_mmio_commands(
        input_path,
        peripheral_specs,
        peripheral_identifier,
        peripheral_replay,
    )

    initial_mmio_store = (
        emit_initial_mmio_store and peripheral_replay == "compressed-mmio"
    )
    emit_debug_trigger = (
        peripheral_replay not in (
            "external-trigger-mmio",
        )
        and usedebugtrigger(debug_program_percent)
    )
    write_c_frame_start(file_p, num_nops_at_start, max_syscall_prob, core_os\
            , num_inst_in_prog, perif_addresses, commands, mmio_settings
            , allow_privilege_switch, initial_mmio_store, emit_debug_trigger)

    if peripheral_replay in (
        "direct-mmio", "external-trigger-mmio", "gap-mmio"
    ):
        for syscall_no, command in enumerate(commands):
            if peripheral_replay == "gap-mmio":
                write_mmio_gap(file_p, command["gap_rows_before"])
            for inst in create_syscall(
                core_os,
                syscall_ids,
                perif_addresses,
                syscall_no,
                command["write"],
                mmio_settings,
            ):
                file_p.write(inst + " \n")
            write_mmio_gap(file_p, command.get("wait_nops", 0))
        write_c_frame_end(file_p, num_nops_at_end)
        file_p.close()
        return

    # determine the sequence of instructions
    # first half will be simple insts and rest will be all insts
    num_first_half_insts = int((num_inst_in_prog*per_safe_insts_in_prog)/100)
    op_seq = [random.choice(first_opcode_list) for i in range( num_first_half_insts )]
    op_seq += [random.choice(opcode_list) for i in range(num_inst_in_prog - len(op_seq))]

    # use syscall insts also
    for i in range(len(op_seq)):
        if (random.randint(0,99) < syscall_prob): op_seq[i] = 'syscall'

    # create the insts from the sequence
    inst_seq = []
    syscall_no = 0
    for op in op_seq:
        if op in ['syscall']: # syscalls and other special insts
            if syscall_no < len(commands):
                command = commands[syscall_no]["write"]
                write_mmio_gap(
                    file_p, commands[syscall_no].get("gap_rows_before", 0)
                )
            else:
                command = random.choice([0,1])
            for inst in create_syscall(core_os, syscall_ids, perif_addresses, syscall_no, command, mmio_settings):
                file_p.write(inst + " \n")
            syscall_no += 1
        else: # normal insts
            inst_data = inst_list_all_w_ext[op]
            write_asm(create_inst(op[0], inst_data, file_p, 'fuzz'), file_p)

    write_c_frame_end(file_p, num_nops_at_end)

    file_p.close()



def gen_random_prog(file_p, num_inst_in_prog, opcode_list, inst_list_all_w_ext\
                    , num_nops_at_start, num_nops_at_end, first_opcode_list\
                    , syscall_prob, max_syscall_prob, core_os, syscall_ids\
                    , perif_addresses, per_safe_insts_in_prog
                    , peripheral_specs=(), mmio_settings=None
                    , allow_privilege_switch=True, emit_initial_mmio_store=True
                    , peripheral_replay="compressed-mmio", debug_program_percent=0):
    
    #write to file
    write_c_frame_start(file_p, num_nops_at_start, max_syscall_prob, core_os\
            , num_inst_in_prog, perif_addresses, mmio_settings=mmio_settings
            , allow_privilege_switch=allow_privilege_switch
            , emit_initial_mmio_store=emit_initial_mmio_store
            , emit_debug_trigger=usedebugtrigger(debug_program_percent))
    
    # determine the sequence of instructions
    op_seq = [random.choice(opcode_list) for i in range( num_inst_in_prog )] 

    # use syscall insts also
    for i in range(num_inst_in_prog): 
        if (random.randint(0,99) < syscall_prob): op_seq[i] = 'syscall'

    # create the insts from the sequence
    inst_seq = []
    syscall_no = 0
    for op in op_seq: 
        if op in ['syscall']: # syscalls and other special insts
            for inst in create_syscall(core_os, syscall_ids, perif_addresses, syscall_no, mmio_settings=mmio_settings): file_p.write(inst + " \n")
            syscall_no += 1
        else: # normal insts
            inst_data = inst_list_all_w_ext[op]
            write_asm(create_inst(op[0], inst_data, file_p, 'fuzz'), file_p)
    
    write_c_frame_end(file_p, num_nops_at_end)
    
    file_p.close()


"""Creates an OpenPiton memory-mapped load or store operation."""
def create_syscall(core_os, syscall_ids, perif_addresses, syscall_no, command=None, mmio_settings=None):

    if mmio_settings is None:
        raise ValueError(f"MMIO settings are required for core OS: {core_os}")

    inst_seq = []
    if command is not None:
        read_write = command
    else: read_write = random.choice([0,1])

    if read_write == 0: # load
        inst_seq.append(f'asm volatile("{mmio_settings["load_mnemonic"]} t1, %0; {mmio_settings["load_mnemonic"]} t0, 0(t1);" : : "m"(addr[{syscall_no}]) : "t0", "t1", "memory");')
    else:  # store
        inst_seq.append(f'asm volatile("{mmio_settings["load_mnemonic"]} t0, %0; {mmio_settings["load_mnemonic"]} t1, %1; {mmio_settings["store_mnemonic"]} t0, 0(t1);" :: "m"(data[{syscall_no}]), "m"(addr[{syscall_no}]) : "t0", "t1", "memory");')

    return inst_seq


def write_mmio_gap(file_p, gap_rows):
    if gap_rows <= 0:
        return
    file_p.write(f"/* IPFuzz idle rows: {gap_rows} */\n")
    for _ in range(gap_rows):
        file_p.write('asm volatile ( "ADDI x0, x0, 0" );\n')



def gen_fuzzer_prog(file_p, num_inst_in_prog, opcode_list, inst_list_all_w_ext\
                    , num_nops_at_start, num_nops_at_end, first_opcode_list\
                    , syscall_prob, max_syscall_prob, core_os, syscall_ids\
                    , perif_addresses, per_safe_insts_in_prog
                    , peripheral_specs=(), mmio_settings=None
                    , allow_privilege_switch=True, emit_initial_mmio_store=True
                    , peripheral_replay="compressed-mmio", debug_program_percent=0):
    
    #write to file
    write_c_frame_start(file_p, num_nops_at_start, max_syscall_prob, core_os\
            , num_inst_in_prog, perif_addresses, mmio_settings=mmio_settings
            , allow_privilege_switch=allow_privilege_switch
            , emit_initial_mmio_store=emit_initial_mmio_store
            , emit_debug_trigger=usedebugtrigger(debug_program_percent))
    
    # determine the sequence of instructions
    # first half will be simple insts and rest will be all insts
    num_first_half_insts = int((num_inst_in_prog*per_safe_insts_in_prog)/100)
    op_seq = [random.choice(first_opcode_list) for i in range( num_first_half_insts )] 
    op_seq += [random.choice(opcode_list) for i in range(num_inst_in_prog - len(op_seq))]


    for i in range(len(op_seq)): 
        if (random.randint(0,99) < syscall_prob): op_seq[i] = 'syscall'

    # create the insts from the sequence
    inst_seq = []
    syscall_no = 0
    for op in op_seq: 
        if op in ['syscall']: # syscalls and other special insts
            for inst in create_syscall(core_os, syscall_ids, perif_addresses, syscall_no, mmio_settings=mmio_settings): file_p.write(inst + " \n")
            syscall_no += 1
        else: # normal insts
            inst_data = inst_list_all_w_ext[op]
            write_asm(create_inst(op[0], inst_data, file_p, 'fuzz'), file_p)
    
    write_c_frame_end(file_p, num_nops_at_end)
    
    file_p.close()


#Writes C start framework into program file (like int main, libraries, ect)
def write_c_frame_start(f_inst, num_nops_at_start, max_syscall_prob, core_os\
        , num_inst_in_prog, perif_addresses, commands=[], mmio_settings=None
        , allow_privilege_switch=True, emit_initial_mmio_store=True
        , emit_debug_trigger=False):

    if mmio_settings is None:
        raise ValueError(f"MMIO settings are required for core OS: {core_os}")

    inst_no = random.randint(0,num_nops_at_start-1)
    
    line = '#include <stdio.h>\n#include <stdint.h>\n\n'
    if allow_privilege_switch:
        line += f"extern void switch2user();\n"

    addrs = []
    if commands:
        addrs = [
            hex(command["address"]) if isinstance(command, dict) else command[1]
            for command in commands
        ]
    for i in range(len(addrs), num_inst_in_prog):
        rand_base_addr_hex = random.choice(perif_addresses) # base address
        rand_offset_hex = (random.randint(0, 0x200)) # offset 
        rand_addr_hex = rand_base_addr_hex + (rand_offset_hex * mmio_settings["alignment"])
        addrs.append(hex(rand_addr_hex))

    datas = []
    if commands:
        datas = [
            hex(command["data"]) if isinstance(command, dict) else command[2]
            for command in commands
        ]
    datas += [hex(random.randint(0, (2 ** mmio_settings["word_bits"]) - 1)) for _ in range(len(datas), num_inst_in_prog)]

    nop = "0x0000001300000013" if mmio_settings["word_bits"] == 64 else "0x00000013"
    nops = [nop] * 8
    c_type = mmio_settings["c_scalar_type"]
    alignment = mmio_settings["alignment"]
    line += f"const {c_type} padd1[8]                 __attribute__((aligned({alignment})))  = {{{ ', '.join(nops) }}};\n";
    line += f"const {c_type} addr[{num_inst_in_prog}] __attribute__((aligned({alignment})))  = {{ {', '.join(addrs)} }};\n";
    line += f"const {c_type} padd2[8]                 __attribute__((aligned({alignment})))  = {{{ ', '.join(nops) }}};\n";
    line += f"const {c_type} data[{num_inst_in_prog}] __attribute__((aligned({alignment})))  = {{ {', '.join(datas)} }};\n";
    line += f"const {c_type} padd3[8]                 __attribute__((aligned({alignment})))  = {{ {', '.join(nops)} }};\n\n";

    line += 'int main(void)\n{\n'

    # randomly enter debug mode
    if emit_debug_trigger:
        line += writedebugtrigger(core_os)

    if allow_privilege_switch and random.choice([0,1]):
        line += f"switch2user();\n"

    if max_syscall_prob > 0:
        line = line + (f'{c_type} rdata;\n')

    if emit_initial_mmio_store:
        line += f'asm volatile("{mmio_settings["load_mnemonic"]} t0, %0; {mmio_settings["load_mnemonic"]} t1, %1; {mmio_settings["store_mnemonic"]} t0, 0(t1);" :: "m"(data[0]), "m"(addr[0]) : "t0", "t1", "memory");\n'
    for i in range(0,num_nops_at_start): #add 4 nop instructions
        if i == inst_no:
            line = line + 'asm volatile ( "L_b_non_prof: ADDI x0, x0, 0" );\n'
        else:
            line = line + 'asm volatile ( "ADDI x0, x0, 0" );\n'

    f_inst.write(line + "\n")


#Writes C end framework into program file (return 0, ect)
def  write_c_frame_end(f_inst, num_nops_at_end):
    line = ""
    for i in range(0,num_nops_at_end): #add nop instructions
        line = line + 'asm volatile ( "ADDI x0, x0, 0" );\n' 

    line = line + '\nreturn 0;\n}'
    f_inst.write(line + "\n")
    

def create_inst(inst_op, inst_data, f_inst=None, run_type ='fuzz', src1='NONE'):
    from riscv_isa import priv_reg 
    key = inst_data[0]
    inst = inst_op
    i_type = inst_data[1]

    if i_type == 'r': 
        dest = "x" + str(random.randint(0,31))
        src1 = "x" + str(random.randint(0,31))

        if key == 'Shifts' and (inst[-1]=='I' or inst[-2:]=='IW'):
            src2 = str(random.randint(0,31))
        else:
            src2 = "x" + str(random.randint(0,31))

        inst = inst + " " + dest + "," + src1 + "," + src2

    if i_type == 'r1':
        dest = "x" + str(random.randint(0,31))
        src1 = "x" + str(random.randint(0,31))
        src2 = str(random.randint(0,63))
        inst = inst + " " + dest + "," + src1 + "," + src2

    if i_type == 'r2': 
        dest = "x" + str(random.randint(0,31))
        src1 = "x" + str(random.randint(0,31))
        src2 = "x" + str(random.randint(0,31))

        atomic_type = random.choice(['', '.AQ', '.RL'])
        inst = inst + atomic_type

        if key == 'Load Reserved':
            inst = inst + " " + dest + "," + "(" + src1 + ")"
        else:
            inst = inst + " " + dest + "," + src1 + "," + "(" + src2 + ")"

    elif i_type == 'i': 
        dest = "x" + str(random.randint(0,31))
        if key == 'CSR Access':
            if src1 == 'NONE':
                src1 = random.choice(priv_reg)
        else:
            src1 = "x" + str(random.randint(0,31))

        if inst in ['CSRRW', 'CSRRS', 'CSRRC']: 
            imm = "x" + str(random.randint(0,31))
        elif inst in ['CSRRWI', 'CSRRSI', 'CSRRCI']: 
            imm = str(random.randint(0,31))
        else:
            imm = str(random.randint(-2048,2047)) 

        if (key == 'Counters'):
            inst = inst + " " + dest
        elif (key == 'Loads'):
            inst = inst + " " + dest + ", " + imm + "(" + src1 + ")"
        else: 
            inst = inst + " " + dest + "," + src1 + "," + imm

    elif i_type == 'i1':
        arg1 = random.choice(['','i']) + random.choice(['','o'])\
               + random.choice(['','r']) + random.choice(['','w'])
        if arg1 != '':
            arg1 = ' ' + arg1
        arg2 = random.choice(['','i']) + random.choice(['','o'])\
               + random.choice(['','r']) + random.choice(['','w'])
        if arg1 == '' or arg2 == '':
            arg1 = ''
            arg2 = ''
        elif arg2 != '':
            arg2 = ' ,' + arg2

        inst = inst + arg1 + arg2

    elif i_type == 'i2': 
        inst = inst

    elif i_type in ['u','j']:
        dest = "x" + str(random.randint(0,31))
        imm = str(random.randint(0,1048575)) 
        if (inst == 'JAL'):
            imm = str(random.randint(int("800010d0",16),int("80001f50",16)))
            imm = str(int(int(int(imm)/2)*2))
            inst = inst + " " + dest + "," + imm
            inst = "ADDI x0, x0, 0"
        else:
            inst = inst + " " + dest + "," + imm

    elif i_type == 's':
        safe_store = 0
        src1 = "x" + str(random.randint(0,31))
        src2 = "x" + str(random.randint(0,31))
        dest = "x" + str(random.randint(0,31))
        if inst == 'SB' and safe_store:
            imm_temp = str(2047)
            inst_temp = "ADDI "+src1+", x0, "+imm_temp
            
            if f_inst == None:
                print("***Warning: unable to do safe_store")
            else:
                write_asm(inst_temp, f_inst)
            imm = str(2047) 
        else:
            imm = str(random.randint(-2048,2047)) 
            
        inst = inst + " " + dest + ", " + imm + "(" + src1 + ")"

    elif i_type == 'b':
        dest = "x" + str(random.randint(0,31))
        src1 = "x" + str(random.randint(0,31))
        src2 = "x" + str(random.randint(0,31))
        imm = str(random.randint(int("800010d0",16),int("80001f50",16))) 
        imm = str(int(int(int(imm)/2)*2))
        if (run_type == 'prof'):
            inst = inst + " " + src1 + "," + src2 + "," + "L_b"
            imm = random.randint(0,127)
            for i in range(0,128):
                if i == imm:
                    label = "L_b: "
                else:
                    label = ""
                f_inst.write("\n")
                line = 'asm volatile ( "' + label + ' ADDI x0, x0, 0" );'
                f_inst.write(line)
        elif run_type == 'fuzz':
            inst = inst + " " + src1 + "," + src2 + "," + "L_b_non_prof"
        elif run_type == 'rand':
            inst = inst + " " + src1 + "," + src2 + "," + imm
        else:   
            print("ERROR: unknown run type found: ", run_type)
            print(inst_op, inst_data)
            exit()

        f_inst.write("\n")

    return inst


def write_asm(inst, f_inst):

    line = 'asm volatile ( "' + inst + '" );'
    f_inst.write(line + "\n")

def cmp_inst(exp_inst, result_inst):
    if len(exp_inst) != len(result_inst):
        return 0

    for exp_c, result_c in zip(exp_inst, result_inst):
        if not (exp_c == 'x' or (exp_c == result_c)):
            return 0
    return 1


def gen_all_inst_files(del_repo, check_all_prog_files\
                       , inst_output_path \
                       , num_inst_in_prog, num_itr_per_inst, inst_list\
                       , num_nops_at_start, num_nops_at_end\
                       , sw_dir, nop_inst_bin_32, no_threads=1\
                       , trash_dir='/tmp/', debug_print=False):
   
    if del_repo:
        fuzz_utils.delete_dir(inst_output_path, True, 'move', f"{trash_dir}/prog_gen_{uuid.uuid1()}")

    op_cnt = 0
    for inst_op, inst_data in tqdm(inst_list.items(), desc="----Generating programs"):
        for itr_cnt in range(num_itr_per_inst):
            
            file_name = "inst_file_" + str(op_cnt) + "_itr_" + str(itr_cnt)\
                        + ".c" 
            f_inst = open(os.path.join(inst_output_path, file_name),'w')
    
    
            write_c_frame_start(f_inst, num_nops_at_start)
    
            if str(inst_data[6]) == "1":
                num_inst_in_prog_local = 1
            else: 
                num_inst_in_prog_local = num_inst_in_prog

            for j in range(num_inst_in_prog_local):
                inst = create_inst(inst_op[0], inst_data,f_inst, 'prof')
                write_asm(inst, f_inst)
    
            write_c_frame_end(f_inst, num_nops_at_end)
    
            f_inst.close()
        
        op_cnt = op_cnt + 1
  
    print("----compiling programs")
    compile_programs(
        sw_dir,
        inst_output_path,
        no_threads,
        debug_print,
        generate_dumps=check_all_prog_files,
    )
    print("----compiling programs done")

    print("----checking generated programs")
    if check_all_prog_files:
        op_cnt = 0
        error = 0
        for inst_op, inst_data in inst_list.items():

            if inst_op[0] in ['BEQ', 'BNE', 'BLT', 'BGE', 'BLTU', 'BGEU']: 
                op_cnt = op_cnt + 1
                continue

            if str(inst_data[6]) == "1":
                num_inst_in_prog_local = 1
            else: 
                num_inst_in_prog_local = num_inst_in_prog

            num_inst_in_main = num_nops_at_start + num_inst_in_prog_local \
                               + num_nops_at_end
            op_bin = inst_data[4]
            funct3_bin = inst_data[3]
            funct7_bin = inst_data[2]
            exp_inst = funct7_bin + "x"*10 + funct3_bin + "x"*5 + op_bin
            exp_inst_list = [nop_inst_bin_32]*num_nops_at_start\
                            + [exp_inst]*num_inst_in_prog_local\
                            + [nop_inst_bin_32]*num_nops_at_end
            error = 0
            for itr_cnt in range(num_itr_per_inst):
    
                file_name = "inst_file_" + str(op_cnt) + "_itr_" + str(itr_cnt)\
                            + ".riscv.dump" 
                try:
                    f_inst = open(os.path.join(inst_output_path,file_name),'r')
                except FileNotFoundError :
                    print("couldnt find file:" , op_cnt, inst_op, itr_cnt)
                    error = 1
                    break
        
                inside_main = 0
                result_inst_list = []
                inst_main_cnt = 0
                f_inst_lines = f_inst.readlines()
                for line in f_inst_lines:
                    if inside_main == 0:
                        if re.match("[0-9a-f]* <main>:", line):
                            inside_main = 1
                        continue
                  
                    inst_re = "[^0-9a-f]*[0-9a-f]+:[^0-9a-f]+([0-9a-f]+)"
                    if not re.match(inst_re, line):
                        continue

                    result_inst = re.match(inst_re, line).group(1)
                    if len(result_inst) == 4:
                        result_inst = "{0:016b}".format(int(result_inst, 16))
                    else:
                        result_inst = "{0:032b}".format(int(result_inst, 16))
                    result_inst_list.append(result_inst) 
                    inst_main_cnt = inst_main_cnt + 1
                    if inst_main_cnt == num_inst_in_main:
                        break
    
                f_inst.close()
    
                if error:
                    break
                if inst_main_cnt != num_inst_in_main:
                    print("couldnt find enough instrns in file:"\
                           , op_cnt, inst_op, itr_cnt)
                    error = 1 
                    break
    
                for result_inst,exp_inst in zip(result_inst_list,exp_inst_list):
                    if not cmp_inst(exp_inst, result_inst):
                        print("inst not matching in file:"\
                              , op_cnt, inst_op, itr_cnt, result_inst, exp_inst\
                              , "{0:08x}".format(int(result_inst,2)) )
                        error = 1
                        break
                if error:
                    break
            
            op_cnt = op_cnt + 1
    print("----checking generated programs done")
