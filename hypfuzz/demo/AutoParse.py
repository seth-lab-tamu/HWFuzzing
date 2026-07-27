# Author: Chen Chen
# Date: 08/19/2022

import xml.etree.ElementTree as et
from parse_pkg import *


def build_hier_path(inst, hier_path: str, inst_db: dict):
    
    if hier_path == '':
        hier_path = inst.inst_name
    else:
        hier_path = inst.inst_name + '.' + hier_path

    # reach the top instance
    if inst.inst_pid == '-1':
        return hier_path

    if inst.inst_pid in inst_db:
        p_inst = inst_db[inst.inst_pid]
        return build_hier_path(p_inst, hier_path, inst_db)
    else:
        print("parse_file: can not find the parent instance")
        exit()


def parse_design(file: str, inst_db: dict):
    """
    srcdef: module info
        chksum? unknown
    srclocmult: location of rtl source code
        file_id: the id of source file, can be found in dve_debug.xml or verilog.sourceinfor.xml
    srcinst: instance info,
        pid: the inst_id of its parent instance
    
    <srcdef id="-54"  name="decoder"  type="module"  chksum="997376648"  >
        <srclocmult file_id="1"  start="7140"  end="8266"  />
        <srcinst id="-136"  name="decoder_i"  pid="-967"  >
            <srcloc file_id="1"  lines="7140"  />
        </srcinst>
    </srcdef>
    """

    tree = et.parse(file)
    root = tree.getroot()

    for i, child in enumerate(root):
        if child.tag == 'srcdef' and child.attrib['type'] == 'module':
            mod_name = child.attrib['name']
            mod_id   = child.attrib['id']
            for j, subchild in enumerate(child):
                if subchild.tag == 'srcinst':
                    inst_name = subchild.attrib['name']
                    inst_id   = subchild.attrib['id']
                    inst_pid  = subchild.attrib['pid']
                    
                    if inst_id in inst_db:
                        print("parse_design: duplicate inst_id")
                        exit()

                    inst = Instance(inst_name, inst_id, inst_pid, mod_name, mod_id)
                    inst_db[inst_id] = inst


    return inst_db


def rm_nonrelated_insts(inst_db):
    # remove instances higher than top mod of processor
    print("number of instances of the entire SoC environment: ", len(inst_db))
    inst_to_rm = []
    for inst_id in inst_db:
        if top_mod not in inst_db[inst_id].hier_path:
            inst_to_rm.append(inst_id)

    for inst_id in inst_to_rm:
        remove_id = inst_db.pop(inst_id, None)
        if remove_id == None:
            print("rm_nonrelated_insts: no such id to remove ", inst_id)
            exit()

    print("number of instaces belong to the DUT: ", len(inst_db))

    return inst_db


def parse_all_cov_file(design_xml: str):
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

    # record the hier. path to child instances
    for child_inst in inst_db.values():
        pid = child_inst.inst_pid
        if pid != "-1" and pid not in inst_db:
            print("parse_cov_file: parent instance not in the database")
            exit()
        elif pid != "-1": # the top instance will have pid as -1
            inst_db[pid].child_hier_paths.append(child_inst.hier_path)

    return inst_db


def parse_cov(file: str, cov_metric: str, inst_db: dict):
    tree = et.parse(file)
    root = tree.getroot()

    for i, child in enumerate(root):
        if child.tag == 'instance_data':
            name = child.attrib['name']
            found_inst = False
            
            for inst in inst_db.values():
                if inst.hier_path == name:
                    found_inst = True
                    inst.add_value(child.attrib['value'], cov_metric)
                    break

            if found_inst == False:
                print("parse_cov: can not find the instance: ", name)
                exit()


    return inst_db


def parse_cov_file(design_xml: str, data_xml: str):
    inst_list = []
    inst_db = {} # use to check if an instance object already exist
    tot_cov = {'branch': 0, 'cond': 0, 'fsm': 0, 'line': 0, 'tgl': 0}
    tot_covd = {'branch': 0, 'cond': 0, 'fsm': 0, 'line': 0, 'tgl': 0}
    tot_cov_bins = {}

    if cov_file_mode == 'all':
        inst_db = parse_all_cov_file(design_xml) # this requires the vdb file
        # record coverage of instances using hier. path
        file_list = os.listdir(data_xml)
        num_file = 0
        if os.path.isdir(data_xml) and len(file_list) != 0:
            for i, file in enumerate(file_list):
                match = re.search('^(.*)\.verilog\.data\.xml$', file)
                if match:
                    num_file += 1
                    cov_metric = match.group(1)
                    cov_file_path = os.path.join(data_xml, file)
                    inst_db = parse_cov(cov_file_path, cov_metric, inst_db)
        else:
            print("parse_file: file or file path are not correct")

        assert num_file == num_cov_metrics, 'num of cov files mismatch after uncompress'
    else:
        print('parse_cov_file: unknow cov_file_mode')
        exit()

    # remove instances not belonging to the processor
    for inst in inst_db.values():
        if top_mod in inst.hier_path:
            # change child hier. path to start from the top mod
            for i, child_path in enumerate(inst.child_hier_paths):
                if top_mod in child_path:
                    # for rocket chip, some instances have child instances that aren't in the top module
                    # example: ['TestDriver.testHarness.chiptop.system.tile_prci_domain.intsink_2']
                    t = child_path.split(top_mod + '.')
                    if len(t) == 1:
                        continue
                    inst.child_hier_paths[i] = t[1]
                else:
                    print("parse_file: top module is not in the child path")
                    exit()
            inst_list.append(inst)
            for key in inst.value:
                tot_cov[key] += inst.tot_cov[key]
                tot_covd[key] += inst.tot_covd[key]

    return inst_list, tot_cov, tot_covd


def find_cov_point(inst, cov_metric: str, cov_rep_path: str):
    if cov_file_mode == 'all':
        shape_file = os.path.join(cov_rep_path, f'{cov_metric}.verilog.shape.xml')
    
    if not os.path.exists(shape_file):
        print('find_cov_point: file not exist')
        exit()

    cov_points = None
    if cov_metric == 'branch':
        cov_points, shape_id_list = find_branch_point(inst, shape_file)

    return cov_points, shape_id_list


def find_branch_point(inst, file):

    # parse branch.verilog.shape.xml
    inst = parse_branch_shape(inst, file)
    has_uncovd = False
    cov_points = []
    shape_id_list = []
    #1. identify the expressions for each point
    #2. if the point require the expressions of another point to be true
    # the point is a child point.
    for branch in inst.branch_cov:
        #print(branch)
        branch.parse_expr()
        has_uncovd = branch.find_uncovd_vecs()
        #print(branch.uncovd_indexs)
        if has_uncovd:
            cond_list, shape_id_list_per_branch_shape = branch.gen_conds()
            cov_points.append(cond_list)
            for shape_id in shape_id_list_per_branch_shape:
                shape_id_list.append(shape_id)

    return cov_points, shape_id_list


def parse_branch_shape(inst, file):

    '''
        in branch.verilog.shape.xml
        will separate all branch statements in a module into different group
        <branch_def  id="-94"  chksum="1194118711"  >
            <branch_shape  >
              <branch_spec  id="0"  type="1"  totalbranches="2"  width="1"  file_id="1"  skip_annotation="0"  chksum="2948608310"  >
              </branch_spec >
              <branch_spec  id="1"  type="0"  totalbranches="11"  width="7"  file_id="1"  skip_annotation="0"  chksum="2242667394"  >
              </branch_spec >
              <branch_spec  id="2"  type="0"  totalbranches="2"  width="1"  file_id="1"  skip_annotation="0"  chksum="3993370529"  >
              </branch_spec >
              <branch_spec  id="3"  type="0"  totalbranches="13"  width="10"  file_id="1"  skip_annotation="0"  chksum="1487321717"  >
              </branch_spec >
              <branch_spec  id="4"  type="0"  totalbranches="2"  width="1"  file_id="1"  skip_annotation="0"  chksum="1510987558"  >
              </branch_spec >
            </branch_shape >
        </branch_def >

    type: not sure
    skip_annotation: not seen in cva6
    '''

    tree = et.parse(file)
    root = tree.getroot()
    has_correct_inst = False
    for i, mod in enumerate(root):
        if mod.tag == 'branch_def' and mod.attrib['id'] == inst.mod_id:
            has_correct_inst = False
            only_one_inst = True
            # check if the module creates the correct instance
            for k, item in enumerate(mod):
                if item.tag == 'branch_inst':
                    only_one_inst = False
                    #print("instance id ", inst.inst_id)
                    #print("item attrib ", item.attrib['id'])
                    if item.attrib['id'] == inst.inst_id:
                        has_correct_inst = True
                        break

            if has_correct_inst == False and only_one_inst == False:
                continue
            elif only_one_inst == True:
                has_correct_inst = True

            #print("has correct inst ", has_correct_inst)
            #print("only one instance ", only_one_inst)
            shape = mod.find('branch_shape')
            branch_num = 0
            for j, branch in enumerate(shape):
                # value segment from top to bot, right (if) to left (else),
                # 1: covered, 0: uncovered
                # e.g., i_mmu. value = 10(0) 10000000000(1) 10(2) 1000000000000(3) 11(4)
                if branch.tag == 'branch_spec':
                    tot_branch = int(branch.attrib['totalbranches'])
                    value_seg = inst.value['branch'][branch_num:(branch_num + tot_branch)]
                    inst.add_branch_cov(value_seg, branch, branch_num)
                    branch_num += tot_branch
                else:
                    print(f'mod has other branch tag, mod id {inst.mod_id}')
                    exit()
            #print(branch_num)
            #print(inst.tot_cov['branch'])
            assert branch_num == inst.tot_cov['branch'], "parse_branch_shape:branch num mismatch"
            
            break

    assert has_correct_inst==True, "parse_branch_shape: did not find such instance from the module"

    return inst