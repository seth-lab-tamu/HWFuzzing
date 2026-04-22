"""
Created by: Rahul Kande
This script has functions to run simulations
- Notes: 

- TODOs: 
    - have diff sim_progs logic for when no progs < no threads
        - no need to lock if no progs not more than no dirs
"""

import subprocess, os, re, sys
import multiprocessing as mp, time, pickle, random
import logging as lg # critical, error, warning, info, debug
from tqdm import tqdm

import thehuzz_utils, parse_cov

# this command is try to bypss the permission error issues 
# when using SemLock to access /dev/shm on Olympus
try:
    mp.set_start_method('fork')
except RuntimeError:
    pass  # start method has already been set


#----------------------------------------#
#----------------functions---------------#
#----------------------------------------#

"""
This function simulates all the programs from the progs_to_sim array
- ISAs supported: riscv
- It uses the number of threads provided as input to run parallel simulations
- Provide mem filelist as progs_to_sim array
- Note make sure there are no_threads no of dirs since no_threads no of
  simulations will be run on dirs 0 to no_threads-1
"""
def sim_progs(progs_to_sim, no_threads, prog_save_no, *args_for_simulation):

    # create locks for each simulation dir so that two simulations wont run in
    # same dir
    locks = [mp.Lock() for i in range(no_threads)]

    write_log_lock = mp.Lock() # lock for workers to print to log file

    # manager = mp.Manager()
    # locks = [manager.Lock() for _ in range(no_threads)]
    # write_log_lock = manager.Lock() # lock for workers to print to log file

    # compute the suitable chunksize
    chunk_size = int((len(progs_to_sim)/no_threads)/4) # so if there are 1000 progs & 10 processes, chunk is 25
    chunk_size = max(1, chunk_size) # if we have less no of progs, then just do one at a time

    # create the arguments for the simulation processes
    args = []
    for i, mem_file_in in enumerate(progs_to_sim): 
        args.append( [mem_file_in, prog_save_no[i], str(random.randrange(sys.maxsize)), *args_for_simulation] )
    
    # invoke all the simulations using multiprocess
    init_args = (locks, write_log_lock)
    with mp.Pool(processes=no_threads, initializer=init_sim_prog, initargs=init_args) as pool: 
        if len(args) > 100: # use tqdm if simulating many files
            cov_data = list(tqdm(pool.imap(sim_prog, args, chunksize=chunk_size), total=len(args), desc="----Simulating files"))
        else: 
            cov_data = list(pool.imap(sim_prog, args, chunksize=chunk_size))

    # convert cov_data to dict
    cov_data_dict = {prog_save_no_i: cov_data_i for prog_save_no_i, cov_data_i in zip(prog_save_no, cov_data)}

    return cov_data_dict

# def sim_progs(progs_to_sim, no_threads, prog_save_no, *args_for_simulation):
#     # No need for locks or multiprocessing

#     # Create the arguments for each simulation
#     args = []
#     for i, mem_file_in in enumerate(progs_to_sim):
#         args.append([mem_file_in, prog_save_no[i], str(random.randrange(sys.maxsize))\
#                    , *args_for_simulation, i % no_threads])

#     # Run simulations serially with progress bar
#     cov_data = []
#     for arg in tqdm(args, desc="----Simulating files"):
#         cov_data.append(sim_prog(arg))

#     # Convert cov_data to dict
#     cov_data_dict = {prog_save_no_i: cov_data_i for prog_save_no_i, cov_data_i in zip(prog_save_no, cov_data)}

#     return cov_data_dict


"""
Gets a simulation directory to for the worker thread to run the simulation
- This is needed since we dont want two simulations from two different processes 
  to run on the same sim directory 
"""
def acquire_sim_dir(locks): 
    while True:
        for i, lock in enumerate(locks): 
            if lock.acquire(block=False): 
                return i


"""
Gets lock for writing to log file, writes the message and releases the lock
- This is needed since all the worker functions write logs to same file
"""
def worker_log(print_func, print_message, lock): 
    lock.acquire()
    print_func(print_message)
    lock.release()


"""
This is the initialization method for all the worker processes used to pass shared data like locks
"""
def init_sim_prog(locks_in, write_log_lock_in):
    global locks, write_log_lock
    locks = locks_in
    write_log_lock = write_log_lock_in



import subprocess
import time

def run_spike_and_kill(riscv_filepath, trace_filepath):
    print(f"running {riscv_filepath}")
    proc = None
    try:
        # Start the process
        proc = subprocess.Popen(
            [
                '/mnt/shared-scratch/Rajendran_J/jkohhokj/benchmarks/riscv-isa-sim/install/bin/spike', 
                '-l',
                '-d',
                '--debug-cmd=/mnt/shared-scratch/Rajendran_J/jkohhokj/CBFuzz/chipyard_1130/trace_eg/rsd_debugger_script.txt',
                riscv_filepath
            ],
            stdout=open(trace_filepath, 'w'),
            stderr=subprocess.STDOUT
        )

        # Optionally wait or check periodically
        time.sleep(10)  # Give it time to run, adjust as needed

        # Kill the process after timeout or your own condition
        proc.kill()
        print("Spike process killed.")
        
    except Exception as e:
        print(f"Error running Spike: {e}")
    finally:
        # Ensure cleanup
        if proc and proc.poll() is None:
            proc.kill()
            print("Spike forcibly terminated in cleanup.")



"""
This is a worker function to simulate one prog file
- Input is mem file
- Note: Arguments for init_sim_prog func also become available to this func
    - 
- TODO: release sim dir lock as soon as possible so that other simulations can
  start
"""
def sim_prog( arg_list ): 
        
    ip_file, file_no, random_seed, core, tot_sim_time, cov_enable\
    , cov_types, vdb_cov_files, core_instance_list\
    , sim_bash_file, CORE_PT, start_time, sim_files_to_save\
    , detecting_bugs, emu_bash_file, EMU_PT, emu_tot_sim_time, return_cov = arg_list
    
    # acquire a sim dir to run the simulation
    thread_no = acquire_sim_dir(locks)

    filename = os.path.basename(ip_file)
    #worker_log(lg.info, f"Running file: {filename}, {file_no} on thread {thread_no}", write_log_lock)

    ## delete previous trace to make sure we dont use previous simulation data
    #trace_out_path = CORE_PT['trace_out_path_t'].substitute(tno=thread_no)
    #thehuzz_utils.delete_file(trace_out_path, force_delete=True)

    if os.path.splitext(ip_file)[1][1:] != CORE_PT['input_format']:  # [1:] removes dot that splittext includes
        if CORE_PT['input_format'] == 'mem': 
            new_ip_file = thehuzz_utils.change_extension(ip_file, CORE_PT['input_format'])
            thehuzz_utils.hex_to_mem(ip_file, new_ip_file)
            ip_file = new_ip_file
        else: 
            assert False, f"Missing core conversion specification for {core} core"

    #run simulation command
    cov_cmd = "cov=1" if cov_enable else ""
    cmd_chk_rtl = subprocess.call([ sim_bash_file\
            , CORE_PT['sim_dir_t'].substitute(tno=thread_no)\
            , CORE_PT['core_dram_path'], ip_file\
            , CORE_PT['sim_out_path_t'].substitute(tno=thread_no), str(tot_sim_time)\
            , sim_files_to_save['trace']['from'].substitute(tno=thread_no)\
            , random_seed])

    if core == "xiangshan": # xs has internal bug detection
        cov_dict = {}
        for cov_type in cov_types:
            cov_dict[cov_type] = ''
        return cov_dict
        #return {k:'' for k in cov_dict.keys()}

    #print( emu_bash_file, EMU_PT['sim_dir_t'].substitute(), ip_file, EMU_PT['sim_out_path_t'].substitute(tno=thread_no), sim_files_to_save['emu_trace']['to'].substitute(fno=str(file_no)))
    # run the emulation command if bug detection is enabled
    if detecting_bugs: 
        cmd_chk_emu = subprocess.call([ emu_bash_file\
                  , EMU_PT['sim_dir_t'].substitute()\
                  , 'None', ip_file\
                  , EMU_PT['sim_out_path_t'].substitute(tno=thread_no), str(1)\
                  , sim_files_to_save['emu_trace']['to'].substitute(fno=str(file_no)) ])
    #worker_log(lg.info, f"[{file_no}] Run time: {time.time() - start_time} | on {thread_no}", write_log_lock)

    # extract coverage data
    rtl_cov_out_path = CORE_PT['cov_out_path_t'].substitute(tno=thread_no)
    cov_dict = parse_cov.vdb_to_dict(rtl_cov_out_path, cov_types, vdb_cov_files\
                    , core_instance_list, CORE_PT['vdb_test_dir'], 'detailed'\
                    , f"simulation for {ip_file} probably dint run properly, {file_no}, {thread_no}")

    # store the simulation files
    for save_file, data in sim_files_to_save.items(): 
        if data["en"]:
            from_file = data["from"].substitute(tno=thread_no)
            assert os.path.exists(from_file), f"there is no file to copy {from_file}"
            if save_file == 'cov': # save the cov dict instead of the original cov file
                with open(data["to"].substitute(fno=str(file_no)), 'wb') as fp:
                    pickle.dump(cov_dict, fp)
            else: 
                subprocess.call([ 'mv', from_file, data["to"].substitute(fno=str(file_no)) ])

    # release sim dir lock
    locks[thread_no].release()

    # return coverage data
    if return_cov: # return entire cov data
        return cov_dict
    else: # just return dummy data
        return {k:'' for k in cov_dict.keys()}