# Author: Chen Chen
# Date: 08/19/2022

import os, subprocess, re
import xml.etree.ElementTree as et
from Config import *


class Instance: 
    def __init__(self, inst_name: str, inst_id: str, inst_pid: str, \
                 mod_name: str, mod_id: str):
        self.inst_name = inst_name
        self.inst_id = inst_id
        self.inst_pid = inst_pid  
        self.hier_path = None # the path to the instance starting from the top instance
        self.hier_path_jg = None
        self.child_hier_paths = [] # the path to all its child instances, this is used to parse the wires of the instance
        self.mod_name = mod_name
        self.mod_id = mod_id
        self.full_path_signals = []
        # each coverage metric should have such two variables
        self.value = {}
        self.tot_cov = {}
        self.tot_covd = {}

        # todo add list for other coverage metrics if necessary
        self.branch_cov = []

        self.num_input = 0
        self.inputs = {}
        self.num_output = 0
        self.outputs = {}
        self.num_register = 0
        self.registers = {}
        self.num_wire = 0
        self.wires = {}


    def __repr__(self):
        return self.hier_path

    def add_value(self, value: str, cov_metric: str):
        self.value[cov_metric] = value
        self.tot_cov[cov_metric] = len(self.value[cov_metric])
        self.tot_covd[cov_metric] = self.value[cov_metric].count('1')

    def add_branch_cov(self, value_seg, entry: et.Element, shape_index_start:int):
        self.branch_cov.append(BranchCovPoints(value_seg, entry, shape_index_start))

    '''
    format of design_info:
    List of inputs: num_inputs (total_size)
    '-'+
    input1 (size)
    input2 (size)
    '''

    def parse_design_info(self, design_info: str):
        with open(design_info, 'r') as f:
            lines = f.readlines()

        lines = iter(lines)
        # nop, input, register, wire
        info = 'nop'
        for line in lines:
            num_info = None
            if 'List of inputs' in line:
                info = 'input'
                num_info = re.search('^List\sof\sinputs:\s(\d+).*$', line)
                if num_info is not None:
                    self.num_input = int(num_info.group(1))
                next(lines)  # skip one line
            elif 'List of registers' in line:
                info = 'register'
                num_info = re.search('^List\sof\sregisters:\s(\d+).*$', line)
                if num_info is not None:
                    self.num_register = int(num_info.group(1))
                next(lines)
            elif 'List of wire' in line:
                info = 'wire'
                num_info = re.search('^List\sof\swire:\s(\d+).*$', line)
                if num_info is not None:
                    self.num_wire = int(num_info.group(1))
                next(lines)
            elif 'List of outputs' in line:
                info = 'output'
                num_info = re.search('^List\sof\soutputs:\s(\d+).*$', line)
                if num_info is not None:
                    self.num_output = int(num_info.group(1))
                next(lines)
            elif '\n' == line:  # parse end
                info = 'nop'
            else:
                if info == 'input':
                    self.parse_input(line)
                elif info == 'register':
                    self.parse_register(line)
                elif info == 'wire':
                    self.parse_wire(line)
                elif info == 'output':
                    self.parse_output(line)
                else:
                    print('parse_design_info: Unknown type')
                    exit()

        assert self.num_input == len(self.inputs), "input num mismatch"
        assert self.num_register == len(self.registers), "reg num mismatch"
        assert self.num_wire == len(self.wires), "wire num mismatch"

    def parse_input(self, line: str):
        input_info = re.search('^(.*)\s\((\d+)\)$', line)
        if input_info is not None:
            sig_name = input_info.group(1)
            if '[' in sig_name and ']' in sig_name:
                sig_name = sig_name.replace('[', '\[')
                sig_name = sig_name.replace(']', '\]')
            sig_size = int(input_info.group(2))
            assert sig_size >= 1, "input size less than 1"
            self.inputs[sig_name] = sig_size

    def parse_output(self, line: str):
        output_info = re.search('^(.*)\s\((\d+)\)$', line)
        if output_info is not None:
            sig_name = output_info.group(1)
            if '[' in sig_name and ']' in sig_name:
                sig_name = sig_name.replace('[', '\[')
                sig_name = sig_name.replace(']', '\]')
            sig_size = int(output_info.group(2))
            assert sig_size >= 1, "output size less than 1"
            self.outputs[sig_name] = sig_size

    def parse_register(self, line: str):
        reg_info = re.search('^(.*)\s\((\d+)\)$', line)
        if reg_info is not None:
            sig_name = reg_info.group(1)
            sig_name = sig_name.replace(self.hier_path + '.', "")
            sig_size = int(reg_info.group(2))
            assert sig_size >= 1, "reg size less than 1"
            self.registers[sig_name] = sig_size

    ## todo check the correct wire && register format, do we need full hier path?
    def parse_wire(self, line: str):
        wire_info = re.search('^(.*)\s\((\d+)\)$', line)
        if wire_info is not None:
            sig_name = wire_info.group(1)
            sig_name = sig_name.replace(self.hier_path + '.', "")
            sig_size = int(wire_info.group(2))
            assert sig_size >= 1, "wire size less than 1"
            self.wires[sig_name] = sig_size

    def print_design_info(self):
        for key in self.inputs.keys():
            print(key, self.inputs[key])

        for key in self.registers.keys():
            print(key, self.registers[key])

        for key in self.wires.keys():
            print(key, self.wires[key])

        print(self.hier_path, self.inst_name, self.inst_id, self.inst_pid, self.module_name, self.mod_id)


# this class is used to record the branch point information of each instance
class BranchCovPoints:
    def __init__(self, value_seg, entry: et.Element, shape_index_start:int):
        self.entry = entry  # branch_shape
        self.value = value_seg[::-1]  # reverse string to follow the id of branch vector
        self.id = entry.attrib['id']
        self.type = entry.attrib['type']
        self.tot_branch = entry.attrib['totalbranches']
        self.skip_annotation = entry.attrib['skip_annotation']
        self.branch_exprs = []
        self.branch_vecs = []
        self.uncovd_indexs = []
        self.shape_index = []
        self.shape_index_start = shape_index_start
    # store branch statements and branch vectors
    def parse_expr(self):
        for expr in self.entry:
            if expr.tag == 'branch_expr':  # if, tenary
                self.branch_exprs.append(BranchExpr(expr))
            elif expr.tag == 'branch_cexpr':  # case
                for citem in expr:
                    if citem.tag == 'branch_citem':
                        self.branch_exprs.append(BranchCExpr(expr, citem))
                    else:
                        print(f'unknown tag, {citem.tag}')
                        exit()

            elif expr.tag == 'branch_vector':
                vec = expr.attrib['vector'][::-1]  # reverse string to follow the index order of branch expr
                self.branch_vecs.append(vec)
                self.shape_index.append(self.shape_index_start+len(self.shape_index))
            else:
                print(f'unknown tag, {self.id}: {expr.tag}')
                exit()

    # find all uncovered vectors
    def find_uncovd_vecs(self):
        has_uncovd = False
        for i, val in enumerate(self.value):
            if val == '0':
                self.uncovd_indexs.append(i)
            
        assert len(self.uncovd_indexs) <= int(self.tot_branch), 'find_uncovd_vecs: the value and index are not paired'
        
        if len(self.uncovd_indexs) > 0:
            has_uncovd = True

        return has_uncovd


    # assume all points except ignored are uncovered
    def find_vecs(self, ignore_shape_ids):
        has_uncovd = False
        for shape_id in self.shape_index:
            if shape_id not in ignore_shape_ids:
                self.uncovd_indexs.append(shape_id-self.shape_index_start)
        # print("ig id: ", ignore_shape_ids)
        # print("shape_index: ", self.shape_index)
        # print("shape start: ", self.shape_index_start)
        # print("uncoved id: ", self.uncovd_indexs)

        assert len(self.uncovd_indexs) <= int(self.tot_branch), 'find_uncovd_vecs: the value and index are not paired'
        
        if len(self.uncovd_indexs) > 0:
            has_uncovd = True

        return has_uncovd


    def gen_conds(self):
        #1 True, 0 false, -1 dont care
        shape_id_list = []
        if len(self.uncovd_indexs) > 0:
            cond_list = []
            for i in self.uncovd_indexs:
                conds = []
                tar_vec = self.branch_vecs[i]
                #print(i, tar_vec)
                for expr in self.branch_exprs:
                    index = int(expr.index) - 1
                    exprstr = expr.exprstr
                    if tar_vec[index] == '1':
                        #if expr.is_case and expr.name == 'default': # let's ignore the default expression when transfer to condition
                        #    print('default of a case statement')
                        #elif expr.is_case:
                        if expr.is_case:
                            item = expr.name
                            conds.append((exprstr, item))
                        else:
                            conds.append((exprstr,1))
                    elif tar_vec[index] == '0':
                        # if case statement is zero, not need to append it to the list
                        if not expr.is_case:
                            # if parent bit on vector is zero, the child exprs can be set as dont-care
                            if self.is_dontcare_expr(expr, tar_vec):
                                t = 1
                                #conds.append((exprstr, -1))
                            else:
                                conds.append((exprstr, 0))
                    #show dont care expr    
                    #elif tar_vec[index] == '-':
                    #    if not expr.is_case:
                    #        conds.append((exprstr, -1))
                shape_id_list.append(i + self.shape_index_start)
                cond_list.append(conds)

            return cond_list, shape_id_list
        else:
            print('Error: no index for uncovd vector')
            exit()

    def gen_point_tree(self, cond_list):
        # create a root node
        root_point = PointsCond([], True)
        for conditions in cond_list:
            root_point.insert(conditions)
        
        # print tree
        #print(root_point)

        return cond_list


    def gen_cond_tree(self, cond_list):
        pass

                
    def is_dontcare_expr(self, child_expr, tar_vec: str):
        # the first branch statement never be dont-care
        if child_expr.index == '1':
            assert child_expr.parent_bit == '0', 'is_dontcare_expr: Special case, parent bit is not zero when index is 1'
            return False
        
        parent_index = child_expr.parent_bit
        p_ind = int(parent_index) - 1

        if tar_vec[p_ind] == '1':
            return False

        return True


    def __repr__(self):
        return f'branch_spec id="{self.id}" type="{self.type}" totalbranches="{self.tot_branch}" skip_annotation="{self.skip_annotation}" value="{self.value}"'

# when convert to SVA property
# Jaspergold will require some specific syntaxes
def add_miss_pkg_refer(expr: str):
    final_expr = expr
    for key in riscv_dict:
        has_vio = re.search(rf'(?<!riscv::){key}', final_expr)
        if has_vio:
            final_expr = final_expr.replace(key, riscv_dict[key])

    return final_expr

# ignore
class CondTree:
    def __init__(self, p_cond, condition, is_root=False):
        self.is_root = is_root
        self.p_cond = p_cond
        self.condition = condition
        self.subtree = []
    def insert(self, p_cond: set, condition: set):
        pass
        # if self.is_root and len(self.subtree) == 0:
        #     self.subtree.append(CondTree(set(),condition, False))
        #     return True

        # is_subtree=False
        # if condition != self.condition: # skip the same condition
        #     if p_cond == self.condition:
                


#ignore
class PointsCond:
    def __init__(self, conditions: list, is_root):
        self.is_root = is_root
        self.conditions = conditions # record the conditions to cover the point
        self.subtree = [] # the points share the same conditions
    def insert(self, conditions:list):
        if self.is_root and len(self.subtree) == 0:
            self.subtree.append(PointsCond(conditions, False))
            return True

        is_subtree=False
        if(all(cond in conditions for cond in self.conditions)): # point is the subpoint
            if len(self.subtree) == 0:
                is_subtree = True
                self.subtree.append(PointsCond(conditions, False))
            else:
                for sub_point in self.subtree:
                    is_subtree = sub_point.insert(conditions)
                    if is_subtree:
                        return True

                if is_subtree == False: # all sub points not share the conditions
                    self.subtree.append(PointsCond(conditions, False))
                    return True

        return is_subtree

    def __repr__(self):
        return f'Cover point: conditions: {self.conditions}; subpoints number: {len(self.subtree)}'

    def __str__(self, level = 0):
        ret = '\t'*level + f'{self.conditions}\n'
        for subnode in self.subtree:
            ret += subnode.__str__(level+1)
        return ret

# record the branch statements of if and ternary (?)
class BranchExpr:
    def __init__(self, entry):
            self.is_case = False
            self.entry = entry
            self.index = entry.attrib['index']
            self.parent_bit = entry.attrib['parent_bit']
            self.exprstr = add_miss_pkg_refer(entry.attrib['exprstr'])

    def __repr__(self):
        return f'branch_expr index="{self.index}" parent_bit="{self.parent_bit}" exprstr="{self.exprstr}"'

# record the branch statements of case statements
class BranchCExpr:
    def __init__(self, case_entry, item_entry):
        self.is_case = True
        self.case_entry = case_entry
        self.item_entry = item_entry
        self.index = item_entry.attrib['index'] # the case and first item will share the same index
        self.name = add_miss_pkg_refer(item_entry.attrib['name'])
        self.parent_bit = case_entry.attrib['parent_bit']
        self.exprstr = add_miss_pkg_refer(case_entry.attrib['exprstr'])

    def __repr__(self):
        return f'branch_expr index="{self.index}" parent_bit="{self.parent_bit}" exprstr="{self.exprstr}"'
