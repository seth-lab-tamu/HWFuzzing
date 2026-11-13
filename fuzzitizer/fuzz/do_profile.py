
import subprocess, os
import logging as lg # critical, error, warning, info, debug

from path_setup import configure_project_paths

FUZZITIZER_ROOT = configure_project_paths()

import config
from configManager import getCONFIG
import prog_gen, riscv_isa, prog_mut, parse_cov, fuzz, cplex_optimizer
import fuzz_utils as TU



"""
get all the cov files for each inst mut pair 
"""
def get_merged_cov_filelist(instr_list, sim_store_dir, merged_covs_dir\
                          , cov_out_t, num_itr_per_inst, mut_list, num_inst_in_prog_prof): 
    inst_mut_cov_filelist = {}
    for inst_i, inst_data in enumerate(instr_list.values()):
        for mut_i in mut_list:          
            inst_mut_merged_cov_file = os.path.join( merged_covs_dir\
                        , cov_out_t.substitute(fno=f'{inst_i}_mut_{mut_i}') )
            inst_mut_cov_filelist[inst_mut_merged_cov_file] = []
            for itr_i in range(num_itr_per_inst):
                num_files_inst_type = num_inst_in_prog_prof if int(inst_data[6]) == 1 else 1
                inst_mut_cov_filelist[inst_mut_merged_cov_file] += \
                    [ os.path.join(sim_store_dir\
                   , cov_out_t.substitute(fno=f'{inst_i}_itr_{itr_i}_mut_{mut_i}_inst_{i}')) for i in range(num_files_inst_type) ]
    
    return inst_mut_cov_filelist



"""
The main function that does profiling
- It uses CPLEX optimizer
"""
def profile(prog_time, CONFIG_PT, CONFIG_CORE_PT\
           , prof_gen_progs, prof_mut_progs, prof_run_progs, prof_merge_cov\
           , prof_run_optimizer, prof_check_prog_files\
           , num_inst_in_prog_prof, num_itr_per_inst, instr_list\
           , num_nops_at_start, num_nops_at_end, nop_inst_bin_32, no_threads\
           , inst_list_all_w_ext, store_trace_file, store_cov_file\
           , core, tot_sim_time, cov_enable, cov_types, vdb_cov_files, instance_list\
           , val_muts, debug_print=False):

    mut_list = [i for i in range(8)]
    lg.debug(f"instr list: {instr_list}")

    if prof_gen_progs: 
        TU.TIMELOG(prog_time, f" -- generating progs, one for each inst", False, True)
        prog_gen.gen_all_inst_files(True, prof_check_prog_files, CONFIG_PT["gen_progs_dir"]\
                     , num_inst_in_prog_prof, num_itr_per_inst, instr_list\
                     , num_nops_at_start, num_nops_at_end\
                     , CONFIG_PT["sw_run_dir"], nop_inst_bin_32, no_threads\
                     , CONFIG_PT["trash_run_dir"], debug_print)
        TU.TIMELOG(prog_time, f" -- generating progs, one for each inst", True, True)

    if prof_mut_progs:
        TU.TIMELOG(prog_time, f" -- mutating each prog with each mut technique", False, True)
        itr_prog_files = TU.get_files_in_dir(CONFIG.pt["gen_progs_dir"]\
                                     , CONFIG.pt["hex_file_itr_re"])
        lg.debug(f"prog files with itrs: {[os.path.basename(i_file) for i_file in itr_prog_files]}")

        prog_mut.gen_mut_files(itr_prog_files\
                         , CONFIG_PT['all_progs_dir'], inst_list_all_w_ext\
                         , instr_list, CONFIG_PT["hex_file_itr_re"]\
                         , num_inst_in_prog_prof, nop_inst_bin_32, CONFIG_PT["hex_file_mut_t"], val_muts) 
        TU.TIMELOG(prog_time, f" -- mutating each prog with each mut technique", True, True)

    cov_data = {}
    if prof_run_progs: 
        TU.TIMELOG(prog_time, f" -- simulating all the files and collecting cov", False, True)
        mut_prog_files = TU.get_files_in_dir(CONFIG.pt["all_progs_dir"]\
                                     , CONFIG.pt["hex_file_mut_re"])
        save_ids = [os.path.splitext(prog)[0].split('inst_file_')[1] for prog in mut_prog_files]
        lg.debug(f"prog files with muts: {[os.path.basename(i_file) for i_file in mut_prog_files]}")

        cov_data = fuzz.sim_testcases(mut_prog_files, save_ids, CONFIG_CORE_PT, CONFIG_PT
               , no_threads, core\
               , store_trace_file, store_cov_file, tot_sim_time, cov_enable\
               , cov_types, vdb_cov_files, instance_list, return_cov=False)

        TU.TIMELOG(prog_time, f" -- simulating all the files and collecting cov", True, True)

    if prof_merge_cov: 
        TU.TIMELOG(prog_time, f" --merge coverage data and measure the increment in cov", False, True)

        # get all the cov files for each inst mut pair 
        inst_mut_cov_filelist = get_merged_cov_filelist(instr_list, CONFIG_PT['sim_store_dir']\
                                                    , CONFIG_PT['merged_covs_dir']\
                                                    , CONFIG_PT['cov_out_t'], num_itr_per_inst\
                                                    , mut_list, num_inst_in_prog_prof)

        # merge the coverage of all files in each inst mut pairs
        parse_cov.merge_cov_dicts_from_lists(inst_mut_cov_filelist, no_threads)

        TU.TIMELOG(prog_time, f" --merge coverage data and measure the increment in cov", True, True)

    # run the optimizer
    if prof_run_optimizer: 
        TU.TIMELOG(prog_time, f" -- running the optimizer", False, True)
        inst_mut_cov_filelist = get_merged_cov_filelist(instr_list, CONFIG_PT['sim_store_dir']\
                                                    , CONFIG_PT['merged_covs_dir']\
                                                    , CONFIG_PT['cov_out_t'], num_itr_per_inst, mut_list\
                                                    , num_inst_in_prog_prof)
        cplex_optimizer.generate_optimized_solution(inst_mut_cov_filelist.keys()\
                                , instr_list, mut_list, CONFIG_PT)
        TU.TIMELOG(prog_time, f" -- running the optimizer done", True, True)


"""
Deletes any previous logs and starts profiling
"""
def main(prog_time): 

    print(f"[-------] Deleting previous log files")
    TU.delete_dir(CONFIG.pt['outputs_run_dir'], CONFIG.force_delete) 
    TU.delete_dir(CONFIG.pt['trash_run_dir'], CONFIG.force_delete) 
    subprocess.call([ 'mkdir', CONFIG.pt['all_progs_dir'] ])
    subprocess.call([ 'mkdir', CONFIG.pt['sim_store_dir'] ])
    subprocess.call([ 'mkdir', CONFIG.pt['merged_covs_dir'] ])
    print(f"[-------] Deleting previous log files done")

    
    print(f"[-------] Setup simulation repositories")
    TU.setup_simulation_repos(CONFIG.CORE.pt['sim_dir_t'], CONFIG.no_threads)
    print(f"[-------] Setup simulation repositories done")

    prog_time.reset_start_time()

    # set the log file
    debug_level = lg.DEBUG if CONFIG.debug_print else lg.INFO 
    lg.basicConfig(filename=CONFIG.pt['fuzz_log_file'], filemode='w', level=debug_level)

    TU.TIMELOG(prog_time, f" Getting the parameters for the profiler", False, True)
    TU.TIMELOG(prog_time, f" Getting the parameters for the profiler", True, True)
   

    TU.TIMELOG(prog_time, f" Profiling the given benchmark, {CONFIG.core_name}", False, True)
    
    profile(prog_time, CONFIG.pt,   CONFIG.CORE.pt\
          , CONFIG.prof_gen_progs,  CONFIG.prof_mut_progs\
          , CONFIG.prof_run_progs,  CONFIG.prof_merge_cov,      CONFIG.prof_run_optimizer\
          , CONFIG.prof_check_prog_files,                       CONFIG.num_inst_in_prog_prof\
          , CONFIG.num_itr_per_inst,riscv_isa.inst_list_all_w_ext, CONFIG.num_nops_at_start\
          , CONFIG.num_nops_at_end, riscv_isa.nop_inst_bin_32\
          , CONFIG.no_threads,      riscv_isa.inst_list_all_w_ext, CONFIG.store_trace_file\
          , CONFIG.store_cov_file,  CONFIG.core_name\
          , CONFIG.CORE.tot_sim_time,CONFIG.cov_enable,         CONFIG.cov_types\
          , CONFIG.vdb_cov_files,   CONFIG.core_instance_list\
          , CONFIG.val_muts,        CONFIG.debug_print)

    TU.TIMELOG(prog_time, f" Profiling the given benchmark, {CONFIG.core_name} done", False, True)


if __name__ == '__main__': 

    prog_time = TU.Mytime()

    CONFIG = getCONFIG(config, configType='file')
    
    main(prog_time)
