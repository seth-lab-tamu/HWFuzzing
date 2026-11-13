

import os
import multiprocessing as mp, pickle
import xml.etree.ElementTree as et, gzip
from tqdm import tqdm
import numpy as np




def assertion_value_to_bits(value, xml_file, error_string):
    values = [int(item) for item in value.split()]
    bits = ''
    index = 0
    while index + 5 < len(values):
        if values[index] != 5:
            index += 1
            continue
        if values[index + 5] not in (0, 1):
            raise ValueError(
                f"malformed assertion coverage in {xml_file}: "
                f"{values[index:]} {error_string}"
            )
        bits += str(int(values[index + 1] > 0 or values[index + 3] > 0))
        index += 6
    return bits


def vdb_xml_to_array(xml_file: str, instance_list, type = 'total',
                     cov_type='line', error_string=''):
    with gzip.open(xml_file, 'rb')  as fin:
        tree = et.parse(fin)
    root = tree.getroot()
    detailed_cov = {key: '' for key in instance_list}
    selected_instances = set(instance_list)


    for child in root:
        if child.tag == "instance_data":
            if child.attrib["name"] in selected_instances:


                value = child.attrib["value"]
                if cov_type == 'assert':
                    value = assertion_value_to_bits(
                        value, xml_file, error_string
                    )
                detailed_cov[child.attrib["name"]] = value


    detailed_cov_str = ''
    index = 0
    for mod, cov in detailed_cov.items():

        if not (mod == instance_list[index]):
            print("ERROR: module list not matching when parsing xml")
            print(xml_file)
            print(index, mod, instance_list[index])
            exit()
        detailed_cov_str = ''.join([detailed_cov_str, cov])
        index += 1

    return detailed_cov_str


def vdb_to_dict(vdb_dir: str, cov_types, vdb_cov_files, instance_list\
        , vdb_test_dir, type = 'total', error_string=''):

    bins = {}
    for (cov_type, vdb_cov_file) in zip(cov_types, vdb_cov_files):
        vdb_cov_file_full_path = os.path.join(vdb_dir, vdb_test_dir, vdb_cov_file)
        assert os.path.exists(vdb_cov_file_full_path), f"couldnt find the coverage file {vdb_cov_file_full_path} {error_string}"
        bins[cov_type] = vdb_xml_to_array(
            vdb_cov_file_full_path,
            instance_list,
            type,
            cov_type,
            error_string,
        )
    return bins









def get_cov_dicts(cov_dicts_input, input_type='dict'): 

    if input_type == 'file': 
        cov_data_dict = {}
        for file_i in cov_dicts_input.keys(): 
            with open(file_i, 'rb') as fp: cov_dict = pickle.load(fp)
            cov_data_dict[os.path.basename(file_i)] = cov_dict
    else: 
        cov_data_dict = cov_dicts_input

    return cov_data_dict





def convert_cov_dicts_to_numpy(cov_data_dict): 

    example_cov_dict = cov_data_dict[0]


    cov_dicts_list = np.zeros(( len(cov_data_dict), sum([len(s) for s in example_cov_dict.values()]) ), dtype='int')
    for i, cov_dict in enumerate(cov_data_dict): 



        cov_dict = ''.join(cov_dict.values())
        temp_list = np.frombuffer(cov_dict.encode('ascii'), dtype='u1') - ord('0')
        cov_dicts_list[i] = temp_list.astype('int')

    return cov_dicts_list





def convert_numpy_to_cov_dict(merged_cov_list, example_cov_dict): 
    merged_cov_dict = {}
    tot_cov = 0
    for cov_type, cov_string in example_cov_dict.items():
        merged_cov_dict[cov_type] = ''.join(merged_cov_list[tot_cov : tot_cov + len(cov_string)].astype('str'))
        tot_cov += len(cov_string)
    
    return merged_cov_dict






def merge_cov_dicts_incremental(cov_dicts_input, input_type, initial_cov=None \
                                , time=None, debug_print=False):

    cov_data_dict = get_cov_dicts(cov_dicts_input, input_type)
    example_cov_dict = cov_data_dict[next(iter(cov_data_dict))]

    if initial_cov == None: 
        merged_cov_dict = {key: '0'*len(data) for (key, data) in example_cov_dict.items()}
    else: 
        merged_cov_dict = initial_cov

    cov_increment_dict = { prog_name: { 'id': prog_name\
                           , 'time': time\
                           , 'incr': {key: 0 for key in merged_cov_dict.keys()}\
                           , 'tot': {key: 0 for key in merged_cov_dict.keys()}} for prog_name in cov_data_dict.keys() }
    

    tot_cov = full_cov_to_cov_num(merged_cov_dict)

    for cov_type, cov_str in merged_cov_dict.items():
        new_merged_cov_arr = [*cov_str]
        itr = tqdm(cov_str, desc=f"------Merging {cov_type}") if debug_print else cov_str
        for i, cov_point in enumerate(itr): 

            if not int(cov_point):
                prog_increasing_cov = -1
                for prog_no, cov_dict in cov_data_dict.items(): 
                    if cov_dict[cov_type][i] == '1':
                        prog_increasing_cov = prog_no
                        break
                new_merged_cov_arr[i] = str(int(prog_increasing_cov != -1))

                if prog_increasing_cov != -1: 
                    cov_increment_dict[prog_increasing_cov]['incr'][cov_type] += 1

        merged_cov_dict[cov_type] = ''.join(new_merged_cov_arr)



    itr = tqdm(cov_increment_dict.items(), desc="------Computing total cov") if debug_print else cov_increment_dict.items()
    for prog_name, prog_dict in itr:
        tot_cov = {cov_type: no_points+prog_dict['incr'][cov_type] for cov_type,no_points in tot_cov.items()}  
        cov_increment_dict[prog_name]['tot'] = tot_cov  

    return merged_cov_dict, cov_increment_dict












def merge_cov_dicts(cov_dicts_input, input_type, merge_mode='incremental', initial_cov=None \
                                , time=None, debug_print=False):

    if merge_mode == 'incremental': 
        return merge_cov_dicts_incremental(cov_dicts_input, input_type, initial_cov, time)
    
    elif merge_mode == 'direct':
        last_prog = list(cov_dicts_input.keys())[-1]
        if initial_cov != None:
            cov_dicts_to_merge = get_cov_dicts(cov_dicts_input, input_type)
            input_type = 'dict'
            cov_dicts_to_merge.update({'merged': initial_cov})
        else: 
            cov_dicts_to_merge = cov_dicts_input

        merged_cov_dict, t = merge_cov_dicts_direct([cov_dicts_to_merge, None, input_type])
      

        cov_increment_dict = { last_prog: { 'id': last_prog\
                           , 'time': time\
                           , 'tot': full_cov_to_cov_num(merged_cov_dict, True)} }

        return merged_cov_dict, cov_increment_dict

    else: 
        assert 0, f"unknown merge mode, {CONFIG.merge_mode}."






def check_always_covered(arg_list):

    cov_dicts_input, mp_id, input_type = arg_list

    cov_data_dict = get_cov_dicts(cov_dicts_input, input_type)
    cov_data_dict_list = list(cov_data_dict.values())
    example_cov_dict = cov_data_dict_list[0]

    cov_dicts_list = convert_cov_dicts_to_numpy(cov_data_dict_list)


    always_cov_list = np.bitwise_and.reduce(cov_dicts_list, axis=0)

    always_cov_dict = convert_numpy_to_cov_dict(always_cov_list, example_cov_dict)

    return [always_cov_dict, mp_id]






def merge_cov_dicts_direct(arg_list):

    cov_dicts_input, mp_id, input_type = arg_list

    cov_data_dict = get_cov_dicts(cov_dicts_input, input_type)
    cov_data_dict_list = list(cov_data_dict.values())
    example_cov_dict = cov_data_dict_list[0]

    cov_dicts_list = convert_cov_dicts_to_numpy(cov_data_dict_list)


    merged_cov_list = np.bitwise_or.reduce(cov_dicts_list, axis=0)

    merged_cov_dict = convert_numpy_to_cov_dict(merged_cov_list, example_cov_dict)

    return [merged_cov_dict, mp_id]





def merge_cov_dicts_from_lists(cov_dicts_lists, no_threads): 

    
    args = [ [{l:l for l in cov_files}, merged_file, 'file'] \
                        for merged_file, cov_files in cov_dicts_lists.items() ]

    with mp.Pool(processes=no_threads) as pool: 

        return_data = list(tqdm( pool.imap(merge_cov_dicts_direct, args), total=len(cov_dicts_lists), desc="[-------] merging cov dicts" ))

    for merged_cov_dict, merged_cov_file in return_data: 

        with open(merged_cov_file, 'wb') as fp:
            pickle.dump(merged_cov_dict, fp)


def full_cov_to_cov_num(full_cov_dict, include_tot=False): 
    cov_num_dict = {key: cov_str.count('1') for key, cov_str in full_cov_dict.items()}
    if include_tot: 
        cov_num_dict['total'] = sum(cov_num_dict.values())
    return cov_num_dict


if __name__ == '__main__':
    temp = 1
