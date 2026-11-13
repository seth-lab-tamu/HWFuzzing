
import subprocess, os, re, sys
import multiprocessing as mp, time, pickle, random
import logging as lg
from tqdm import tqdm

import parse_cov

LOCKS = None
WRITE_LOG_LOCK = None
ARGS_FOR_SIMULATION = None


def sim_progs(progs_to_sim, no_threads, prog_save_no, *args_for_simulation):

    locks = [mp.Lock() for i in range(no_threads)]

    write_log_lock = mp.Lock()

    chunk_size = int((len(progs_to_sim)/no_threads)/4)
    chunk_size = max(1, chunk_size)

    args = []
    for i, mem_file_in in enumerate(progs_to_sim): 
        args.append( [mem_file_in, prog_save_no[i]] )
    
    init_args = (locks, write_log_lock, args_for_simulation)
    
    with mp.Pool(processes=no_threads, initializer=init_sim_prog, initargs=init_args) as pool: 
        if len(args) > 100:
            cov_data = list(tqdm(pool.imap(sim_prog, args, chunksize=chunk_size), total=len(args), desc="----Simulating files"))
        else: 
            cov_data = list(pool.imap(sim_prog, args, chunksize=chunk_size))

    cov_data_dict = {prog_save_no_i: cov_data_i for prog_save_no_i, cov_data_i in zip(prog_save_no, cov_data)}

    return cov_data_dict


def acquire_sim_dir(locks): 
    while True:
        for i, lock in enumerate(locks): 
            if lock.acquire(block=False): 
                return i


def worker_log(print_func, print_message, lock): 
    lock.acquire()
    print_func(print_message)
    lock.release()


def init_sim_prog(locks_in, write_log_lock_in, args_for_simulation):
    global LOCKS, WRITE_LOG_LOCK, ARGS_FOR_SIMULATION
    LOCKS = locks_in
    WRITE_LOG_LOCK = write_log_lock_in
    ARGS_FOR_SIMULATION = args_for_simulation


def sim_prog( arg_list ): 
        
    ip_file, file_no = arg_list
    random_seed = str(random.randrange(sys.maxsize))
    
    core, tot_sim_time, cov_enable\
    , cov_types, vdb_cov_files, core_instance_list\
    , sim_bash_file, CORE_PT, start_time, sim_files_to_save\
    , return_cov = ARGS_FOR_SIMULATION

    thread_no = acquire_sim_dir(LOCKS)

    try:
        filename = os.path.basename(ip_file)


        cov_cmd = "cov=1" if cov_enable else ""
        cmd_chk_rtl = subprocess.call([ sim_bash_file\
                  , CORE_PT['sim_dir_t'].substitute(tno=thread_no)\
                  , CORE_PT['core_dram_path'], ip_file\
                  , CORE_PT['sim_out_path_t'].substitute(tno=thread_no), str(tot_sim_time)\
                  , sim_files_to_save['trace']['to'].substitute(fno=str(file_no)), random_seed\
                  , core ])
        if cmd_chk_rtl != 0:
            raise RuntimeError(
                f"simulator exited with status {cmd_chk_rtl} for input {ip_file}")


        cov_dict = {}
        if return_cov or sim_files_to_save['cov']['en']:
            rtl_cov_out_path = CORE_PT['cov_out_path_t'].substitute(tno=thread_no)
            cov_dict = parse_cov.vdb_to_dict(rtl_cov_out_path, cov_types, vdb_cov_files\
                            , core_instance_list, CORE_PT['vdb_test_dir'], 'detailed'\
                            , f"simulation for {ip_file} probably dint run properly, {file_no}, {thread_no}")

        for save_file, data in sim_files_to_save.items():
            if data["en"]:
                from_file = data["from"].substitute(tno=thread_no)
                if not os.path.exists(from_file):
                    raise FileNotFoundError(f"there is no file to copy {from_file}")
                if save_file == 'cov':
                    with open(data["to"].substitute(fno=str(file_no)), 'wb') as fp:
                        pickle.dump(cov_dict, fp)
                else:
                    move_status = subprocess.call([
                        'mv', from_file, data["to"].substitute(fno=str(file_no))
                    ])
                    if move_status != 0:
                        raise RuntimeError(
                            f"could not store {save_file} for input {ip_file}"
                        )

        if return_cov:
            return cov_dict
        else:
            return {k:'' for k in cov_dict.keys()}
    finally:
        LOCKS[thread_no].release()
