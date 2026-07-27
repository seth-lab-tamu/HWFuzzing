# Author: Chen Chen
# Date: 08/19/2022

top_mod = 'i_ariane' # top instance name
core    = 'cva6' # the name of the benchmark
cov_file_mode = 'all' # the coverage report will contain all information
num_cov_metrics = 5 # number of coverage metrics in use
riscv_dict = {} # this is used to handle some syntax issues, ignore
num_point_sel = 1 # number of point selected for Jaspergold
inst_point_re = '(\d+)_(\d+)' # format of uncovd point