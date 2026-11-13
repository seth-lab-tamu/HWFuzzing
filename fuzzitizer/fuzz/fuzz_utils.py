"""Shared runtime utilities for FUZZItizer."""

import os, re, shutil, subprocess
import time, copy
import logging as lg # critical, error, warning, info, debug
from multiprocessing import Process

testcase_template = {'id': None\
                    , 'hex_file': None, 'times_mutated': 0}

"""
Deletes the target dir
- Actions: 
    - delete: deletes the target dir
    - move: moves the target dir to a trash dir
"""
def delete_dir(target_dir, force_delete=False, action='delete', trash_dir='/tmp/'):
    target_dir = os.fspath(target_dir)
    trash_dir = os.fspath(trash_dir)

    if not os.path.isdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        return 'deleted'

    if action not in ['delete', 'move']:
        print("ERROR: Unknown action:", action)
        exit()

    if len(os.listdir(target_dir)) == 0:
        shutil.rmtree(target_dir)
        os.makedirs(target_dir)
        return 'deleted'

    confirm = 'y' if force_delete else input(
        f"Are you sure you want to delete {target_dir}? (y,n,a) : ")
    if confirm == 'a':
        exit()
    if confirm != 'y':
        return 'not_deleted'

    if action == 'delete':
        shutil.rmtree(target_dir)
    else:
        shutil.move(target_dir, trash_dir)
    os.makedirs(target_dir)
    return action

"""
Gets a sorted filelist of all the files with a given pattern in a dir
"""
def get_files_in_dir(target_dir, pattern=""):
    # get a list of all the files
    all_filelist = os.listdir(target_dir)

    # filter out files based on the pattern
    filelist = []
    for filename in all_filelist:
        if re.match(pattern, filename):
            filelist.append(filename)

    # Preserve numeric ordering for generated inputs, while also accepting
    # peripheral names such as opn_dma.csv that contain no digits.
    numbered_files = []
    unnumbered_files = []
    for file_path in filelist:
        digits = re.sub('[^0-9]', '', file_path)
        if digits:
            numbered_files.append((int(digits), file_path))
        else:
            unnumbered_files.append(file_path)

    numbered_files.sort(key=lambda item: item[0])
    unnumbered_files.sort()
    filelist = [file_path for _, file_path in numbered_files] + unnumbered_files

    # add full path to the names
    filelist_fullpath = [os.path.join(target_dir, filename) for filename in filelist]

    return filelist_fullpath


def change_extension(filepath, new_extension): 
    basepath = os.path.splitext(filepath)[0]
    return f"{basepath}.{new_extension}"


def log(logfile, data, time=None, overwrite=False): 

    mode = 'w' if overwrite else 'a'
    # get time string, dont update time difference
    time_string = f"[{time.get_time(False)} sec] " if time else ""
   
    with open(logfile, mode) as fp: fp.write(f"{time_string}{data}")


def TIMELOG(time, string, done=False, terminal=False, log_file=True):
   
    time_diff = time.time_diff()
    done_string = f"done in {time_diff} sec" if done else ""

    if terminal: 
        print(f"[{time.get_time()} sec]{string} {done_string}")

    if log_file: 
        lg.info(f"[{time.get_time()} sec]{string} {done_string}")
    
    return time_diff


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


class DATABASE: 
    def __init__(self, testcase_dir, hex_file_t):
        self.testcase_dir = testcase_dir
        self.new_testcases = []
        self.simulated_testcases = []
        self.testcases_to_sim = []
        self.hex_file_t = hex_file_t

    def add_testcases(self, filelist, save_filetypes=[]):
        for file_i in filelist:
            testcase = copy.deepcopy(testcase_template)
            testcase['id'] = self.num_testcases()

            testcase_filename = self.hex_file_t.substitute(fno=testcase['id'])
            testcase['hex_file'] = os.path.join(self.testcase_dir, testcase_filename)
            testcase['times_mutated'] = 0

            self.new_testcases.append(testcase)

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
            for i in range(testcase['mut_times']): 
                new_testcase = copy.deepcopy(testcase_template)
                new_testcase['id'] = self.num_testcases()
                new_testcase_filename = self.hex_file_t.substitute(fno=new_testcase['id'])
                new_testcase['hex_file'] = os.path.join(self.testcase_dir, new_testcase_filename)
                new_testcase['times_mutated'] = testcase['times_mutated'] + 1

                self.new_testcases.append(new_testcase)
                testcase['new_hex_files'].append(new_testcase['hex_file'])

        return testcases_to_mut

    def num_testcases(self): 
        return len(self.new_testcases) + len(self.simulated_testcases)

    def num_new_testcases(self): 
        return len(self.new_testcases)

    def num_testcases_simulated(self): 
        return len(self.simulated_testcases)



def hex_to_mem(hex_file, mem_file):
    inf = open(hex_file, 'r')
    in_file = inf.readlines()
    out_file = open(mem_file, 'w')
    
    for line in in_file:
        line = line.lower()
        hex_addr = line[1:9]
        inst1 = line[10:18]
        inst1 = inst1[6:8] + inst1[4:6] + inst1[2:4] + inst1[0:2]
        inst2 = line[19:27]
        inst2 = inst2[6:8] + inst2[4:6] + inst2[2:4] + inst2[0:2]
        inst3 = line[28:36]
        inst3 = inst3[6:8] + inst3[4:6] + inst3[2:4] + inst3[0:2]
        inst4 = line[37:45]
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
    primary = sim_dir_t.substitute(tno=0)
    assert os.path.isdir(primary), f"no simulation repos found: {sim_dir_t.template}"
    worker_dirs = [sim_dir_t.substitute(tno=i) for i in range(1, no_threads)]
    for repo in worker_dirs:
        if os.path.isdir(repo):
            shutil.rmtree(repo)

    procs = []
    for repo in worker_dirs:
        proc = Process(target=shutil.copytree, args=(primary, repo))
        procs.append(proc); proc.start()
    
    for proc in procs:
        proc.join()
        if proc.exitcode:
            raise RuntimeError("could not refresh a simulation worker repository")
