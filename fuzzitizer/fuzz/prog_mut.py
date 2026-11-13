
import os, random, re
import logging as lg
from tqdm import tqdm

import fuzz_utils


def bits(data, start_index, stop_index):
    l = len(data)
    return data[l-start_index-1:l-stop_index]

def cmp_inst_fields(target_inst, inst_data):

    for b, b_ref in zip(bits(target_inst,6,0), inst_data[4]):
        if not (b_ref == 'x' or (b == b_ref)):
            return 0

    for b, b_ref in zip(bits(target_inst,14,12), inst_data[3]):
        if not (b_ref == 'x' or (b == b_ref)):
            return 0

    for b, b_ref in zip(bits(target_inst,31,25), inst_data[2]):
        if not (b_ref == 'x' or (b == b_ref)):
            return 0
    return 1



def inst_hex_to_bin(inst_h):
	try:
		inst_bin = (bin(int(inst_h,16)))
		inst_bin = inst_bin[2:]
		inst_bin = inst_bin.zfill(32)

	except:
		inst_bin = "00010101000000000000000000000000"

	return inst_bin


def inst_bin_to_hex(inst_bin):

	inst_h = hex(int(inst_bin,2))
	inst_h = inst_h[2:]
	inst_h = inst_h.zfill(8)
	return inst_h


def reverse_inst_bytes(inst): 
    inst_bytes = [inst[i*2:(i*2)+2] for i in range(4)]
    return ''.join(inst_bytes[::-1])

def cal_m_index(inst_data, num_bits, bits_type='data'):
    m_index = []
    avail_index = []

    if (inst_data == 0):
        mask = "x"*32
    elif (inst_data == 1):
        if bits_type == 'data': 
            mask = "0"*21+"x"*8+"0"*3
        else: 
            mask = "x"*32
    elif (bits_type == 'data'):

        mask = inst_data[2] + "x"*10 + inst_data[3] + "x"*5 + inst_data[4]






        if inst_data[8] in ['LR.W', 'LR.D']:
            mask = mask[0:7] + '0'*5 + mask[12:]
        if inst_data[8] in ['ECALL', 'EBREAK']:
            mask = '0'*32
    elif (bits_type == 'all'):

        mask = "x"*30 + '11'
    elif (bits_type == 'opcode'):

        mask_n = inst_data[2] + "x"*10 + inst_data[3] + "x"*5 + inst_data[4]

        if inst_data[8] in ['LR.W', 'LR.D']:
            mask_n = mask_n[0:7] + '0'*5 + mask_n[12:]
        if inst_data[8] in ['ECALL', 'EBREAK']:
            mask_n = '0'*32

        mask = ''
        for bit in mask_n:
            bit_reversed = 'x' if bit!='x' else '0' 
            mask += bit_reversed


        mask = mask[0:30] + '11'
        
    else:
        print('Error: Unknown bits type found when mutating', bits_type \
               , inst_data, num_bits)

    mask = mask[::-1]


    index = 0
    for bit in mask:
        if bit == 'x':
            avail_index.append(index)
        index = index + 1

    if len(avail_index) < num_bits:
        m_index = avail_index
    else:
        m_index_start = random.randint(0, len(avail_index)-1)    
        avail_index = avail_index + avail_index
        m_index = avail_index[m_index_start:m_index_start+num_bits]

    return m_index


def bitflip(mut, inst_type, num_bits):

    m_index = cal_m_index(inst_type, num_bits)

    mut_list = [b for b in mut]
    for i in m_index:
        mut_list[i] = '0' if mut_list[i] == '1' else '1'

    mut = ''.join(mut_list)
    
    return mut



def arith(mut, inst_type, num_bytes):

    if not num_bytes in [1,2]:
        print("Error. invalid num of bytes to arith function")
        exit()


    m_index = cal_m_index(inst_type, 8*num_bytes)


    if len(m_index) == 0:
        return mut

    mut_list = [b for b in mut]
    mut_byte_list = [mut_list[i] for i in m_index]
    mut_byte = ''.join(mut_byte_list)
    mut_byte = int(mut_byte,2)


    rand_int = random.randint(-35,35)
    mut_byte = mut_byte + rand_int


    if num_bytes == 1:
        mut_byte = (mut_byte + 2**8 -1) if mut_byte<0 else mut_byte
    elif num_bytes == 2:
        mut_byte = (mut_byte + 2**16 -1) if mut_byte<0 else mut_byte


    if num_bytes == 1:
        mut_byte = "{0:08b}".format(mut_byte)
    elif num_bytes == 2:
        mut_byte = "{0:016b}".format(mut_byte)

    num_bits = len(m_index)
    byte_num = 0
    for i in m_index:
        mut_list[i] = mut_byte[-len(m_index) + byte_num]
        byte_num = byte_num + 1

    mut = ''.join(mut_list)

    return mut


def bitflip_1(mut, inst_type):   return bitflip(mut, inst_type, 1)
def bitflip_2(mut, inst_type):   return bitflip(mut, inst_type, 2)
def bitflip_4(mut, inst_type):   return bitflip(mut, inst_type, 4)
def byte_flip(mut, inst_type):   return bitflip(mut, inst_type, 8)
def byte_flip_16(mut, inst_type):return bitflip(mut, inst_type, 16)
def arith_8(mut, inst_type):     return arith(mut, inst_type, 1)
def arith_16(mut, inst_type):    return arith(mut, inst_type, 2)
def random_8(mut, inst_type):    return my_random(mut, inst_type, 8, 'data')
def random_8_any(mut, inst_type):    return my_random(mut, inst_type, 8, 'all')
def opcode_mut(mut, inst_type):    return my_random(mut, inst_type, 32, 'opcode')


def my_random(mut, inst_type, num_bits, bits_type):

    if inst_type == 0: 
        m_index = [i for i in range(num_bits)]
    elif inst_type == 1: 
        if bits_type == 'data':
            m_index = [3,4,5,6,7,8,9,10]
        else: 
            m_index = [i for i in range(num_bits)]
    else: 
        m_index = cal_m_index(inst_type, num_bits, bits_type)

    mut_list = [b for b in mut]
    for i in m_index:
        mut_list[i] = str(random.randint(0,1))

    mut = ''.join(mut_list)
    
    return mut


def delete(mut, inst_type, nop_inst_bin_32):            
    mut = nop_inst_bin_32[::-1]
    return mut












def clone(mut, inst_type, replace_inst): 

    replace_inst = replace_inst[::-1]
    return replace_inst



def gen_mut_files(ip_hex_files, out_dir\
                  , inst_list_all_w_ext, instr_list, hex_file_itr_re\
                  , num_inst_in_prog_prof, nop_inst_bin_32, hex_file_mut_t, val_muts):


    fuzz_utils.delete_dir(out_dir)
    
    for hex_file_in in tqdm(ip_hex_files, desc="----Mutating progs"):
        filename = os.path.basename(hex_file_in)

        if not re.match(hex_file_itr_re, filename):
            continue
        inst = re.match(hex_file_itr_re, filename)
   
        instr_no = int(inst.group(1))
        inst_data = list((instr_list.items()))[instr_no]
        inst_data_clone = inst_data[1]
        inst_op_clone = inst_data[0]
        lg.debug(f"{inst_data_clone}, {inst_op_clone}")




        for m_type in val_muts:
            if (str(inst_data_clone[6]) == "1"):
                no_of_files = num_inst_in_prog_prof
            else:
                no_of_files = 1
            inst_bin_i_prev = -1
            for inst_no in range(no_of_files):

                hex_file_out = hex_file_mut_t.substitute(\
                                             file_no = str(inst.group(1)), \
                                             file_itr = str(inst.group(2)), \
                                             mut = str(m_type), \
                                             inst_no = str(inst_no))
             
                hex_file_out = os.path.join(out_dir, hex_file_out)
                mem_file_out = hex_file_out.replace(".hex", ".mem")



                hex_file_in_f = open(hex_file_in, 'r')
                hex_file_out_f = open(hex_file_out, 'w')
        
                mut_state = 0
                line_number = 0
                for line in hex_file_in_f.readlines():


                    inst_addr_h = line[1:9]
                    inst_a_h    = line[10:18]
                    inst_b_h    = line[19:27]
                    inst_c_h    = line[28:36]
                    inst_d_h    = line[37:45]

                    if (inst_a_h == "00000013" and inst_b_h == "00000013" \
                        and inst_c_h == "00000013" and inst_d_h == "00000013"): 

                            if (mut_state == 0):
                                    mut_state = 1
                            elif (mut_state == 2):
                                    mut_state = 3


                            hex_file_out_f.write(line)

                    elif (mut_state == 1 or mut_state == 2): 
                        mut_state = 2

                        line.strip('\n')
                                      


                        inst_bin = [0,0,0,0]
                        inst_bin[0]    = inst_hex_to_bin(inst_a_h)
                        inst_bin[1]    = inst_hex_to_bin(inst_b_h) 
                        inst_bin[2]    = inst_hex_to_bin(inst_c_h) 
                        inst_bin[3]    = inst_hex_to_bin(inst_d_h)  
                        
                        for inst_i in [0,1,2,3]:
                            inst_bin_i = inst_bin[inst_i]




                            if (inst_bin_i == nop_inst_bin_32): 
                                inst_bin[inst_i] = inst_bin_i
                                continue


                            inst_bin_i_orig = inst_bin_i


                            if (inst_bin_i_prev!=-1):
                                inst_bin_i = inst_bin_i_prev
                            else: 
                                inst_bin_i = inst_bin_i[::-1]


                            i = inst_data_clone + [inst_op_clone[0]]


















                            if   (m_type == 0): inst_bin_i = bitflip_1(inst_bin_i,i)    
                            elif (m_type == 1): inst_bin_i = bitflip_2(inst_bin_i,i)
                            elif (m_type == 2): inst_bin_i = bitflip_4(inst_bin_i,i)
                            elif (m_type == 3): inst_bin_i = arith_8(inst_bin_i,i)
                            elif (m_type == 4): inst_bin_i = arith_16(inst_bin_i,i)
                            elif (m_type == 5): inst_bin_i = random_8(inst_bin_i,i)
                            elif (m_type == 6): inst_bin_i = byte_flip(inst_bin_i,i)
                            elif (m_type == 7): inst_bin_i = byte_flip_16(inst_bin_i,i)                   
                            else: print("Error: Incorrect Mutation")

                            inst_bin[inst_i] = inst_bin_i[::-1]
                            inst_bin_i_prev = inst_bin_i






                        inst_a    = inst_bin_to_hex(inst_bin[0]) 
                        inst_b    = inst_bin_to_hex(inst_bin[1])
                        inst_c    = inst_bin_to_hex(inst_bin[2])
                        inst_d    = inst_bin_to_hex(inst_bin[3])
                        

                        line = line[0] + inst_addr_h + " " + inst_a + " " + inst_b + " " + inst_c + " " + inst_d
                        


                        hex_file_out_f.write(line + "\n")

                    else:
                        hex_file_out_f.write(line)
                    
                    line_number = line_number + 1
    
                hex_file_in_f.close()
                hex_file_out_f.close()


                fuzz_utils.hex_to_mem(hex_file_out, mem_file_out)









def get_prog_lines_to_mut(prog_lines, hex_file_type, nop_inst_hex_32): 
    if hex_file_type == 'hex': 
        nop_line = ' '.join([nop_inst_hex_32]*4)
    elif hex_file_type == 'opn': 
        nop_inst_hex_32_rev = reverse_inst_bytes(nop_inst_hex_32)
        nop_line = ' '.join([''.join( [nop_inst_hex_32_rev]*2 )] *4)
    elif hex_file_type == 'cal':
        nop_bytes = [
            reverse_inst_bytes(nop_inst_hex_32)[i:i + 2]
            for i in range(0, 8, 2)
        ]
        nop_line = ' '.join(nop_bytes * 4).lower()

        first_nop_user_prog = None
        got_user_prog = False
        last_nop_user_prog = None
        for line_i, line in enumerate(prog_lines):
            is_nop_line = line.strip().lower() == nop_line
            if first_nop_user_prog is None:
                if is_nop_line:
                    first_nop_user_prog = line_i
            elif not got_user_prog:
                if not is_nop_line:
                    got_user_prog = True
            elif is_nop_line:
                last_nop_user_prog = line_i
                break

        if first_nop_user_prog is None or last_nop_user_prog is None:
            raise ValueError("could not find Caliptra user-program NOP delimiters")
        return {
            'user_prog': list(range(first_nop_user_prog, last_nop_user_prog)),
            'datas': [],
            'addrs': [],
        }
    else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"
  


    first_nop_user_prog = -1
    got_user_prog = 0
    last_nop_user_prog = -1

    got_main_end = 0
    last_nop_main_end = -1

    got_datas = 0
    last_nop_datas = -1

    got_addrs = 0
    last_addrs = -1
    for line_i, line in enumerate(prog_lines): 
        if first_nop_user_prog == -1:
            if nop_line in line: first_nop_user_prog = line_i
        elif not got_user_prog:
            if not nop_line in line: got_user_prog = 1
        elif last_nop_user_prog == -1:
            if nop_line in line: last_nop_user_prog = line_i

        elif not got_main_end:
            if not nop_line in line: got_main_end = line_i
        elif last_nop_main_end == -1:
            if nop_line in line: last_nop_main_end = line_i

        elif not got_datas:
            if not nop_line in line: got_datas = line_i
        elif last_nop_datas == -1:
            if nop_line in line: last_nop_datas = line_i

        elif not got_addrs:
            if not nop_line in line: got_addrs = line_i
        elif last_addrs == -1:
            if nop_line in line: last_addrs = line_i



    lines = {}
    lines['user_prog'] = [i for i in range(first_nop_user_prog, last_nop_user_prog)]
    lines['datas']     = [i for i in range(last_nop_main_end+1, last_nop_datas)]
    lines['addrs']     = [i for i in range(last_nop_datas+1, last_addrs)]
    return lines










def parse_inst_from_prog(prog_lines, hex_file_type):
    if hex_file_type == 'hex': 
        return [line[10+(i*9) : 10+(i*9)+8] for line in prog_lines for i in range(4)]
    elif hex_file_type == 'opn': 
        prog_insts = {}
        for line_type, lines in prog_lines.items():
            prog_insts[line_type] = []
            for line in lines: 
                twin_insts = [line[(i*17) : (i*17)+16] for i in range(4)]
                line_bytes = [twin_inst[(i*2):(i*2)+2] for twin_inst in twin_insts for i in range(8)]
                prog_insts[line_type] += [''.join(line_bytes[i:i+4][::-1]) for i in range(0,len(line_bytes),4)]
        return prog_insts
    elif hex_file_type == 'cal':
        prog_insts = {}
        for line_type, lines in prog_lines.items():
            prog_insts[line_type] = []
            for line in lines:
                byte_tokens = line.split()
                if len(byte_tokens) != 16:
                    raise ValueError(
                        f"Caliptra program line must contain 16 bytes: {line.rstrip()}"
                    )
                prog_insts[line_type] += [
                    ''.join(byte_tokens[i:i + 4][::-1]).lower()
                    for i in range(0, 16, 4)
                ]
        return prog_insts
    else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"
    return





def det_mut_for_inst(inst_bin, mut_prob_type, inst_list_all_w_ext\
                   , optimizer_sol, val_muts, opc_muts, per_opc_muts): 

    if mut_prob_type == 'optimizer': 

        got_inst = 0
        for inst_op, inst_data in inst_list_all_w_ext.items():
            if cmp_inst_fields(inst_bin, inst_data):
                i = inst_data + [inst_op[0]]
                got_inst = 1
                break
        if got_inst:

            try:
                opt_sol_mut_list = optimizer_sol[inst_op]
            except: 
                opt_sol_mut_list = val_muts
            m_type_frm_opt = random.choice(opt_sol_mut_list)

            m_type_opcode = random.choice(opc_muts)
            m_type = random.choices([m_type_frm_opt, m_type_opcode]\
                                   , weights=[100-per_opc_muts,per_opc_muts], k=1)
            m_type = m_type[0]
        else:
            i = [ "none" , "z" , "xxxxxxx", "xxx", "xxxxxxx"\
                    , "none", "1", 9999 ] + ["none"]
            m_type = random.choice(opc_muts)
    else: assert 0, f"unspecified mut_prob_type {mut_prob_type}"

    return i, m_type





def mut_insts(prog_insts, mutation_prob, mut_prob_type, inst_list_all_w_ext\
            , optimizer_sol, val_muts, opc_muts, nop_inst_bin_32, per_opc_muts): 

    mutated_insts = {}





    insts_to_mut = prog_insts['user_prog']
    insts_to_mut_bin = [inst_hex_to_bin(inst) for inst in insts_to_mut]

    mutated_insts['user_prog'] = []
    prev_auipc = False
    for inst, inst_bin in zip(insts_to_mut, insts_to_mut_bin): 

        inst_bin_rev = inst_bin[::-1]


        if (inst_bin == nop_inst_bin_32): 
            mutated_insts['user_prog'].append(inst); continue


        elif (bits(inst_bin, 6,0) in ['0000011', '0100011'] \
                and  bits(inst_bin, 14,12) == '011'):
            mutated_insts['user_prog'].append(inst); continue

        elif (bits(inst_bin, 6,0) in ['0010111']): 
            prev_auipc = True
            mutated_insts['user_prog'].append(inst); continue
        elif prev_auipc: 
            prev_auipc = False
            mutated_insts['user_prog'].append(inst); continue
                       

        if (random.randint(0,100) > mutation_prob): 
            mutated_insts['user_prog'].append(inst)
            continue


        i, m_type = det_mut_for_inst(inst_bin, mut_prob_type, inst_list_all_w_ext\
                   , optimizer_sol, val_muts, opc_muts, per_opc_muts)


        if   (m_type == 0): inst_bin_rev_mutated = bitflip_1(inst_bin_rev,i)    
        elif (m_type == 1): inst_bin_rev_mutated = bitflip_2(inst_bin_rev,i)
        elif (m_type == 2): inst_bin_rev_mutated = bitflip_4(inst_bin_rev,i)
        elif (m_type == 3): inst_bin_rev_mutated = arith_8(inst_bin_rev,i)
        elif (m_type == 4): inst_bin_rev_mutated = arith_16(inst_bin_rev,i)
        elif (m_type == 5): inst_bin_rev_mutated = random_8(inst_bin_rev,i)
        elif (m_type == 6): inst_bin_rev_mutated = byte_flip(inst_bin_rev,i)
        elif (m_type == 7): inst_bin_rev_mutated = byte_flip_16(inst_bin_rev,i)                   
        elif (m_type == 8): inst_bin_rev_mutated = random_8_any(inst_bin_rev,i)
        elif (m_type == 9): inst_bin_rev_mutated = delete(inst_bin_rev,i\
                                            , nop_inst_bin_32)
        elif (m_type == 10): inst_bin_rev_mutated = clone(inst_bin_rev,i\
                                 , random.choice(insts_to_mut_bin))
        elif (m_type == 11): inst_bin_rev_mutated = opcode_mut(inst_bin_rev, i) 
        else: print("Error: Incorrect Mutation")


        inst_bin_mutated = inst_bin_rev_mutated[::-1]
        mutated_insts['user_prog'].append(inst_bin_to_hex(inst_bin_mutated))



    insts_to_mut = prog_insts['datas']
    insts_to_mut_bin = [inst_hex_to_bin(inst) for inst in insts_to_mut]
    mutated_insts['datas'] = []
    for inst, inst_bin in zip(insts_to_mut, insts_to_mut_bin): 
        inst_bin_rev = inst_bin[::-1]


        if (inst_bin == nop_inst_bin_32): 
            mutated_insts['datas'].append(inst); continue


        if (random.randint(0,100) > mutation_prob): 
            mutated_insts['datas'].append(inst)
            continue

        m_type = random.choice(val_muts)
        m_type_rand = random.choice([8,10])
        m_type = random.choices([m_type, m_type_rand], weights=[100-per_opc_muts, per_opc_muts], k=1)
        m_type = m_type[0]
        i=0
        if   (m_type == 0): inst_bin_rev_mutated = bitflip_1(inst_bin_rev,i)    
        elif (m_type == 1): inst_bin_rev_mutated = bitflip_2(inst_bin_rev,i)
        elif (m_type == 2): inst_bin_rev_mutated = bitflip_4(inst_bin_rev,i)
        elif (m_type == 3): inst_bin_rev_mutated = arith_8(inst_bin_rev,i)
        elif (m_type == 4): inst_bin_rev_mutated = arith_16(inst_bin_rev,i)
        elif (m_type == 5): inst_bin_rev_mutated = random_8(inst_bin_rev,i)
        elif (m_type == 6): inst_bin_rev_mutated = byte_flip(inst_bin_rev,i)
        elif (m_type == 7): inst_bin_rev_mutated = byte_flip_16(inst_bin_rev,i)                   
        elif (m_type == 8): inst_bin_rev_mutated = random_8_any(inst_bin_rev,i)
        elif (m_type == 10): inst_bin_rev_mutated = clone(inst_bin_rev,i\
                                 , random.choice(insts_to_mut_bin))
        inst_bin_mutated = inst_bin_rev_mutated[::-1]
        mutated_insts['datas'].append(inst_bin_to_hex(inst_bin_mutated))




    insts_to_mut = prog_insts['addrs']
    insts_to_mut_bin = [inst_hex_to_bin(inst) for inst in insts_to_mut]
    mutated_insts['addrs'] = []
    for inst, inst_bin in zip(insts_to_mut, insts_to_mut_bin): 
        inst_bin_rev = inst_bin[::-1]


        if ((inst_bin == nop_inst_bin_32) or (inst == '000000ff')): 
            mutated_insts['addrs'].append(inst); continue


        if (random.randint(0,100) > mutation_prob): 
            mutated_insts['addrs'].append(inst)
            continue

        m_type = random.choice(val_muts)
        m_type_rand = random.choice([8,10])
        m_type = random.choices([m_type, m_type_rand], weights=[100-per_opc_muts, per_opc_muts], k=1)
        m_type = m_type[0]
        clone_choices = [i for i in insts_to_mut_bin if i not in ['00000000000000000000000011111111', nop_inst_bin_32]]
        i=1
        if   (m_type == 0): inst_bin_rev_mutated = bitflip_1(inst_bin_rev,i)    
        elif (m_type == 1): inst_bin_rev_mutated = bitflip_2(inst_bin_rev,i)
        elif (m_type == 2): inst_bin_rev_mutated = bitflip_4(inst_bin_rev,i)
        elif (m_type == 3): inst_bin_rev_mutated = arith_8(inst_bin_rev,i)
        elif (m_type == 4): inst_bin_rev_mutated = arith_16(inst_bin_rev,i)
        elif (m_type == 5): inst_bin_rev_mutated = random_8(inst_bin_rev,i)
        elif (m_type == 6): inst_bin_rev_mutated = byte_flip(inst_bin_rev,i)
        elif (m_type == 7): inst_bin_rev_mutated = byte_flip_16(inst_bin_rev,i)                   
        elif (m_type == 8): inst_bin_rev_mutated = random_8_any(inst_bin_rev,i)
        elif (m_type == 10): inst_bin_rev_mutated = clone(inst_bin_rev,i\
             , random.choice(clone_choices))
        inst_bin_mutated = inst_bin_rev_mutated[::-1]
        mutated_insts['addrs'].append(inst_bin_to_hex(inst_bin_mutated))

  
    return mutated_insts








def update_lines_to_mut(prog_lines_to_mut, prog_insts_mutated, hex_file_type): 
   
    if hex_file_type in ('hex', 'cal'): num_insts_in_line = 4
    elif hex_file_type == 'opn': num_insts_in_line = 8
    else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"


    for inst_type, lines in prog_lines_to_mut.items(): 
        prog_insts = prog_insts_mutated[inst_type]
        for line_i, line in enumerate(lines): 
            line_first_inst_index = line_i*num_insts_in_line
            line_end_inst_index   = (line_i*num_insts_in_line) + num_insts_in_line - 1
            if hex_file_type == 'hex': 
                prog_lines_to_mut[line_i] = line[0:10] + ' '.join(prog_insts[line_first_inst_index:line_end_inst_index+1]) + '\n'
            elif hex_file_type == 'opn':
                line = ""
                for i in range(4): 
                    for j in range(2): 
                        line += reverse_inst_bytes( prog_insts[line_first_inst_index+(i*2)+j] )
                    line += '\n' if i==3 else ' '
                prog_lines_to_mut[inst_type][line_i] = line
            elif hex_file_type == 'cal':
                instructions = prog_insts[
                    line_first_inst_index:line_end_inst_index + 1
                ]
                byte_tokens = [
                    reverse_inst_bytes(instruction)[i:i + 2]
                    for instruction in instructions
                    for i in range(0, 8, 2)
                ]
                has_lowercase_hex = any(character in 'abcdef' for character in line)
                has_uppercase_hex = any(character in 'ABCDEF' for character in line)
                if has_uppercase_hex or not has_lowercase_hex:
                    byte_tokens = [token.upper() for token in byte_tokens]
                newline = '\n' if line.endswith('\n') else ''
                prog_lines_to_mut[inst_type][line_i] = ' '.join(byte_tokens) + newline
            else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"
            
    return prog_lines_to_mut








def mutate_prog(hex_file_in, hex_file_out, mutation_prob\
              , optimizer_sol, nop_inst_bin_32, inst_list_all_w_ext\
              , val_muts, opc_muts, num_nops_at_start, num_nops_at_end\
              , per_opc_muts, mut_prob_type='optimizer'):

    lg.debug("generating", os.path.basename(hex_file_out), "from"\
            ,os.path.basename(hex_file_in))

    nop_inst_hex_32 = inst_bin_to_hex(nop_inst_bin_32)


    with open(hex_file_in, 'r') as fp: prog_lines = fp.readlines()

    hex_file_type = os.path.splitext(hex_file_in)[1][1:]


    prog_line_indexes_to_mut = get_prog_lines_to_mut(prog_lines, hex_file_type, nop_inst_hex_32)


    prog_lines_to_mut = {
        key: prog_lines[indexes[0]:indexes[-1] + 1] if indexes else []
        for key, indexes in prog_line_indexes_to_mut.items()
    }



    prog_insts = parse_inst_from_prog(prog_lines_to_mut, hex_file_type)



    prog_insts_mutated = mut_insts(prog_insts, mutation_prob, mut_prob_type, inst_list_all_w_ext\
            , optimizer_sol, val_muts, opc_muts, nop_inst_bin_32, per_opc_muts)






   

    prog_lines_to_mut = update_lines_to_mut(prog_lines_to_mut\
                        , prog_insts_mutated, hex_file_type)
    for inst_type, lines in prog_lines_to_mut.items(): 
        for prog_line_index_to_mut, prog_line_to_mut in zip(prog_line_indexes_to_mut[inst_type], lines): 
            prog_lines[prog_line_index_to_mut] = prog_line_to_mut



    with open(hex_file_out, 'w') as fp: 
        for line in prog_lines: 
            fp.write(line)


