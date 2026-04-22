"""
This script is used to generate program files
- Notes: 

- TODOs: 
"""

import json, os, subprocess, re, json
import time, copy
from tqdm import tqdm
import logging as lg # critical, error, warning, info, debug
from multiprocessing import Process

testcase_template = {'id': None\
                    , 'hex_file': None, 'bin_file': None\
                    , 'riscv_file': None, 'times_mutated': 0}

"""
Deletes the target file
"""
def delete_file(target_file, force_delete=False, action='delete'):
    if not os.path.exists(target_file): # just return if file doesnt exist
        return 'deleted'
    if action == 'delete': 
        if force_delete:
            confirm = 'y'
        else: 
            confirm = input("Are you sure you want to delete "+ target_file + "? (y,n,a) : ")

        if (confirm == 'y'):
            subprocess.call("rm -rf " + target_file,shell=True)
            return 'deleted'
        elif (confirm == 'a'): # abort
            exit()
        else: 
            return 'not_deleted'
    else: 
        print("ERROR: Unknown action:", action)
        exit()
    

"""
Deletes the target dir
- Actions: 
    - delete: deletes the target dir
    - move: moves the target dir to a trash dir
"""
def delete_dir(target_dir, force_delete=False, action='delete', trash_dir='/tmp/'):
    if not os.path.isdir(target_dir): # just create if dir doesnt exist
        subprocess.call("mkdir -p "  + target_dir,shell=True)
        return 'deleted'
    if action in ['delete', 'move']: 
        if len(os.listdir(target_dir)) > 0:
            if force_delete:
                confirm = 'y'
            else: 
                confirm = input("Are you sure you want to delete "+ target_dir + "? (y,n,a) : ")

            if (confirm == 'y'):
                if action == 'delete': 
                    subprocess.call("rm -rf " + target_dir,shell=True)
                else: 
                    subprocess.call([ 'mv', target_dir, trash_dir ])
                subprocess.call("mkdir -p "  + target_dir,shell=True)
                return action
            elif (confirm == 'a'): # abort
                exit()
            else: 
                return 'not_deleted'
        else: 
            subprocess.call("rm -rf " + target_dir,shell=True)
            subprocess.call("mkdir -p "  + target_dir,shell=True)
            return 'deleted'
    else: 
        print("ERROR: Unknown action:", action)
        exit()

"""
Gets a sorted filelist of all the files with a given pattern in a dir
"""
def get_files_in_dir(target_dir, pattern="", sort_file=True):
    # get a list of all the files
    all_filelist = os.listdir(target_dir)

    # filter out files based on the pattern
    filelist = []
    for filename in all_filelist:
        if re.match(pattern, filename):
            filelist.append(filename)

    # sort the files
    if sort_file == True:
        filelist.sort(key=lambda f: int(''.join(filter(str.isdigit, f))))

    # add full path to the names
    filelist_fullpath = [os.path.join(target_dir, filename) for filename in filelist]

    return filelist_fullpath

"""
"""
def update_json_file(json_file, input_data): 

    data_changed = False

    if os.path.exists(json_file):
        with open(json_file, 'r') as fp: data = json.load(fp)

        for key, value in input_data.items(): # update with new data
            if key in data.keys():
                if data[key] != value:
                    data[key] = value
                    data_changed = True
            else: 
                data[key] = value
                data_changed = True
    else:
        data = input_data
        data_changed = True
    
    if data_changed: # update json file only if it is changed to save time
        with open(json_file, 'w') as fp: 
            json.dump(data, fp, indent=2)


"""
"""
def change_extension(filepath, new_extension): 
    basepath = os.path.splitext(filepath)[0]
    return f"{basepath}.{new_extension}"


"""
"""
def log(logfile, data, time=None, overwrite=False): 

    mode = 'w' if overwrite else 'a'
    # get time string, dont update time difference
    time_string = f"[{time.get_time(False)} sec] " if time else ""
   
    with open(logfile, mode) as fp: fp.write(f"{time_string}{data}")


"""
"""
def TIMELOG(time, string, done=False, terminal=False, log_file=True):
   
    time_diff = time.time_diff()
    done_string = f"done in {time_diff} sec" if done else ""

    if terminal: 
        print(f"[{time.get_time()} sec]{string} {done_string}")

    if log_file: 
        lg.info(f"[{time.get_time()} sec]{string} {done_string}")
    
    return time_diff


"""
"""
class Mytime: 
    def __init__(self, init_time=None): 
        self.start_time = init_time if init_time else time.time()
        self.latest_queried_time = self.start_time

    # return the time from creating this object
    def get_time(self, update=True): 
        if update: # update latest queried time 
            self.latest_queried_time = time.time()
        return round(time.time()-self.start_time, 2)

    # return the time diff from last query
    def time_diff(self, update=True): 
        self.latest_queried_time_prev = self.latest_queried_time
        if update: # update latest queried time 
            self.latest_queried_time = time.time()
        return round(time.time()-self.latest_queried_time_prev, 2)

    # reset start time
    def reset_start_time(self): 
        self.__init__()


"""
"""
class DATABASE: 
    def __init__(self, core, testcase_dir, hex_file_t\
               , bin_file_t, riscv_file_t, run_mode):
        self.core = core
        self.run_mode = run_mode
        self.testcase_dir = testcase_dir
        self.new_testcases = []
        self.simulated_testcases = []
        self.testcases_to_sim = []
        self.hex_file_t = hex_file_t
        self.bin_file_t = bin_file_t
        self.riscv_file_t = riscv_file_t

    # add hex files to database
    def add_testcases(self, filelist, save_filetypes=[]):
        for file_i in filelist:
            # add the testcase to all testcases
            testcase = copy.deepcopy(testcase_template)
            testcase['id'] = self.num_testcases()

            testcase_filename_hex = self.hex_file_t.substitute(fno=testcase['id'])
            testcase['hex_file'] = os.path.join(self.testcase_dir, testcase_filename_hex)
            testcase_filename_bin = self.bin_file_t.substitute(fno=testcase['id'])
            testcase['bin_file'] = os.path.join(self.testcase_dir, testcase_filename_bin)
            testcase_filename_riscv = self.riscv_file_t.substitute(fno=testcase['id'])
            testcase['riscv_file'] = os.path.join(self.testcase_dir, testcase_filename_riscv)
            testcase['times_mutated'] = 0

            self.new_testcases.append(testcase)

            # put the testcase in the database dir
            subprocess.call([ 'mv', file_i, testcase['hex_file'] ])
            for save_file_i in save_filetypes:
                subprocess.call([ 'mv', change_extension(file_i, save_file_i), change_extension(testcase['hex_file'], save_file_i) ])
    
    def get_testcases_to_sim(self, no_testcases): 
        assert self.num_new_testcases() >= no_testcases, f"dont have enough testcases, {self.num_new_testcases()}, {no_testcases}"
        self.testcases_to_sim = self.new_testcases[:no_testcases]
        self.new_testcases = self.new_testcases[no_testcases:]
        self.simulated_testcases += self.testcases_to_sim

        return self.testcases_to_sim 


    def allocate_testcases_to_mut(self, testcases_to_mut): 
        for testcase in testcases_to_mut: 
            testcase['new_hex_files'] = []
            testcase['new_bin_files'] = []
            testcase['new_riscv_files'] = []
            for i in range(testcase['mut_times']): 
                new_testcase = copy.deepcopy(testcase_template)
                new_testcase['id'] = self.num_testcases()
                new_testcase_filename_hex = self.hex_file_t.substitute(fno=new_testcase['id'])
                new_testcase['hex_file'] = os.path.join(self.testcase_dir, new_testcase_filename_hex)
                new_testcase_filename_bin = self.bin_file_t.substitute(fno=new_testcase['id'])
                new_testcase['bin_file'] = os.path.join(self.testcase_dir, new_testcase_filename_bin)
                new_testcase_filename_riscv = self.riscv_file_t.substitute(fno=new_testcase['id'])
                new_testcase['riscv_file'] = os.path.join(self.testcase_dir, new_testcase_filename_riscv)
                new_testcase['times_mutated'] = testcase['times_mutated'] + 1

                self.new_testcases.append(new_testcase)
                testcase['new_hex_files'].append(new_testcase['hex_file'])
                testcase['new_bin_files'].append(new_testcase['bin_file'])
                testcase['new_riscv_files'].append(new_testcase['riscv_file'])

        return testcases_to_mut

    def sim_done(self): 
        t= 1

    def num_testcases(self): 
        return len(self.new_testcases) + len(self.simulated_testcases)

    def num_new_testcases(self): 
        return len(self.new_testcases)

    def num_testcases_simulated(self): 
        return len(self.simulated_testcases)

def hex_to_riscv(in_hex_file, out_riscv_file, bit_width=128):
    """
    Converts a hex file with address markers and hex values back to binary.
    Parameters:
    - input_file (str): Path to the input hex file.
    - output_file (str): Path to the output binary file.
    - bit_width (int): Bit width of each hex data chunk (default is 128).
    """
    with open(in_hex_file, 'r') as hex_file, open(out_riscv_file, 'wb') as bin_file:
        for line in hex_file:
            hex_values = line.strip().split()[1:]
            for hex_value in hex_values:
                bin_data = int(hex_value, 16).to_bytes(bit_width // 32, byteorder='little')
                bin_file.write(bin_data)


def hex_to_bin(input_file, output_file, bit_width=128): # only for xiangshan
    """
    Converts a hex file with address markers and hex values back to binary.
    Parameters:
    - input_file (str): Path to the input hex file.
    - output_file (str): Path to the output binary file.
    - bit_width (int): Bit width of each hex data chunk (default is 128).
    """
    with open(input_file, 'r') as hex_file, open(output_file, 'wb') as bin_file:
        for line in hex_file:
            # Remove the address prefix and split hex values by spaces
            hex_values = line.strip().split()[1:]
            # Convert each hex value to binary and write it to the binary file
            for hex_value in hex_values:
                # Convert hex to binary, considering the bit-width (128-bit = 16 bytes)
                bin_data = int(hex_value, 16).to_bytes(bit_width // 32, byteorder='little')
                bin_file.write(bin_data)


#converts the hex files into mem format readble by the ariane and emulator
def hex_to_mem(hex_file, mem_file):

    #Copy hex file to be modified (original file will be unchanged)
    #seed_cpy = "cp -f " + hex_file + " " + mem_file
    #subprocess.call(seed_cpy,shell=True) #runs command
    #out_file = fileinput.input(files=mem_file, inplace=1, backup='.back')
    inf = open(hex_file, 'r')
    in_file = inf.readlines()
    out_file = open(mem_file, 'w')
    
    for line in in_file:
        #reformats important info so that the fuzzer can parse it
        line = line.lower()
        hex_addr = line[1:9]
        inst1 = line[10:18]#[::-1]
        inst1 = inst1[6:8] + inst1[4:6] + inst1[2:4] + inst1[0:2] #flip bits b/c of endiniess
        inst2 = line[19:27]#[::-1]
        inst2 = inst2[6:8] + inst2[4:6] + inst2[2:4] + inst2[0:2]
        inst3 = line[28:36]#[::-1]
        inst3 = inst3[6:8] + inst3[4:6] + inst3[2:4] + inst3[0:2]
        inst4 = line[37:45]#[::-1]
        inst4 = inst4[6:8] + inst4[4:6] + inst4[2:4] + inst4[0:2]
        inst_total = inst1+inst2+inst3+inst4
        i=0
        while i < 31:
            out_file.write(inst_total[i:i+2] + "\n")
            i=i+2	
    
    inf.close()	
    out_file.close()


"""
It creates copies of the simulation repos depending on number of threads
"""
def setup_simulation_repos(sim_dir_t, no_threads):
    sim_dirs = [sim_dir_t.substitute(tno=i) for i in range(no_threads)]
    assert os.path.isdir(sim_dir_t.substitute(tno=0)), f"no simulation repos found: {sim_dir_t.template}"
    repos_to_create = [repo for repo in sim_dirs if not os.path.isdir(repo)]

    # start processes
    procs = []
    def f(fr, to): subprocess.call([ 'cp', '-r', fr, to ])
    for repo in repos_to_create: 
        proc = Process(target=f, args=(sim_dir_t.substitute(tno=0), repo))
        procs.append(proc); proc.start()
    
    # wait
    for proc in procs: proc.join()


def main():
    temp = 1 # do nothing


if __name__ == '__main__':
    main()
        
        
