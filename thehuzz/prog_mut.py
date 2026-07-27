"""
Created by: Rahul Kande
This script is used to mutate prog files
- Notes: 

- TODOs: 
"""
import subprocess, os, random, sys, re, math
from string import Template
import logging as lg # critical, error, warning, info, debug
from tqdm import tqdm

import thehuzz_utils


def bits(data, start_index, stop_index):
    l = len(data)
    return data[l-start_index-1:l-stop_index]

def cmp_inst_fields(target_inst, inst_data):
    #check opcode
    for b, b_ref in zip(bits(target_inst,6,0), inst_data[4]):
        if not (b_ref == 'x' or (b == b_ref)):
            return 0
    #check funct3
    for b, b_ref in zip(bits(target_inst,14,12), inst_data[3]):
        if not (b_ref == 'x' or (b == b_ref)):
            return 0
    #check funct7
    for b, b_ref in zip(bits(target_inst,31,25), inst_data[2]):
        if not (b_ref == 'x' or (b == b_ref)):
            return 0
    return 1


#function to convert hex instruction to binary
def inst_hex_to_bin(inst_h):
	try: #make sure that instruction is in correct format
		inst_bin = (bin(int(inst_h,16)))
		inst_bin = inst_bin[2:] #removes unnecessary chars (0 and b)
		inst_bin = inst_bin.zfill(32) #pads string with zeros

	except:	 #if not -> just replace it with all nop instruction
		inst_bin = "00010101000000000000000000000000"
			#print(inst_h,"->",inst_bin,"\n") #for testing
	return inst_bin

#function to convert binary instuction to hex
def inst_bin_to_hex(inst_bin):
	#convert back to hex
	inst_h = hex(int(inst_bin,2))
	inst_h = inst_h[2:] #removes unnecessary chars (0 and x)
	inst_h = inst_h.zfill(8) #pads string with zeros
	return inst_h

# invert 4 bytes in 32-bit instrn
def reverse_inst_bytes(inst): 
    inst_bytes = [inst[i*2:(i*2)+2] for i in range(4)]
    return ''.join(inst_bytes[::-1])

def cal_m_index(inst_data, num_bits, bits_type='data'):
    m_index = []
    avail_index = []

    if (bits_type == 'data'):
        #general mask = funct7 + rs2 + rs1 + funct3 + xxxxx + op
        mask = inst_data[2] + "x"*10 + inst_data[3] + "x"*5 + inst_data[4]

        #exceptions:
        #if inst_data[0] in ['System' or 'Sync']:
        #    mask = '0'*32  # nothing can be changed
        #    if inst_data[6] == 'FENCE'
        #        mask = mask[0:4] + 'x'*8 + mask[12:]
        if inst_data[8] in ['LR.W', 'LR.D']:
            mask = mask[0:7] + '0'*5 + mask[12:]
        if inst_data[8] in ['ECALL', 'EBREAK']:
            mask = '0'*32  # no bit can be changed
    elif (bits_type == 'all'):  #only mask the lsb 2 bits which indicate that
                                #instruction is 32 bits
        mask = "x"*30 + '11'
    elif (bits_type == 'opcode'): #mask everything other than opcode bits
        #general mask = funct7 + rs2 + rs1 + funct3 + xxxxx + op
        mask_n = inst_data[2] + "x"*10 + inst_data[3] + "x"*5 + inst_data[4]
        #exceptions:
        if inst_data[8] in ['LR.W', 'LR.D']:
            mask_n = mask_n[0:7] + '0'*5 + mask_n[12:]
        if inst_data[8] in ['ECALL', 'EBREAK']:
            mask_n = '0'*32  # no bit can be changed
        #mask_n masks data bits, reverse it
        mask = ''
        for bit in mask_n:
            bit_reversed = 'x' if bit!='x' else '0' 
            mask += bit_reversed
        #make sure last two bits are always masked since they indicte instrn
        #length
        mask = mask[0:30] + '11'
        
    else:
        print('Error: Unknown bits type found when mutating', bits_type \
               , inst_data, num_bits)

    mask = mask[::-1] #bcz inst data is reversed


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

#function to perform bit flip mutations
def bitflip(mut, inst_type, num_bits):
    #select bits to flip in registers
    m_index = cal_m_index(inst_type, num_bits)

    mut_list = [b for b in mut]
    for i in m_index:
        mut_list[i] = '0' if mut_list[i] == '1' else '1'

    mut = ''.join(mut_list)
    
    return mut

#add +-35 to a byte/bytes
#num_bytes = 1 or 2
def arith(mut, inst_type, num_bytes):

    if not num_bytes in [1,2]:
        print("Error. invalid num of bytes to arith function")
        exit()

    #select bits to flip in registers
    m_index = cal_m_index(inst_type, 8*num_bytes)

    # if no bit to mutate, return directly
    if len(m_index) == 0:
        return mut

    mut_list = [b for b in mut]
    mut_byte_list = [mut_list[i] for i in m_index]
    mut_byte = ''.join(mut_byte_list)
    mut_byte = int(mut_byte,2) #convert to integer    

    #add random # btw 0 and 35 to byte
    rand_int = random.randint(-35,35)
    mut_byte = mut_byte + rand_int

    #bring mut_byte back to range
    if num_bytes == 1:
        mut_byte = (mut_byte + 2**8 -1) if mut_byte<0 else mut_byte
    elif num_bytes == 2:
        mut_byte = (mut_byte + 2**16 -1) if mut_byte<0 else mut_byte

    #convert back to binary
    if num_bytes == 1:
        mut_byte = "{0:08b}".format(mut_byte)
    elif num_bytes == 2:
        mut_byte = "{0:016b}".format(mut_byte)

    num_bits = len(m_index)
    byte_num = 0
    for i in m_index:  #only overwrite bits given by m_index
        mut_list[i] = mut_byte[-len(m_index) + byte_num]
        byte_num = byte_num + 1

    mut = ''.join(mut_list)

    return mut

#functions to perform variable length bit flip mutations
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

#function to perform random mutation
def my_random(mut, inst_type, num_bits, bits_type):
    #select bits to flip 
    m_index = cal_m_index(inst_type, num_bits, bits_type)

    mut_list = [b for b in mut]
    for i in m_index:
        mut_list[i] = str(random.randint(0,1))

    mut = ''.join(mut_list)
    
    return mut

#Mutation that "deletes" (makes no op) the instruction
def delete(mut, inst_type, nop_inst_bin_32):            
    mut = nop_inst_bin_32[::-1]
    return mut
    ##randomly decides to replace instruction with no-op
    #delete_num = random.randint(0,3)
    #if (delete_num == 3): 
    #    if len(mut) == 16: 
    #        mut = nop_inst_16[::-1]
    #    elif len(mut) == 32:
    #        mut = nop_inst_bin_32[::-1]


#Mutation that clones a instruction
#mut --> instruction reversed
#replace_inst --> instruction not reversed
def clone(mut, inst_type, replace_inst): 
    #make sure to invert the replace inst
    replace_inst = replace_inst[::-1]
    return replace_inst


# mutate testcases for profiling
def gen_mut_files(ip_hex_files, out_dir\
                  , inst_list_all_w_ext, instr_list, hex_file_itr_re\
                  , num_inst_in_prog_prof, nop_inst_bin_32, hex_file_mut_t, val_muts):

    #delete previous out log files
    thehuzz_utils.delete_dir(out_dir)
    
    for hex_file_in in tqdm(ip_hex_files, desc="----Mutating progs"):
        filename = os.path.basename(hex_file_in)
        # filter out hex files
        if not re.match(hex_file_itr_re, filename):
            continue
        inst = re.match(hex_file_itr_re, filename)
   
        instr_no = int(inst.group(1))
        inst_data = list((instr_list.items()))[instr_no]
        inst_data_clone = inst_data[1]
        inst_op_clone = inst_data[0]
        lg.debug(f"{inst_data_clone}, {inst_op_clone}")

        #if not int(inst.group(1)) in range(23,25):
        #    continue

        for m_type in val_muts:
            if (str(inst_data_clone[6]) == "1"): # single prog per inst
                no_of_files = num_inst_in_prog_prof
            else:  # all inst in one prog
                no_of_files = 1
            inst_bin_i_prev = -1
            for inst_no in range(no_of_files):
                #for mut_file in range(no_times_to_mut): 
                hex_file_out = hex_file_mut_t.substitute(\
                                             file_no = str(inst.group(1)), \
                                             file_itr = str(inst.group(2)), \
                                             mut = str(m_type), \
                                             inst_no = str(inst_no))
             
                hex_file_out = os.path.join(out_dir, hex_file_out)
                mem_file_out = hex_file_out.replace(".hex", ".mem")
                #print("generating " + mem_file_out.split('/')[-1], end='\r')

                #write new instructions to instruction file 
                hex_file_in_f = open(hex_file_in, 'r')
                hex_file_out_f = open(hex_file_out, 'w')
        
                mut_state = 0
                line_number = 0
                for line in hex_file_in_f.readlines():
	                #Parse input	
	                #these are in hex
                    inst_addr_h = line[1:9]   #instruction address        
                    inst_a_h    = line[10:18] #1st instruction
                    inst_b_h    = line[19:27] #2nd instruction
                    inst_c_h    = line[28:36] #3rd instruction
                    inst_d_h    = line[37:45] #4th instruction

                    if (inst_a_h == "00000013" and inst_b_h == "00000013" \
                        and inst_c_h == "00000013" and inst_d_h == "00000013"): 
                                 #4 nops tells it that it should start/stop mutating
                            if (mut_state == 0):
                                    mut_state = 1
                            elif (mut_state == 2):
                                    mut_state = 3

                            #write line to file
                            hex_file_out_f.write(line)

                    elif (mut_state == 1 or mut_state == 2): 
                        mut_state = 2
                        #only mutate line if it is not nop
                        line.strip('\n') #removes '\n'
                                      
                        #convert instructions to binary and reverse them
                        ###reversing is done so that 0 index in python becomes bit 0
                        inst_bin = [0,0,0,0]
                        inst_bin[0]    = inst_hex_to_bin(inst_a_h)
                        inst_bin[1]    = inst_hex_to_bin(inst_b_h) 
                        inst_bin[2]    = inst_hex_to_bin(inst_c_h) 
                        inst_bin[3]    = inst_hex_to_bin(inst_d_h)  
                        
                        for inst_i in [0,1,2,3]:
                            inst_bin_i = inst_bin[inst_i]

                            #print("start: ", inst_bin_i)

                            #if nop or shouldnt mutate instrn, skip mutation
                            if (inst_bin_i == nop_inst_bin_32): 
                                inst_bin[inst_i] = inst_bin_i
                                continue

                            ###reversing is done so that 0 index in python becomes bit 0
                            inst_bin_i_orig = inst_bin_i
                            # use the prev instruction since this is profiling
                            # stage
                            if (inst_bin_i_prev!=-1):
                                inst_bin_i = inst_bin_i_prev
                            else: 
                                inst_bin_i = inst_bin_i[::-1] #reverse

                            # get the inst type
                            i = inst_data_clone + [inst_op_clone[0]]
                            #got_inst = 0
                            #for inst_op, inst_data in inst_list_all_w_ext.items():
                            #    #print(bits(inst_bin_i_orig,6,0), inst_data[4])
                            #    if cmp_inst_fields(inst_bin_i_orig, inst_data):
                            #        if (inst_bin_i_prev!=-1):
                            #            inst_bin_i = inst_bin_i_prev
                            #        i = inst_data + [inst_op[0]]
                            #        if not (inst_data[7] == inst_data_clone[7]):
                            #            print("clone inst type and actual"\
                            #                    + "inst type not matching")
                            #            print(hex_file_in, hex_file_out)
                            #            print(inst_bin_i_orig, inst_data)
                            #            print(inst_data_clone)
                            #            print(i)
                            #            exit()
                            #        got_inst = 1
                            #        break

                            if   (m_type == 0): inst_bin_i = bitflip_1(inst_bin_i,i)    
                            elif (m_type == 1): inst_bin_i = bitflip_2(inst_bin_i,i)
                            elif (m_type == 2): inst_bin_i = bitflip_4(inst_bin_i,i)
                            elif (m_type == 3): inst_bin_i = arith_8(inst_bin_i,i)
                            elif (m_type == 4): inst_bin_i = arith_16(inst_bin_i,i) #j & r type
                            elif (m_type == 5): inst_bin_i = random_8(inst_bin_i,i)
                            elif (m_type == 6): inst_bin_i = byte_flip(inst_bin_i,i)
                            elif (m_type == 7): inst_bin_i = byte_flip_16(inst_bin_i,i)                   
                            else: print("Error: Incorrect Mutation")
                            #reverse the bits back when storing back to correct 
                            inst_bin[inst_i] = inst_bin_i[::-1]
                            inst_bin_i_prev = inst_bin_i
                            #print("ssoot: ", inst_bin_i[::-1])
                            #print(" ")
                               #print(inst_bin_i)
                               #print(" ")

                        #convert instructions back to hex       
                        inst_a    = inst_bin_to_hex(inst_bin[0]) 
                        inst_b    = inst_bin_to_hex(inst_bin[1])
                        inst_c    = inst_bin_to_hex(inst_bin[2])
                        inst_d    = inst_bin_to_hex(inst_bin[3])
                        
                        #format line for instruction file       
                        line = line[0] + inst_addr_h + " " + inst_a + " " + inst_b + " " + inst_c + " " + inst_d
                        
                        #print line to instruction file 
                        #print(line, end='\n')
                        hex_file_out_f.write(line + "\n")

                    else: #line is not in the range
                        hex_file_out_f.write(line)
                    
                    line_number = line_number + 1
    
                hex_file_in_f.close()
                hex_file_out_f.close()

                #convert the hex file into mem file so that ariane core and emulator can use it to run simulations
                thehuzz_utils.hex_to_mem(hex_file_out, mem_file_out)


"""
Instrns to mut will be padded with multiple nop instrns. 
    - Identify the lines with nop instrns and extract them
    - chipyard 1130, bm: @00000254 00000013 00000013 00000013 00000013
    - rsd, bm: 00000013000000130000001300000013
"""
def get_prog_lines_to_mut(prog_lines, hex_file_type, nop_inst_hex_32, core): 
    #print(nop_inst_hex_32, core)
    if hex_file_type == 'bm': 
        nop_line = ' '.join([nop_inst_hex_32]*4)
    else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"
   
    #print("nop_line: ", nop_line)

    # get first nop line and last nop line, everything in between should be mutated
    first_nop_line_index = -1
    last_nop_line_index = -1
    for line_i, line in enumerate(prog_lines): 
    #    print(line, nop_line)
        if first_nop_line_index == -1: # dint find the first nop line yet
            if nop_line in line: first_nop_line_index = line_i
        else: # keep looking for last nop line
            if nop_line in line: last_nop_line_index = line_i

    # include one line before and after to gather any remaining nop insts as
    # long as there are lines
    first_nop_line_index = max(0, first_nop_line_index-1)
    last_nop_line_index = min(len(prog_lines), last_nop_line_index+1)

    # for thehuzz
    assert (first_nop_line_index != -1), f"Error: No nop line found in {hex_file_type} file"

    # print(first_nop_line_index, last_nop_line_index)
    return [i for i in range(first_nop_line_index, last_nop_line_index+1)]


"""
Extracts instructions from baremetal type/openpiton(pk) prog file
- Line format: @00000000 00000093 00000113 00000193 00000213
    - the 32bit instrns are in the  right order, i.e., 1st instrn is 0000_0093
- Line format: 6f00801f73110134 6308011a2338a104 233cb104f3252034 63d2050893951500
    - Note that first two lines and last line should be ignored
    - the 32bit instrns are in reverse byte order, i.e., 1st instrn is 1f80_006f
"""
def parse_inst_from_prog(prog_lines, hex_file_type, core):
    if hex_file_type == 'bm': 
        return [line[10+(i*9) : 10+(i*9)+8] for line in prog_lines for i in range(4)]
    else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"
    return


"""
Find the instrns to mutate. 
    - These instrns will be padded before and after with nop instrns
"""
def get_prog_insts_to_mut(prog_insts, nop_inst_hex_32, num_nops_at_start, num_nops_at_end): 
    num_nop_insts = 0
    prog_insts_to_mut_indexes = []
    prog_insts_to_mut = []
    state = 'PRE_MUT'
    for i, prog_inst in enumerate(prog_insts): 
        if state == 'PRE_MUT': 
            num_nop_insts = num_nop_insts+1 if (prog_inst == nop_inst_hex_32) else 0
            if (num_nop_insts == num_nops_at_start): 
                state = 'MUT'
                num_nop_insts = 0
        elif state == 'MUT': 
            prog_insts_to_mut_indexes.append(i)
            prog_insts_to_mut.append(prog_inst)
            num_nop_insts = num_nop_insts+1 if (prog_inst == nop_inst_hex_32) else 0
            if (num_nop_insts == num_nops_at_end): 
                prog_insts_to_mut_indexes = prog_insts_to_mut_indexes[:num_nops_at_end*-1] # remove the padding nops
                prog_insts_to_mut= prog_insts_to_mut[:num_nops_at_end*-1] # remove the padding nops
                state = 'POST_MUT'
                num_nop_insts = 0

    return prog_insts_to_mut, prog_insts_to_mut_indexes 

  
"""
Determine the mutation technique to use for the instrn
"""
def det_mut_for_inst(inst_bin, mut_prob_type, inst_list_all_w_ext\
                   , optimizer_sol, val_muts, opc_muts, P=''):

    # Value mutations need the decoded instruction fields. Opcode mutations can
    # still operate when the instruction is not recognized.
    got_inst = 0
    for inst_op, inst_data in inst_list_all_w_ext.items():
        if cmp_inst_fields(inst_bin, inst_data):
            i = inst_data + [inst_op[0]]
            got_inst = 1
            break

    if mut_prob_type == 'optimizer': 
        if got_inst: # recognized the inst type
            #mutations suggested by optimizer:
            try:
                opt_sol_mut_list = optimizer_sol[inst_op]
            except: 
                opt_sol_mut_list = val_muts
            m_type_frm_opt = random.choice(opt_sol_mut_list)
            #also use opcode changing mut techniques sometimes
            m_type_opcode = random.choice(opc_muts)
            m_type = random.choices([m_type_frm_opt, m_type_opcode]\
                                   , weights=[85,15], k=1)
            m_type = m_type[0] # bcz rand choices returns list
        else: # inst type not recognized
            i = [ "none" , "z" , "xxxxxxx", "xxx", "xxxxxxx"\
                    , "none", "1", 9999 ] + ["none"]
            m_type = random.choice(opc_muts)
    elif mut_prob_type == 'random':
        m_type = random.choices(val_muts+opc_muts, k=1)
        m_type = m_type[0]
        i = [ "none" , "z" , "xxxxxxx", "xxx", "xxxxxxx"\
            , "none", "1", 9999 ] + ["none"]

    elif mut_prob_type == 'pso':
        mutation_types = val_muts + opc_muts
        try:
            mutation_weights = [float(weight) for weight in P]
        except (TypeError, ValueError) as exc:
            raise ValueError("PSOFuzz mutation weights must be numeric") from exc
        if len(mutation_weights) != len(mutation_types):
            raise ValueError(
                "PSOFuzz mutation-weight count does not match mutation operators"
            )
        if (
            any(not math.isfinite(weight) or weight < 0
                for weight in mutation_weights)
            or sum(mutation_weights) <= 0
        ):
            raise ValueError(
                "PSOFuzz mutation weights must be finite, nonnegative, "
                "and contain at least one positive value"
            )

        if got_inst:
            available_mutations = mutation_types
            available_weights = mutation_weights
        else:
            available_mutations = opc_muts
            available_weights = mutation_weights[len(val_muts):]
            if sum(available_weights) <= 0:
                available_weights = [1] * len(available_mutations)
            i = [ "none" , "z" , "xxxxxxx", "xxx", "xxxxxxx"\
                , "none", "1", 9999 ] + ["none"]
        m_type = random.choices(
            available_mutations, weights=available_weights, k=1
        )[0]

    else: assert 0, f"unspecified mut_prob_type {mut_prob_type}"

    return i, m_type


"""
Mutate the input list of instrns
"""
def mut_insts(insts_to_mut, mutation_prob, mut_prob_type, inst_list_all_w_ext\
            , optimizer_sol, val_muts, opc_muts, nop_inst_bin_32, P=''):
    mutated_insts = []
    insts_to_mut_bin = [inst_hex_to_bin(inst) for inst in insts_to_mut]

    for inst, inst_bin in zip(insts_to_mut, insts_to_mut_bin): 

        inst_bin_rev = inst_bin[::-1] #reversing is done so that 0 index in python becomes bit 0

        # mutate only mutation_prob percentage of insts
        if (random.randint(0,100) > mutation_prob): 
            mutated_insts.append(inst)
            continue

        # determine mutation technique to use
        i, m_type = det_mut_for_inst(inst_bin, mut_prob_type, inst_list_all_w_ext\
                   , optimizer_sol, val_muts, opc_muts, P)

        # mutate the instrn
        if   (m_type == 0): inst_bin_rev_mutated = bitflip_1(inst_bin_rev,i)    
        elif (m_type == 1): inst_bin_rev_mutated = bitflip_2(inst_bin_rev,i)
        elif (m_type == 2): inst_bin_rev_mutated = bitflip_4(inst_bin_rev,i)
        elif (m_type == 3): inst_bin_rev_mutated = arith_8(inst_bin_rev,i)
        elif (m_type == 4): inst_bin_rev_mutated = arith_16(inst_bin_rev,i) #j & r type
        elif (m_type == 5): inst_bin_rev_mutated = random_8(inst_bin_rev,i)
        elif (m_type == 6): inst_bin_rev_mutated = byte_flip(inst_bin_rev,i)
        elif (m_type == 7): inst_bin_rev_mutated = byte_flip_16(inst_bin_rev,i)                   
        elif (m_type == 8): inst_bin_rev_mutated = random_8_any(inst_bin_rev,i)
        elif (m_type == 9): inst_bin_rev_mutated = delete(inst_bin_rev,i\
                                            , nop_inst_bin_32)
        elif (m_type == 10): inst_bin_rev_mutated = clone(inst_bin_rev,i\
                                 , random.choice(insts_to_mut_bin)) # replace with one inst from all insts
        elif (m_type == 11): inst_bin_rev_mutated = opcode_mut(inst_bin_rev, i) 
        else: print("Error: Incorrect Mutation")

        #reverse the bits back when storing back to correct 
        inst_bin_mutated = inst_bin_rev_mutated[::-1]
        mutated_insts.append(inst_bin_to_hex(inst_bin_mutated))
  
    return mutated_insts


"""
Update the lines to mutate by replacing the orig insts from input hex file with the mutated instrns
    - For each line, if there are any insts to mut, update the line, else write it as it is 
    - chipyard, bm: @00000254 00000013 00000013 00000013 00000013
    - rsd, bm: 00000013000000130000001300000013
"""
def update_lines_to_mut(prog_lines_to_mut, prog_insts_to_mut_indexes, prog_insts\
                      , hex_file_type, core):
   
    if hex_file_type == 'bm': num_insts_in_line = 4
    else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"

    # update lines which had instrns to mutate
    for line_i, line in enumerate(prog_lines_to_mut): 
        line_first_inst_index = line_i*num_insts_in_line
        line_end_inst_index   = (line_i*num_insts_in_line) + num_insts_in_line - 1
        if line_end_inst_index < prog_insts_to_mut_indexes[0]: # dint reach line with insts to mutate
            t = 1 # nothing to do
        elif line_first_inst_index > prog_insts_to_mut_indexes[-1]: # lines after insts to mutate
            t = 1 # nothing to do
        else: # update the line with mutated insts
            if hex_file_type == 'bm': 
                prog_lines_to_mut[line_i] = line[0:10] + ' '.join(prog_insts[line_first_inst_index:line_end_inst_index+1]) + '\n'
            else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"
            
    return prog_lines_to_mut


"""
Extracts instructions from baremetal type/openpiton(pk) prog file
- hex file line format: @00000000 00000093 00000113 00000193 00000213
    - the 32bit instrns are in the  right order, i.e., 1st instrn is 0000_0093
"""
def parse_insts_from_lines(prog_lines, hex_file_type, core):
    if hex_file_type == 'hex':
        if core == 'rsd':
            inst_list = []
            for line in prog_lines:
                inst_list.append(line[-9:-1])
                inst_list.append(line[-17:-9])
                inst_list.append(line[-25:-17])
                inst_list.append(line[-33:-25])
            return inst_list
        else:
            return [line[10+(i*9) : 10+(i*9)+8] for line in prog_lines for i in range(4)]
    else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"
    return


"""
Find the instrns to mutate. 
    - for thehuzz hex file, these instrns will be padded before and after with nop instrns
    - for cascade hex file, its all instructions other than first 16*4 and also one instruction before all 0000000 instrns
    - The second 4 instructions are different between cascade and thehuzz
    - ASSUMES that the first 4 instructions will be fixed for each type\
    - ASSUMES that cascade input will always have more than 16*4+2+14*4 instrs
"""
def get_insts_to_mut(inst_list, nop_inst_hex_32, num_nops_at_start, num_nops_at_end, core):
    insts_to_mut_indexes = []
    insts_to_mut = []
    
    # identify if the format is thehuzz or cascade
#    if inst_list[0:4] == ['00000093', '00000113', '00000193', '00000213'] or \
#       inst_list[0:4] == ['464c457f', '00010102', '00000000', '00000000']: # thehuzz hex file
    if inst_list[6] == '80000000':
        num_nop_insts = 0
        state = 'PRE_MUT'
        for i, inst in enumerate(inst_list): 
            if state == 'PRE_MUT': 
                num_nop_insts = num_nop_insts+1 if (inst == nop_inst_hex_32) else 0
                if (num_nop_insts == num_nops_at_start): 
                    state = 'MUT'
                    num_nop_insts = 0
            elif state == 'MUT': 
                insts_to_mut_indexes.append(i)
                insts_to_mut.append(inst)
                num_nop_insts = num_nop_insts+1 if (inst == nop_inst_hex_32) else 0
                if (num_nop_insts == num_nops_at_end): 
                    insts_to_mut_indexes = insts_to_mut_indexes[:num_nops_at_end*-1] # remove the padding nops
                    insts_to_mut= insts_to_mut[:num_nops_at_end*-1] # remove the padding nops
                    state = 'POST_MUT'
                    num_nop_insts = 0
    elif inst_list[6] == '00000000':
        # first 16 lines and two more instr are prefix and should not be mutated. 16 lines = 16*4 + 2 insts
        # also do not mutate the last 14 lines of instructions
        state = 'ZEROS'
        num_zero_insts = 0
        insts_in_block = []
        insts_in_block_indexes = []
        for i, inst in enumerate(inst_list[(16*4+2):-14*4]): 
            if state == 'ZEROS': # look for next block of code
                if inst != '00000000': 
                    insts_in_block_indexes.append(i + (16*4+2))
                    insts_in_block.append(inst)
                    state = 'MUT'
            elif state == 'MUT': 
                insts_in_block_indexes.append(i + (16*4+2))
                insts_in_block.append(inst)

                # if you see 4 zero insts, stop and dont mutate those 4 + 2 extra insts 
                # which can have the last jump inst
                # - it can happen that there is only 4 zeros + 1 jump inst. we can still do [:-6] bcz python returns empty array anyways
                num_zero_insts = num_zero_insts+1 if (inst == '00000000') else 0
                if (num_zero_insts == 4): 
                    insts_to_mut_indexes += insts_in_block_indexes[:6*-1] # remove the padding nops
                    insts_to_mut += insts_in_block[:6*-1] # remove the padding nops
                    state = 'ZEROS'
                    num_zero_insts = 0
                    insts_in_block = []
                    insts_in_block_indexes = []

        # if the last 4 instructions are not zeros, 
        # make sure not to mutate the last 6 instructions to ensure branch instruction is not mutated
        if not inst_list[:-4] == ['00000000', '00000000', '00000000','00000000']: 
            insts_to_mut_indexes = insts_to_mut_indexes[:6*-1] # remove the padding nops
            insts_to_mut= insts_to_mut[:6*-1] # remove the padding nops

    else: assert 0, f"unknown hex file type found: {inst_list[0:8]}"
    
    return insts_to_mut, insts_to_mut_indexes 


"""
Recreate the prog lines with the new instructions
    - Line format: 
    - bm: @00000254 00000013 00000013 00000013 00000013
    - ASSUMES no of instructions in the file doesnt change
"""
def update_prog_lines(prog_lines, inst_list, hex_file_type, core): 
   
    if hex_file_type == 'hex': num_insts_in_line = 4
    else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"

    # update lines
    new_prog_lines = []
    for line_i, line in enumerate(prog_lines): 
        line_first_inst_index = line_i*num_insts_in_line
        line_end_inst_index   = (line_i*num_insts_in_line) + num_insts_in_line - 1
        
        # update the line with mutated insts
        if hex_file_type == 'hex': 
            new_prog_lines.append(line[0:10] + ' '.join(inst_list[line_first_inst_index:line_end_inst_index+1]) + '\n')
        else: assert 0, f"Unknown hex_file_type found: {hex_file_type}"
            
    return new_prog_lines


"""
Mutate testcase for fuzzing
- First the data to mutate is extracted
- That data is mutated and replaced in the original file to create the mutated file
- Assumes all insts are 32 bit
"""
def mutate_prog(hex_file_in, hex_file_out, mutation_prob\
              , optimizer_sol, nop_inst_bin_32, inst_list_all_w_ext\
              , val_muts, opc_muts, num_nops_at_start, num_nops_at_end\
              , core, hex_file_type='bm', mut_prob_type='optimizer', P=''):

    lg.debug("generating", os.path.basename(hex_file_out), "from"\
            ,os.path.basename(hex_file_in))

    nop_inst_hex_32 = inst_bin_to_hex(nop_inst_bin_32)
    hex_file_type = os.path.splitext(hex_file_in)[1][1:] # there could still be types in each type

    # read the input file
    with open(hex_file_in, 'r') as fp: prog_lines = fp.readlines()

    # get the list of instrns
    inst_list = parse_insts_from_lines(prog_lines, hex_file_type, core)

    # identify instrns to mutate
    insts_to_mut, insts_to_mut_indexes = get_insts_to_mut(inst_list, nop_inst_hex_32, num_nops_at_start, num_nops_at_end, core)

    insts_to_mut_mutated = mut_insts(insts_to_mut, mutation_prob, mut_prob_type, inst_list_all_w_ext\
            , optimizer_sol, val_muts, opc_muts, nop_inst_bin_32, P)
    #print(insts_to_mut_mutated)

    # update prog insts with mutated insts
    for inst_index, inst_mutated in zip(insts_to_mut_indexes, insts_to_mut_mutated): 
        inst_list[inst_index] = inst_mutated
    #print(inst_list)
   
    # update the prog lines with the mutated instrns
    prog_lines = update_prog_lines(prog_lines, inst_list, hex_file_type, core)
    #print(prog_lines)

    # create the mutated prog file
    with open(hex_file_out, 'w') as fp: 
        for line in prog_lines: 
            fp.write(line)


    # # identify the part of file with instrns to mutate
    # prog_line_indexes_to_mut = get_prog_lines_to_mut(prog_lines, hex_file_type, nop_inst_hex_32, core)
    # prog_lines_to_mut = prog_lines[prog_line_indexes_to_mut[0]:prog_line_indexes_to_mut[-1]+1]

    # # parse instructions from the prog file
    # prog_insts = parse_inst_from_prog(prog_lines_to_mut, hex_file_type, core)
    # #print(prog_insts)

    #print("before mutation")

    # prog_insts_to_mut, prog_insts_to_mut_indexes = \
    #         get_prog_insts_to_mut(prog_insts, nop_inst_hex_32, num_nops_at_start, num_nops_at_end)
    # #print(prog_insts_to_mut, prog_insts_to_mut_indexes)

    # prog_insts_to_mut_mutated = mut_insts(prog_insts_to_mut, mutation_prob, mut_prob_type, inst_list_all_w_ext\
    #         , optimizer_sol, val_muts, opc_muts, nop_inst_bin_32)
    #print(prog_insts_to_mut_mutated)

    # # update prog insts with mutated insts
    # for inst_index, prog_inst_mutated in zip(prog_insts_to_mut_indexes, prog_insts_to_mut_mutated): 
    #     prog_insts[inst_index] = prog_inst_mutated
    # #print(prog_insts)
   
    # # update the lines to mut with the mutated insts
    # prog_lines_to_mut = update_lines_to_mut(prog_lines_to_mut\
    #                     , prog_insts_to_mut_indexes, prog_insts\
    #                     , hex_file_type, core)
    # for prog_line_index_to_mut, prog_line_to_mut in zip(prog_line_indexes_to_mut, prog_lines_to_mut): 
    #     prog_lines[prog_line_index_to_mut] = prog_line_to_mut
    #     #print(prog_lines[prog_line_index_to_mut])
    
    # # create the mutated prog file
    # with open(hex_file_out, 'w') as fp: 
    #     for line in prog_lines: 
    #         fp.write(line)


def mutate_prog_old(hex_file_in, hex_file_out, mutation_prob\
              , optimizer_sol, nop_inst_bin_32, inst_list_all_w_ext\
              , val_muts, opc_muts):

    lg.debug("generating", os.path.basename(hex_file_out), "from"\
            ,os.path.basename(hex_file_in))

    #write new instructions to instruction file 
    hex_file_in_f = open(hex_file_in, 'r')
    hex_file_out_f = open(hex_file_out, 'w')
    
    mut_state = 0
    line_number = 0
    inst_bin_i_prev = -1
    inst_list_fr_clone = []
    for line in hex_file_in_f.readlines():
	    #Parse input	
	    #these are in hex
        inst_addr_h = line[1:9]   #instruction address        
        inst_a_h    = line[10:18] #1st instruction
        inst_b_h    = line[19:27] #2nd instruction
        inst_c_h    = line[28:36] #3rd instruction
        inst_d_h    = line[37:45] #4th instruction

        if (inst_a_h == "00000013" and inst_b_h == "00000013" \
            and inst_c_h == "00000013" and inst_d_h == "00000013"): 
            #4 nops tells it that it should start/stop mutating
            if (mut_state == 0):
                    mut_state = 1
            elif (mut_state == 2):
                    mut_state = 3

            #write line to file
            hex_file_out_f.write(line)

        elif (mut_state == 1 or mut_state == 2): 
            mut_state = 2

            #only mutate line if it is not nop
            line.strip('\n') #removes '\n'
                          
            #convert instructions to binary and reverse them
            inst_bin = [0,0,0,0]
            inst_bin[0]    = inst_hex_to_bin(inst_a_h)
            inst_bin[1]    = inst_hex_to_bin(inst_b_h) 
            inst_bin[2]    = inst_hex_to_bin(inst_c_h) 
            inst_bin[3]    = inst_hex_to_bin(inst_d_h)  
            
            for inst_i in [0,1,2,3]:
                inst_bin_i = inst_bin[inst_i]
                inst_list_fr_clone.append(inst_bin_i)

                #calculate if this instrn should be mutated
                mutate_inst = (random.randint(0,100) < mutation_prob)
                #if nop or shouldnt mutate instrn, skip mutation
                if (inst_bin_i == nop_inst_bin_32) or not mutate_inst: 
                    inst_bin[inst_i] = inst_bin_i
                    continue

                ###reversing is done so that 0 index in python becomes bit 0
                inst_bin_i_orig = inst_bin_i
                inst_bin_i = inst_bin_i[::-1] #reverse

                # get the inst type
                got_inst = 0
                for inst_op, inst_data in inst_list_all_w_ext.items():
                    #print(bits(inst_bin_i_orig,6,0), inst_data[4])
                    if cmp_inst_fields(inst_bin_i_orig, inst_data):
                        i = inst_data + [inst_op[0]]
                        got_inst = 1
                        break
                if got_inst: # recognized the inst type
                    #mutations suggested by optimizer:
                    try:
                        opt_sol_mut_list = optimizer_sol[inst_op]
                    except: 
                        opt_sol_mut_list = val_muts
                    m_type_frm_opt = random.choice(opt_sol_mut_list)
                    #also use opcode changing mut techniques sometimes
                    m_type_opcode = random.choice(opc_muts)
                    #m_type = 11
                    m_type = random.choices([m_type_frm_opt, m_type_opcode]\
                                           , weights=[85,15], k=1)
                    m_type = m_type[0] # bcz rand choices returns list
                else: # inst type not recognized
                    i = [ "none" , "z" , "xxxxxxx", "xxx", "xxxxxxx"\
                            , "none", "1", 9999 ] + ["none"]
                    m_type = random.choice(val_muts+opc_muts)

                if   (m_type == 0): inst_bin_i = bitflip_1(inst_bin_i,i)    
                elif (m_type == 1): inst_bin_i = bitflip_2(inst_bin_i,i)
                elif (m_type == 2): inst_bin_i = bitflip_4(inst_bin_i,i)
                elif (m_type == 3): inst_bin_i = arith_8(inst_bin_i,i)
                elif (m_type == 4): inst_bin_i = arith_16(inst_bin_i,i) #j & r type
                elif (m_type == 5): inst_bin_i = random_8(inst_bin_i,i)
                elif (m_type == 6): inst_bin_i = byte_flip(inst_bin_i,i)
                elif (m_type == 7): inst_bin_i = byte_flip_16(inst_bin_i,i)                   
                elif (m_type == 8): inst_bin_i = random_8_any(inst_bin_i,i)
                elif (m_type == 9): inst_bin_i = delete(inst_bin_i,i\
                                                    , nop_inst_bin_32)
                elif (m_type == 10): inst_bin_i = clone(inst_bin_i,i\
                                         , random.choice(inst_list_fr_clone))
                elif (m_type == 11): inst_bin_i = opcode_mut(inst_bin_i, i) 

                else: print("Error: Incorrect Mutation")
                #reverse the bits back when storing back to correct 
                inst_bin[inst_i] = inst_bin_i[::-1]

            #convert instructions back to hex       
            inst_a    = inst_bin_to_hex(inst_bin[0]) 
            inst_b    = inst_bin_to_hex(inst_bin[1])
            inst_c    = inst_bin_to_hex(inst_bin[2])
            inst_d    = inst_bin_to_hex(inst_bin[3])

            #format line for instruction file       
            line = line[0] + inst_addr_h + " " + inst_a + " " + inst_b + " " + inst_c + " " + inst_d
            
            #print line to instruction file 
            #print(line, end='\n')
            hex_file_out_f.write(line + "\n")

        else: #line is not in the range
            hex_file_out_f.write(line)
        
        line_number = line_number + 1
    
    hex_file_in_f.close()
    hex_file_out_f.close()






    ##convert the hex file into mem file so that ariane core and emulator can use it to run simulations
    #hex_to_mem(hex_file_out, mem_file_out)
    #exit()

#    inst_addr_offset = 0 #reset the instruction address offset

    # End of simulations


if __name__ == '__main__': 
    import config
    from configManager import getCONFIG
    #from riscv_isa import inst_list_all_w_ext, nop_inst_bin_32
    from riscv_isa import nop_inst_bin_32
    import thehuzz_utils as TU
    
    prog_time = TU.Mytime()
