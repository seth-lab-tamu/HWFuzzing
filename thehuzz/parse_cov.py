"""
- TODOs: 
    - optimize vdb_to_dict function
"""

import subprocess, os, re, json
import multiprocessing as mp, time, pickle
import xml.etree.ElementTree as et, gzip
from tqdm import tqdm
import numpy as np
import pickle

import thehuzz_utils

# get the instance list of the core form the coverage file
def get_inst_list(xml_dir):
    inst_list = []

    for xml_file in os.listdir(xml_dir):
        with gzip.open(xml_dir + xml_file, 'rb')  as fin:
            tree = et.parse(fin)
            root = tree.getroot()
            for child in root:
                if child.tag == "instance_data":
                    if child.attrib["name"] not in inst_list:
                        inst_list.append(child.attrib["name"])

    fp = open("list.py", "w")
    fp.write("l = [ \n")
    fp.write('    "' + inst_list[0] + '"\n')
    for inst in inst_list[1:]:
        fp.write('    ,"' + inst + '"\n')
    fp.close()



# parses the xml files from a single vdb file
# currently extracts only detailed cov
# detailed cov output is a string of 0's ad 1's 
def vdb_xml_to_array(xml_file: str, instance_list, type = 'total'):
    with gzip.open(xml_file, 'rb')  as fin:
        tree = et.parse(fin)
    root = tree.getroot()
    detailed_cov = {key: '' for key in instance_list}

    # get cov data of all modules
    for child in root:
        if child.tag == "instance_data":
            if child.attrib["name"] in instance_list: 
                        # make sure that this instance is one of the instances
                        # we are interested in 
                detailed_cov[child.attrib["name"]] = child.attrib["value"]

    # append to single array and return
    detailed_cov_str = ''
    index = 0
    for mod, cov in detailed_cov.items():
        #make sure the order is correct: 
        if not (mod == instance_list[index]):
            print("ERROR: module list not matching when parsing xml")
            print(xml_file)
            print(index, mod, instance_list[index])
            exit()
        detailed_cov_str = ''.join([detailed_cov_str, cov])
        index += 1

    return detailed_cov_str

# take vdb, return dict of all cov points
def vdb_to_dict(vdb_dir: str, cov_types, vdb_cov_files, instance_list\
        , vdb_test_dir, type = 'total', error_string=''):

    bins = {} #coverage of the binary
    for (cov_type, vdb_cov_file) in zip(cov_types, vdb_cov_files):
        vdb_cov_file_full_path = os.path.join(vdb_dir, vdb_test_dir, vdb_cov_file)
        assert os.path.exists(vdb_cov_file_full_path), f"couldnt find the coverage file {vdb_cov_file_full_path} {error_string}"
        bins[cov_type] = vdb_xml_to_array(vdb_cov_file_full_path, instance_list, type)
    return bins


"""
Load the cov dicts in case json files are input instead of the dicts themselves
- input type: 
    - dict: the cov dicts are in the form of python dicts
    - file: the cov dicts are in the form of json dump files containing the cov
            dicts
"""
def get_cov_dicts(cov_dicts_input, input_type='dict'): 
    # load the cov dicts if input type is file
    if input_type == 'file': 
        cov_data_dict = {}
        for file_i in cov_dicts_input.keys(): 
            with open(file_i, 'rb') as fp: cov_dict = pickle.load(fp)
            cov_data_dict[os.path.basename(file_i)] = cov_dict
    else: 
        cov_data_dict = cov_dicts_input

    return cov_data_dict


"""
Convert all the dicts into 2D numpy matrix
"""
def convert_cov_dicts_to_numpy(cov_data_dict): 

    example_cov_dict = cov_data_dict[0] # first get a example cov dict, just to store the cov format

    # load all the cov dicts to numpy matrix
    cov_dicts_list = np.zeros(( len(cov_data_dict), sum([len(s) for s in example_cov_dict.values()]) ), dtype='int')
    for i, cov_dict in enumerate(cov_data_dict): 
        #print({key: cov_str.count('1') for key, cov_str in cov_dict.items()})

        # convert cov data to one string and then numpy array
        cov_dict = ''.join(cov_dict.values())
        temp_list = np.frombuffer(cov_dict.encode(), dtype='u1') - ord('0')
        cov_dicts_list[i] = temp_list.astype('int')

    return cov_dicts_list


"""
Convert the numpy list to cov dict using the example cov dict for format
"""
def convert_numpy_to_cov_dict(merged_cov_list, example_cov_dict): 
    merged_cov_dict = {}
    tot_cov = 0
    for cov_type, cov_string in example_cov_dict.items():
        merged_cov_dict[cov_type] = ''.join(merged_cov_list[tot_cov : tot_cov + len(cov_string)].astype('str'))
        tot_cov += len(cov_string)
    
    return merged_cov_dict


"""
- Merges the cov dicts incrementally recording which cov dict increased how many
  coverage points --> this is used to check which input increased how much coverage
"""
def merge_cov_dicts_incremental(cov_dicts_input, input_type, initial_cov=None \
                                , time=None, debug_print=False):

    cov_data_dict = get_cov_dicts(cov_dicts_input, input_type) # get cov dicts
    assert cov_data_dict, "cannot merge an empty coverage dictionary"
    example_cov_dict = cov_data_dict[next(iter(cov_data_dict))] # first get a example cov dict, to use as cov template
    # if initial coverage is not provided, start with all points as uncovered
    if initial_cov == None: 
        merged_cov_dict = {key: '0'*len(data) for (key, data) in example_cov_dict.items()}
    else: 
        # Do not mutate the caller's initial coverage object. ReFuzz initializes
        # every MAB arm from the same global coverage dict, so in-place updates
        # would make all arms share one changing coverage state.
        merged_cov_dict = dict(initial_cov)

    cov_increment_dict = { prog_name: { 'id': prog_name\
                           , 'time': time\
                           , 'num_progs': 1\
                           , 'incr': {key: 0 for key in merged_cov_dict.keys()}\
                           , 'tot': {key: 0 for key in merged_cov_dict.keys()}} for prog_name in cov_data_dict.keys() }
    
    # compute the tot cov so far
    tot_cov = full_cov_to_cov_num(merged_cov_dict)

    for cov_type, cov_str in merged_cov_dict.items(): # cov_str is a string of 0's and 1's 
        cov_dicts_with_type = {prog_no: cov_dict for prog_no, cov_dict in cov_data_dict.items() if cov_type in cov_dict}
        if not cov_dicts_with_type:
            continue
        assert len(cov_dicts_with_type) == len(cov_data_dict), \
            f"coverage type {cov_type} is missing from some simulation results"
        for prog_no, cov_dict in cov_dicts_with_type.items():
            assert len(cov_dict[cov_type]) == len(cov_str), \
                f"coverage length mismatch for {cov_type} in {prog_no}: got {len(cov_dict[cov_type])}, expected {len(cov_str)}"

        new_merged_cov_arr = [*cov_str]
        itr = tqdm(cov_str, desc=f"------Merging {cov_type}") if debug_print else cov_str
        for i, cov_point in enumerate(itr): 
            # if cov point is already 1, no need to update merged cov and no incr in cov
            if not int(cov_point):
                prog_increasing_cov = -1
                for prog_no, cov_dict in cov_dicts_with_type.items(): 
                    if cov_dict[cov_type][i] == '1':
                        prog_increasing_cov = prog_no
                        break
                new_merged_cov_arr[i] = str(int(prog_increasing_cov != -1)) # if we found a 1, then merged coverage is 1

                if prog_increasing_cov != -1: 
                    cov_increment_dict[prog_increasing_cov]['incr'][cov_type] += 1

        merged_cov_dict[cov_type] = ''.join(new_merged_cov_arr)


    # calculate the tot cov by adding the cov increments for each program: 
    itr = tqdm(cov_increment_dict.items(), desc="------Computing total cov") if debug_print else cov_increment_dict.items()
    for prog_name, prog_dict in itr:
        tot_cov = {cov_type: no_points+prog_dict['incr'][cov_type] for cov_type,no_points in tot_cov.items()}  
        cov_increment_dict[prog_name]['tot'] = tot_cov  

    return merged_cov_dict, cov_increment_dict


"""
Merges the cov dicts either incrementally or directly based on the mode
- merge_mode: 
    - incremental: used by fuzzer to find cov increased by each input
    - direct: used by random regression to find total cov achieved so far
- input_type: 
    - dict: coverage data is input in the form of dicts
    - file: coverage data is input in the form of path to json files where cov
            dict is dumped
"""
def merge_cov_dicts(cov_dicts_input, input_type, merge_mode='incremental', \
                    initial_cov=None, time=None, arm_initial_cov_dict=None, \
                    particle_seed_ids=[], particle_initial_cov=None, \
                    debug_print=False):

    if merge_mode == 'incremental': 
        return merge_cov_dicts_incremental(cov_dicts_input, input_type, initial_cov, time)
    
    elif merge_mode == 'direct':
        last_prog = list(cov_dicts_input.keys())[-1] # get last prog first bcz cov_dicts_input is changed afterwards
        if initial_cov != None: # if initial cov is there, add it to the list of dicts to merge
            cov_dicts_to_merge = get_cov_dicts(cov_dicts_input, input_type) # get cov dicts
            input_type = 'dict' # change input type since already converted to dict
            cov_dicts_to_merge.update({'merged': initial_cov})
        else: 
            cov_dicts_to_merge = cov_dicts_input

        merged_cov_dict, t = merge_cov_dicts_direct([cov_dicts_to_merge, None, input_type])

        incr_cov_num = 0
        # in the cov incr dict, only add the cov of last prog
        merged_cov_num = full_cov_to_cov_num(merged_cov_dict, True)
        if initial_cov != None:
            initial_cov_num = full_cov_to_cov_num(initial_cov, True)
            incr_cov_num = {key: value - initial_cov_num.get(key, 0) for key, value in merged_cov_num.items()}
        else:
            incr_cov_num = merged_cov_num
        cov_increment_dict = { last_prog: { 'id': last_prog\
                           , 'time': time\
                           , 'num_progs': len(list(cov_dicts_input.keys()))\
                           , 'incr': incr_cov_num\
                           , 'tot': merged_cov_num} }

        return merged_cov_dict, cov_increment_dict

    elif merge_mode == 'mab': # get total merged cov and also arm's merged cov

        last_prog = list(cov_dicts_input.keys())[-1] # get last prog

        # merged cov of arm
        arm_merged_cov_dict, arm_cov_increment_dict \
            = merge_cov_dicts_incremental(cov_dicts_input, input_type, arm_initial_cov_dict, time)
        
        # total merged cov
        merged_cov_dict, cov_increment_dict = merge_cov_dicts({last_prog:arm_merged_cov_dict}\
                                            , 'dict', 'direct', initial_cov, time)
        cov_increment_dict[last_prog]['num_progs'] = len(list(cov_dicts_input.keys()))

        return merged_cov_dict, cov_increment_dict, None, None, arm_merged_cov_dict, arm_cov_increment_dict

    else: 
        assert 0, f"unknown merge mode, {CONFIG.merge_mode}."


"""
This function takes a list of coverage dicts as inputs and outputs which coverage points
are covered by all the coverage dictionaries
"""
def check_always_covered(arg_list):

    cov_dicts_input, mp_id, input_type = arg_list

    cov_data_dict = get_cov_dicts(cov_dicts_input, input_type) # get cov dicts
    cov_data_dict_list = list(cov_data_dict.values())
    example_cov_dict = cov_data_dict_list[0] # first get a example cov dict, to use as cov template

    cov_dicts_list = convert_cov_dicts_to_numpy(cov_data_dict_list)

    #check all covered points
    always_cov_list = np.bitwise_and.reduce(cov_dicts_list, axis=0)

    always_cov_dict = convert_numpy_to_cov_dict(always_cov_list, example_cov_dict)

    return [always_cov_dict, mp_id]
    #return merged_cov_dict


"""
This is same as the above merge function but this does only merge, no incremental
"""
def merge_cov_dicts_direct(arg_list):

    cov_dicts_input, mp_id, input_type = arg_list

    cov_data_dict = get_cov_dicts(cov_dicts_input, input_type) # get cov dicts
    cov_data_dict_list = list(cov_data_dict.values())
    example_cov_dict = cov_data_dict_list[0] # first get a example cov dict, to use as cov template

    cov_dicts_list = convert_cov_dicts_to_numpy(cov_data_dict_list)

    # merge all the files
    merged_cov_list = np.bitwise_or.reduce(cov_dicts_list, axis=0)

    merged_cov_dict = convert_numpy_to_cov_dict(merged_cov_list, example_cov_dict)

    return [merged_cov_dict, mp_id]
    #return merged_cov_dict


"""
"""
def merge_cov_dicts_from_lists(cov_dicts_lists, no_threads): 

    
    args = [ [{l:l for l in cov_files}, merged_file, 'file'] \
                        for merged_file, cov_files in cov_dicts_lists.items() ]

    with mp.Pool(processes=no_threads) as pool: 
        #[merged_cov_dict, merged_cov_file] = list(tqdm( pool.imap(merge_cov_dicts1, args), total=len(cov_dicts_lists), desc="[-------] merging cov dicts" ))
        return_data = list(tqdm( pool.imap(merge_cov_dicts_direct, args), total=len(cov_dicts_lists), desc="[-------] merging cov dicts" ))

    for merged_cov_dict, merged_cov_file in return_data: 
        # save the merged file
        with open(merged_cov_file, 'wb') as fp:
            pickle.dump(merged_cov_dict, fp)


def full_cov_to_cov_num(full_cov_dict, include_tot=False): 
    cov_num_dict = {key: cov_str.count('1') for key, cov_str in full_cov_dict.items()}
    if include_tot: 
        cov_num_dict['total'] = sum(cov_num_dict.values())
    return cov_num_dict

if __name__ == '__main__':
    temp = 1


####################
# depreciated code #
####################
