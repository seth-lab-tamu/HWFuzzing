

import subprocess, os, shutil, sys
import multiprocessing as mp, pickle, random
from tqdm import tqdm

import parse_cov














def sim_progs(progs_to_sim, no_threads, prog_save_no, *args_for_simulation):



    locks = [mp.Lock() for i in range(no_threads)]


    chunk_size = int((len(progs_to_sim)/no_threads)/4)
    chunk_size = max(1, chunk_size)


    args = []
    for i, input_file in enumerate(progs_to_sim):
        args.append( [input_file, prog_save_no[i], str(random.randrange(sys.maxsize)), *args_for_simulation] )
    

    init_args = (locks,)
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





def init_sim_prog(locks_in):
    global locks
    locks = locks_in









def sim_prog( arg_list ): 
        
    ip_file, file_no, random_seed, core, tot_sim_time, cov_enable\
    , cov_types, vdb_cov_files, core_instance_list\
    , sim_bash_file, CORE_PT, sim_files_to_save\
    , return_cov = arg_list
    

    thread_no = acquire_sim_dir(locks)
    try:


        output_templates = (
            CORE_PT.get('sim_out_path_t'),
            CORE_PT.get('trace_out_path_t'),
        )
        for output_template in output_templates:
            if output_template is None:
                continue
            stale_output = output_template.substitute(tno=thread_no)
            if os.path.isdir(stale_output):
                shutil.rmtree(stale_output)
            elif os.path.exists(stale_output):
                os.remove(stale_output)



        coverage_template = CORE_PT.get('cov_out_path_t')
        if coverage_template is not None:
            coverage_database = coverage_template.substitute(tno=thread_no)
            stale_coverage = os.path.join(
                coverage_database, CORE_PT['vdb_test_dir']
            )
            if os.path.isdir(stale_coverage):
                shutil.rmtree(stale_coverage)
            elif os.path.exists(stale_coverage):
                os.remove(stale_coverage)

        simulation_command = [
            sim_bash_file,
            CORE_PT['sim_dir_t'].substitute(tno=thread_no),
            CORE_PT['core_dram_path'],
            ip_file,
            CORE_PT['sim_out_path_t'].substitute(tno=thread_no),
            str(tot_sim_time),
            sim_files_to_save['trace']['to'].substitute(fno=str(file_no)),
            random_seed,
        ]
        simulation_status = subprocess.call(simulation_command)
        if simulation_status != 0:
            raise subprocess.CalledProcessError(
                simulation_status, simulation_command
            )


        rtl_cov_out_path = CORE_PT['cov_out_path_t'].substitute(tno=thread_no)
        cov_dict = parse_cov.vdb_to_dict(rtl_cov_out_path, cov_types, vdb_cov_files\
                        , core_instance_list, CORE_PT['vdb_test_dir'], 'detailed'\
                        , f"simulation for {ip_file} probably dint run properly, {file_no}, {thread_no}")


        for save_file, data in sim_files_to_save.items():
            if data["en"]:
                from_file = data["from"].substitute(tno=thread_no)
                assert os.path.exists(from_file), f"there is no file to copy {from_file}"
                destination = data["to"].substitute(fno=str(file_no))
                if save_file == 'cov':
                    with open(destination, 'wb') as fp:
                        pickle.dump(cov_dict, fp)
                else:
                    shutil.move(from_file, destination)


        if return_cov:
            return cov_dict
        else:
            return {k:'' for k in cov_dict.keys()}
    finally:
        locks[thread_no].release()

