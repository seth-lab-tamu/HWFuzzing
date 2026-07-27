# Author: Chen Chen
# Date: 08/19/2022

import os, json, re, random
from os.path import join
import pandas as pd
from AutoParse import parse_design, build_hier_path, rm_nonrelated_insts, \
                      parse_cov_file, find_cov_point
from Config import *

script_path = os.getcwd()
cov_xml = join(script_path, 'cov_xml')
design_xml = join(cov_xml, 'snps/coverage/db/design/verilog.design.xml')
data_xml = join(cov_xml, 'snps/coverage/db/testdata/test') # a folder store coverage results
shape_xml = join(cov_xml, 'snps/coverage/db/shape') # a folder store conditions to cover branch points
target_metric = 'branch'
uncovd_json = join(script_path, "uncovd_point.json")
topbot_csv = join(script_path, f"{core}_topbot.csv")
bottop_csv = join(script_path, f"{core}_bottop.csv")
fanout_xlsx = join(script_path, f'fanout_data.xlsx')

def get_inst_db():
    inst_db = {}
    inst_db = parse_design(design_xml, inst_db)

    # construct hier. path of each instance
    for inst in inst_db.values():
        hier_path = ''
        hier_path = build_hier_path(inst, hier_path, inst_db)
        inst.hier_path = hier_path
        path_top = hier_path[hier_path.find(top_mod):]
        inst.hier_path_jg = path_top[path_top.find(".") + 1:]

    # verify if there are duplicated hier_path
    path_set = set()
    dups = []
    for inst in inst_db.values():
        if inst.hier_path in path_set:
            dups.append(inst)
        else:
            path_set.add(inst.hier_path)

    if len(dups) > 0:
        print("parse_file: script generates duplicate hier_path")
        exit()

    inst_db = rm_nonrelated_insts(inst_db)

    return inst_db


def module_hierarchy():
    def get_distance(inst_id, db):
        curr = inst_id
        dist = 0
        try:
            while db[curr].inst_name != top_mod:
                curr = db[curr].inst_pid
                dist += 1
            return dist
        except KeyError:
            return None

    inst_db = get_inst_db()
    inst_ids = inst_db.keys()
    out_ids = []

    for inst_id in inst_db.keys():
        dist = get_distance(inst_id, inst_db)
        if dist is not None:
            out_ids.append((inst_id, dist))
    out_ids.sort(key=lambda x: x[1])

    with open(topbot_csv, "w") as f: 
        f.write("inst,hierpath,distance\n") 
        for inst_id, dist in out_ids:
            inst = inst_db[inst_id]
            f.write(f"{inst.inst_name},{inst.hier_path},{dist}\n")

    with open(bottop_csv, "w") as f: 
        f.write("inst,hierpath,distance\n") 
        for inst_id, dist in reversed(out_ids):
            inst = inst_db[inst_id]
            f.write(f"{inst.inst_name},{inst.hier_path},{dist}\n")


def preprocess():
    print("======Preprocess design information======")
    # TopBot, BotTop
    # measure the distance to the top module
    # read module hierarchy from coverage report
    # the function will dump two csv files 
    module_hierarchy()

    # ModDep
    # count the fanout of each instance's outputs
    # the fanout info is from Jaspergold
    # we check each output's cone of influence across the entire design
    # the input file is too huge, the final csv file is in the folder

 
def convert_to_prop(point):
    cov_prop_expr = ''
    for i, cond in enumerate(point):
        if type(cond[1]) == str: # the expression is a case item
            # multiple case items may share the same point
            # by default use the first expression of the case list
            case_list = re.split(r'(?<!,)\s', cond[1])
            case = case_list[0]
            cov_prop_expr += f'{cond[0]} == {case}'
        elif type(cond[1]) == int:
            use_expr = cond[0]
            if cond[1] == 1: # True
                cov_prop_expr += use_expr
            elif cond[1] == 0:
                cov_prop_expr += f'!({use_expr})'
            else:
                print('convert_to_prop: unknow expression: ', cond)
                print('point: ', point)
                exit()
        else:
            print('add_cmd_content: unknow type expression: ', cond)
            print('point: ', point)
            exit()

        if i != len(point) - 1: # not the last condition
            cov_prop_expr += ' && '

    return cov_prop_expr


def compare_rate(rate_fuzz, points_select):
    print("======Compare rate and determine if it is the time to switch to formal======")
    switch_to_formal = False
    # calculate the rate of formal
    time = 0
    num_point = len(points_select)
    for point in points_select:
        time += points_select[point]
    rate_formal = float(num_point) / float(time)
    print("\tRate of fuzzing: ", rate_fuzz)
    print("\tRate of formal: ", rate_formal)

    if rate_formal > rate_fuzz:
        switch_to_formal = True
    print("\tSwitch to formal: ", switch_to_formal)

    return switch_to_formal


def iden_uncovd_points():
    print("======Identify uncovered points in a DUT======")
    cov_db = {} # dump uncovered points of each instance as a json file
    # parse the design xml file to get inst list
    inst_list, tot_cov, tot_covd = parse_cov_file(design_xml, data_xml)
    print(f"Total points of {target_metric} coverage: ", tot_cov[target_metric])
    print(f"Total covered points of {target_metric} coverage: ", tot_covd[target_metric])

    for inst in inst_list:
        if target_metric not in inst.tot_cov.keys():
            # instance has no target point
            continue

        if inst.tot_cov[target_metric] == inst.tot_covd[target_metric]:
            # all target points have been covered
            continue

        cov_db[inst.hier_path] = {}
        # record basic info of the instance
        cov_db[inst.hier_path]["inst_name"] = inst.inst_name
        cov_db[inst.hier_path]["inst_id"] = inst.inst_id
        cov_db[inst.hier_path]["inst_pid"] = inst.inst_pid
        cov_db[inst.hier_path]["module_name"] = inst.mod_name
        cov_db[inst.hier_path]["mod_id"] = inst.mod_id
        # record conditions of uncovered points
        cov_db[inst.hier_path]["uncovd_points"] = {}
        cov_points = []
        shape_id_list = []
        num_uncov = 0
        cov_points, shape_id_list = find_cov_point(inst, target_metric, shape_xml)
        for shape in cov_points:
            for point in shape:
                shape_id = shape_id_list[num_uncov]
                # convert conditions of a point into a cover property
                cov_prop_expr = convert_to_prop(point)
                cov_db[inst.hier_path]["uncovd_points"][shape_id] = cov_prop_expr
                num_uncov += 1                


    with open(uncovd_json, 'w') as fp:
        json.dump(cov_db, fp, indent=2)


def print_cov_prop(strategy: str, select_points, uncov_db):
    print("point selection strategy: ", strategy)
    for point in select_points:
        match = re.search(inst_point_re, point)
        if match:
            inst_id = match.group(1)
            point_id = match.group(2)
            cov_prop_expr = f'cover property {point} {{'
            for inst in uncov_db:
                if uncov_db[inst]["inst_id"][1:] == inst_id:
                    inst_uncovd_points = uncov_db[inst]["uncovd_points"]
                    cov_prop_expr = cov_prop_expr + inst_uncovd_points[point_id] + '}'
                    break
            print(cov_prop_expr)


def sel_point(uncovd_points):
    select_points = []
    if len(uncovd_points) != 0:
        if len(uncovd_points) < num_point_sel:
            select_points = uncovd_points
        else:
            select_points = random.sample(uncovd_points, num_point_sel)

    return select_points


def randsel(uncov_db):
    uncovd_points = []
    select_points = []
    for inst in uncov_db:
        inst_id = uncov_db[inst]["inst_id"][1:]
        inst_uncovd_points = uncov_db[inst]["uncovd_points"]
        for point_id in inst_uncovd_points:
            inst_point_id = f'{inst_id}_{point_id}'
            uncovd_points.append(inst_point_id)

    select_points = sel_point(uncovd_points)

    print_cov_prop('randsel', select_points, uncov_db)


def maxuncovd(uncov_db):
    uncovd_points = []
    select_points = []
    tar_inst_id = None
    tar_uncovd_points = []
    max_num_uncov = None
    for inst in uncov_db:
        inst_id = uncov_db[inst]["inst_id"][1:]
        inst_uncovd_points = uncov_db[inst]["uncovd_points"]
        num_uncov = len(inst_uncovd_points)
        if max_num_uncov is None or num_uncov > max_num_uncov:
            max_num_uncov = num_uncov
            tar_inst_id = inst_id
            tar_uncovd_points = inst_uncovd_points

    for point_id in tar_uncovd_points:
        inst_point_id = f'{tar_inst_id}_{point_id}'
        uncovd_points.append(inst_point_id)

    select_points = sel_point(uncovd_points)

    print_cov_prop('maxuncovd', select_points, uncov_db)


def moddep_topbot_bottop(strategy, uncov_db, moddep_list, topbot_list, bottop_list):
    uncovd_points = []
    select_points = []
    tar_inst_id = None
    tar_uncovd_points = []
    tar_inst_list = []

    if strategy == 'moddep':
        tar_inst_list = moddep_list
    elif strategy == 'topbot':
        tar_inst_list = topbot_list
    elif strategy == 'bottop':
        tar_inst_list = bottop_list


    for inst in tar_inst_list:
        inst_id = uncov_db[inst]["inst_id"][1:]
        inst_uncovd_points = uncov_db[inst]["uncovd_points"]
        num_uncov = len(inst_uncovd_points)
        if num_uncov > 0: # has uncovd points
            tar_inst_id = inst_id
            tar_uncovd_points = inst_uncovd_points
            break

    for point_id in tar_uncovd_points:
        inst_point_id = f'{tar_inst_id}_{point_id}'
        uncovd_points.append(inst_point_id)

    select_points = sel_point(uncovd_points)

    print_cov_prop(strategy, select_points, uncov_db)


def sel_uncovd_point(uncovd_json, topbot_csv, bottop_csv, fanout_xlsx):
    print("======point selection strategy======")
    # read coverage json
    uncov_db = {}
    with open(uncovd_json, 'r') as fj:
        uncov_db = json.load(fj)

    # read instance list
    fanout_info = pd.read_excel(fanout_xlsx)
    moddep_list = []
    for path in fanout_info['hierpath']:
        moddep_list.append(path)

    topbot_list = []
    inst_asc = pd.read_csv(topbot_csv)
    for path in inst_asc['hierpath']:
        topbot_list.append(path)
    
    bottop_list = []
    inst_des = pd.read_csv(bottop_csv)
    for path in inst_des['hierpath']:
        bottop_list.append(path)

    # random
    randsel(uncov_db)

    # maxuncovd
    maxuncovd(uncov_db)

    # moddep, topbot, bottop share the same logic with different instances list
    # use bottop as an example
    strategy = 'bottop'
    moddep_topbot_bottop(strategy, uncov_db, moddep_list, topbot_list, bottop_list)


def main():

    # Purpose: preprocess for different point selection strategies
    # ModDep, TopBot, BotTop
    # input: a module hierarchy file from vcs coverage report
    # output: three rank tables of modules in a DUT for the corresponding three strategies
    preprocess()

    # Purpose: compare rate of fuzzing and formal
    #          determine if it is the time to switch to formal
    # this function will be called when every time thehuzz generated 100 test cases
    # input:
    #       1. rate of fuzzing (rate_fuzz): the number of new covered points in the most recent 100 test cases
    #               divided by time consumption in second
    #       2. selected points history (points_select): points selected for formal with their time consumption in second 
    #               when each time switch to formal. This is used to estimate the rate of formal in average
    # output: if it is the right time to switch to formal
    switch_to_formal = False
    rate_fuzz = 0.01 # cover 0.01 point per sec
    points_select = {"0": 0.5, "1": 0.3, "2": 5, "3": 2.5}
    switch_to_formal = compare_rate(rate_fuzz, points_select)

    # Purpose: identify uncovered points in each module
    # input: a coverage report from thehuzz
    # output: a json file records the uncovd branch points in each module
    #         and the corresponding conditions of covering them.
    iden_uncovd_points()

    # Purpose: Select uncovered points using different strategies for formal
    # Note: make sure all input files are there
    # input:
    #       1.the json file records the uncovd branch points in each module
    #       2.three rank tables of modules
    #       3.the number of uncovd points we want to select (num_point_sel)
    # output: the uncovered points selected by each strategy
    sel_uncovd_point(uncovd_json, topbot_csv, bottop_csv, fanout_xlsx)


if __name__ == "__main__":
    main()