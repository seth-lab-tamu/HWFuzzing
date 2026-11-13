import subprocess, os, re, json
import random
from tqdm import tqdm

import fuzz_utils



def calc_no_times_to_mut(num_times_to_mut, times_mutated\
                         , cov_incr_dict, num_new_testcases, feedback_cov_types):

    n = num_new_testcases
    queue_load = 1 if n>10_000 else ( 0.75 if n>5_000 else (0.5 if n>1_000 else 0) )

    num_times_to_mut_local = num_times_to_mut 

    cov_incr = sum([cov_incr_dict[cov_type] for cov_type in feedback_cov_types])

    mut_type = "no_mut"

    if cov_incr > 0:

        num_times_to_mut_local = num_times_to_mut*(1-queue_load)


        decr_factor = 0.25 if times_mutated>3 else (0.5 if times_mutated>1 else 1 )
        num_times_to_mut_local = int(num_times_to_mut_local*decr_factor)

        if (num_times_to_mut_local < 1):
            num_times_to_mut_local = 1
        mut_type = 'interesting'
    else:



        if times_mutated == 0:
            num_times_to_mut_local = random.randint(0,max(int(num_times_to_mut/2), 1))
            mut_type = 'just_gen'
        else:
            num_times_to_mut_local = 0
            mut_type = 'no_mut'
            
    return num_times_to_mut_local, mut_type



def feedback_based_selection(num_new_testcases, testcases_to_sim\
                    , cov_increment_data_dict, num_times_to_mut, feedback_cov_types):


    progs_to_mut = []
    interesting_testcases = []
    just_generated_testcases = []
    no_times_to_mut_prog_local = 0

    for testcase in testcases_to_sim:
        testcase['mut_times'], mut_type = calc_no_times_to_mut(\
                num_times_to_mut,  testcase['times_mutated']\
                , cov_increment_data_dict[testcase['id']]['incr'], num_new_testcases\
                , feedback_cov_types)

        if mut_type == 'interesting': 
            interesting_testcases.append( [testcase['id'], testcase['mut_times']] )
        elif mut_type == 'just_gen': 
            just_generated_testcases.append( [testcase['id'], testcase['mut_times']] )
        else: 
            assert mut_type == 'no_mut', f"unknown reason for mutation: {mut_type}"

    return testcases_to_sim, interesting_testcases, just_generated_testcases




if __name__ == '__main__':
    temp = 1
