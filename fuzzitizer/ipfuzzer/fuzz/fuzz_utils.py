
import copy
import logging as lg
import os
import re
import shutil
import time

testcase_template = {'id': None\
                    , 'ip_file': None, 'times_mutated': 0}


def isProjectSource(sourcePath, relativeBase, allowedRoots):
    sourcePath = os.fspath(sourcePath)
    if not sourcePath or os.path.basename(sourcePath) in {'mhdlinst.dat', '.mhdlinst.dat'}:
        return False

    if os.path.isabs(sourcePath):
        resolvedPath = os.path.realpath(sourcePath)
    else:
        resolvedPath = os.path.realpath(os.path.join(os.fspath(relativeBase), sourcePath))

    for allowedRoot in allowedRoots:
        allowedRoot = os.path.realpath(os.fspath(allowedRoot))
        try:
            if os.path.commonpath([resolvedPath, allowedRoot]) == allowedRoot:
                return True
        except ValueError:
            continue
    return False


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

def get_files_in_dir(target_dir, pattern=""):
    all_filelist = os.listdir(target_dir)

    filelist = []
    for filename in all_filelist:
        if re.match(pattern, filename):
            filelist.append(filename)

    filelist.sort(key=lambda f: int(''.join(filter(str.isdigit, f))))

    filelist_fullpath = [os.path.join(target_dir, filename) for filename in filelist]

    return filelist_fullpath

def log(logfile, data, time=None, overwrite=False): 

    mode = 'w' if overwrite else 'a'
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

    def get_time(self, update=True): 
        if update:
            self.latest_queried_time = time.time()
        return round(time.time()-self.start_time, 2)

    def time_diff(self, update=True): 
        self.latest_queried_time_prev = self.latest_queried_time
        if update:
            self.latest_queried_time = time.time()
        return round(time.time()-self.latest_queried_time_prev, 2)

    def reset_start_time(self): 
        self.__init__()


class DATABASE: 
    def __init__(self, testcase_dir, fuzzer_input_file_t):
        self.testcase_dir = testcase_dir
        self.new_testcases = []
        self.simulated_testcases = []
        self.testcases_to_sim = []
        self.fuzzer_input_file_t = fuzzer_input_file_t 
        self.testcase_id_to_path = {}

    def add_testcases(self, filelist):
        for file_i in filelist:
            testcase = copy.deepcopy(testcase_template)
            testcase['id'] = self.num_testcases()

            testcase_filename = self.fuzzer_input_file_t.substitute(fno=testcase['id'])
            testcase['ip_file'] = os.path.join(self.testcase_dir, testcase_filename)
            testcase['times_mutated'] = 0

            self.new_testcases.append(testcase)
            self.testcase_id_to_path[testcase['id']] = testcase['ip_file']

            shutil.move(file_i, testcase['ip_file'])

    def get_testcases_to_sim(self, no_testcases): 
        assert self.num_new_testcases() >= no_testcases, f"dont have enough testcases, {self.num_new_testcases()}, {no_testcases}"
        self.testcases_to_sim = self.new_testcases[:no_testcases]
        self.new_testcases = self.new_testcases[no_testcases:]
        self.simulated_testcases += self.testcases_to_sim

        return self.testcases_to_sim 


    def allocate_testcases_to_mut(self, testcases_to_mut): 
        for testcase in testcases_to_mut: 
            testcase['new_ip_files'] = []
            for i in range(testcase['mut_times']): 
                new_testcase = copy.deepcopy(testcase_template)
                new_testcase['id'] = self.num_testcases()
                new_testcase_filename = self.fuzzer_input_file_t.substitute(fno=new_testcase['id'])
                new_testcase['ip_file'] = os.path.join(self.testcase_dir, new_testcase_filename)
                new_testcase['times_mutated'] = testcase['times_mutated'] + 1

                self.new_testcases.append(new_testcase)
                testcase['new_ip_files'].append(new_testcase['ip_file'])
                self.testcase_id_to_path[new_testcase['id']] = new_testcase['ip_file']

        return testcases_to_mut

    def num_testcases(self): 
        return len(self.new_testcases) + len(self.simulated_testcases)

    def num_new_testcases(self): 
        return len(self.new_testcases)

    def num_testcases_simulated(self): 
        return len(self.simulated_testcases)


    def get_testcase_path(self, testcase_id): 
        return self.testcase_id_to_path[testcase_id]

