#inspired from http://www.neos-guide.org/content/diet-problem-solver


import os, re
from collections import namedtuple
import json
import pickle
from tqdm import tqdm

from docplex.mp.model import Model
from docplex.util.environment import get_environment
import parse_cov


no_mut = 8
                                                

def build_opt_model(instr_list, mut_list, example_cov_dict, all_cov_data\
                  , name='optimizer', **kwargs):

  
    INST_MUTS = [('_'.join(list(opcode)+[str(mut)]), 1, 0, 1) for opcode in instr_list \
                                       for mut in mut_list ]
    inst_mut_tup = namedtuple("inst_mut", ["name", "unit_cost", "qmin", "qmax"])
    inst_muts = [inst_mut_tup(*im) for im in INST_MUTS]
   
    
    all_merged_cov = parse_cov.merge_cov_dicts_direct([all_cov_data, None, 'dict'])
    all_merged_cov = all_merged_cov[0]
    tot_profile_cov = {key: cov_str.count('1') for key, cov_str in all_merged_cov.items()}
    tot_profile_cov['Total'] = sum(tot_profile_cov.values())
    print(f"[-------] -- Total profiling coverage: {tot_profile_cov}")
    COV_BINS = [(cov_type+'_'+str(i), 1, int(cov_point_data), int(cov_point_data)*10000)\
                                for cov_type, cov_data in all_merged_cov.items()\
                                            for i,cov_point_data in enumerate(cov_data)]
    

    # if a coverage point is covered always, ignore it (to reduce load on optimizer)
    always_cov = parse_cov.check_always_covered([all_cov_data, None, 'dict'])
    always_cov = always_cov[0]
    tot_all_cov = {key: cov_str.count('1') for key, cov_str in always_cov.items()}
    tot_all_cov['Total'] = sum(tot_all_cov.values())
    print(f"[-------] -- Total always coverage: {tot_all_cov}")
    for i, cov_bin in enumerate(tqdm(COV_BINS, desc="[-------] -- Remove points that are always covered")):
        cov_type = cov_bin[0].split('_')[0]
        cov_type_no = int(cov_bin[0].split('_')[1])
        if always_cov[cov_type][cov_type_no] == '1': 
            COV_BINS[i] = (cov_bin[0], cov_bin[1], 0,0)
        
    ints = kwargs.pop('ints', 'False')
    mdl = Model(name=name, **kwargs)

    print(f"[-------] -- Adding inst_mut pairs as variables to model...")
    imtype = mdl.integer_vartype if ints else mdl.continuous_vartype
    im_bool = mdl.var_dict(inst_muts, imtype, lb=lambda im:im.qmin, ub=lambda im:im.qmax\
                                           , name=lambda im: "bool_"+im.name)

    cov_bool_dict = {}
    for i, cov_bin in enumerate(tqdm(COV_BINS, desc="[-------] -- Adding bin inequations to model")):
        cov_type = cov_bin[0].split('_')[0]
        cov_type_no = int(cov_bin[0].split('_')[1])
        if cov_bin[3] > 0:
            cov_bool = mdl.sum(im_bool[im] * int(all_cov_data[im.name][cov_type][cov_type_no]) for im in inst_muts)
            cov_bool_dict[cov_bin[0]] = cov_bool
            mdl.add_range(cov_bin[2], cov_bool, cov_bin[3])

    # Minimize cost
    print(f"[-------] -- Adding total cost")
    total_cost = mdl.sum(im_bool[im] * im.unit_cost for im in inst_muts)
    mdl.add_kpi(total_cost, 'Total cost')

    def nb_products(mdl_, s_):
        im_sol = mdl_.find_matching_vars(pattern="bool_")
        return sum(1 for im in im_sol if s_[im] >= 1e-5)

    mdl.add_kpi(nb_products, 'Num inst-mut pairs used')
    mdl.minimize(total_cost)

    return mdl


def get_sol(sol_file):
    sol = {}

    sol_file_p = open(sol_file, 'r')
    sol_data_json = json.load(sol_file_p)

    for variable in sol_data_json["CPLEXSolution"]["variables"]:
        if variable["value"] == '1.0':
            name_data = re.match('bool_([^"]*)_([0-9])', variable["name"])
            sol_opcode = name_data.group(1)
            sol_mut = int(name_data.group(2))
            if sol_opcode in sol:
                sol[sol_opcode].append(sol_mut)
            else:
                sol[sol_opcode] = [sol_mut]

    return sol


"""
"""
def generate_optimized_solution(inst_mut_cov_filelist, instr_list, mut_list\
                , CONFIG_PT): 

    example_cov_dict = None
    all_cov_data = {}
    for cov_dict_file in tqdm(inst_mut_cov_filelist, desc="[-------] -- loading cov data from files"): 
        file_details = re.match("^rtl_cov_out_([0-9]+)_mut_([0-9]+).pickle$", os.path.basename(cov_dict_file))
        opcode = list(instr_list.keys())[int(file_details.group(1))]
        opcode = '_'.join(opcode)
        mut = int(file_details.group(2))
        with open(cov_dict_file, 'rb') as fp: 
            all_cov_data[f"{opcode}_{mut}"] = pickle.load(fp)
            if not example_cov_dict: example_cov_dict = all_cov_data

    # build the optimizer model
    mdl = build_opt_model(instr_list, mut_list, example_cov_dict, all_cov_data\
            , name='optimizer'\
            , ints=True, log_output=True, float_precision=6)
    mdl.print_information()

    # run the model to get the optimal solution
    s = mdl.solve()
    if s:
        im_sol = mdl.find_matching_vars(pattern="bool_")
        for im in im_sol:
            im_name = im.name[5:]
            print("Use {0:<25} = {1:9.6g}".format(im_name, im.solution_value))

        mdl.report_kpis()
        with get_environment().get_output_stream("cplex_cov_solution.json") as fp:
            mdl.solution.export(fp, "json")
    else:
        print("* model has no solution")




if __name__ == '__main__':

    t = 1
