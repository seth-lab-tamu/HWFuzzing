# -*- coding: utf-8 -*-
"""
@author: rahulkande
TODOs: 
    - add option to pause and resume with json files
"""

##################################################
###########  Imports  ############################
##################################################
import subprocess, os, re, pprint, json, jsonlines
from string import Template
import logging as lg # critical, error, warning, info, debug
from tqdm import tqdm
from openpyxl import load_workbook
import copy, statistics, itertools, math
import matplotlib.pyplot as plt
from matplotlib import gridspec
import numpy as np
import pandas as pd

import thehuzz_utils


##################################################
############# utility Functions ##################
##################################################


"""
Cleans one column of data
- Removes nans at the end, checks if any values are missing, removes nans at the end, 
"""
def clean_col_data(data, error_str, max_value_to_plot, data_type=None):

    # remove any trailing nans --> trim data till there is no nan
    nan_indices = np.nonzero(np.isnan(data))[0] # gets all the indices which are nans
    if nan_indices.size > 0: # nans are there
        if nan_indices[0] > 0: data = data[0:nan_indices[0]]
        else: data = np.array([])

    # change the data type if needed
    if data_type: 
        data = data.astype(data_type)

    # check if the data is in ascending order
    assert np.all(data[:-1] <= data[1:]), f"{error_str}: data is not sorted, {data}"

    # trim data based on max value
    data = data[data <= max_value_to_plot]

    return data


"""
Parses given range of cols in sheet 
--> typically used fr seperating prog, time, cov data
- It also cleans the col  data
- Returns ndarray of ndarray
"""
def parse_cols_in_sheet(run_type, ws, data_name, start_row, end_row\
                      , cols_with_data, max_value_to_plot, data_type=False): 

    # first get the cols, transpose bcz data is generated rowise in numpy
    # whereas we want col wise
    data_temp = ws.iloc[start_row:end_row, cols_with_data].to_numpy().T 

    # clean & trim data, change type
    data = np.array( [clean_col_data(col_data, f"in {data_name} of {run_type}", max_value_to_plot, data_type)\
                            for col_data in data_temp] )

    # atleast 1 row of data of this type (prog, time, cov) should be there
    max_no_rows = max([ col_data.size for col_data in data ])
    assert max_no_rows > 0, f"{data_name} data of {run_type} doesnt have even 1 row, {data}"

    max_value = max([ col_data[-1] for col_data in data if col_data.size > 0])

    return data, max_value, max_no_rows


"""
Parses one seet (ie., one run type info) to generate the prog no, time, & cov info
Structure of data: 
    nparray( [exp1 nparray, exp2 nparray, exp3 nparray, exp1 nparray, ...] )
- We use nparray of nparray bcz diff exps will have diff rows of data
- Data is trimmed to min(max prog data & max time data) and all have same size
"""
def parse_sheet_data(run_type, ws, max_progs_to_plot, max_time_to_plot\
                    , no_col_per_exp, col_to_plot):

    # make sure there is atleast 1 row of data to avoid index errors
    assert ws.shape[0] > 0, f"not even 1 row of data is there for {run_type}, {ws.shape}"

    # get the prog data from sheet, trimmed to max prog to plot
    cols_with_prog_data = [0] # only row 0 has prog no data
    prog_data, max_prog_no, max_no_prog_rows = parse_cols_in_sheet(\
                                run_type, ws, 'prog', 0, ws.shape[0]\
                              , cols_with_prog_data, max_progs_to_plot, 'int')

    # get the time data from sheet, trimmed to min(max prog data & max time data)
    cols_with_time_data = np.arange(1, ws.shape[1], no_col_per_exp)
    time_data, max_run_time, max_no_time_rows = parse_cols_in_sheet(\
                                run_type, ws, 'time', 0, max_no_prog_rows\
                              , cols_with_time_data, max_time_to_plot)

    # get the cov data from sheet, trimmed to min(max prog data & max time data)
    cols_with_cov_data = np.arange(1+col_to_plot, ws.shape[1], no_col_per_exp)
    cov_data, max_cov, max_no_cov_rows = parse_cols_in_sheet(\
                                run_type, ws, 'cov', 0, min(max_no_prog_rows, max_no_time_rows)\
                              , cols_with_cov_data, np.Inf, 'int')

    # to ensure prog has same shape as time & cov, modify it
    # note that prog data is 2d array
    prog_data = np.array([ prog_data[0][:covi.size] for covi in cov_data ])

    return prog_data, time_data, cov_data, max_prog_no, max_run_time


"""
Structure of data dict: 
    "run1":  nparray( [exp1 nparray, exp2 nparray, exp3 nparray, exp1 nparray, ...] )
- Data is trimmed to min(max prog data & max time data) and all have same size
"""
def get_data_from_excel(sheet_df, col_to_plot, core, excel_file, runs_to_plot, no_col_per_exp\
                       , max_progs_to_plot, max_time_to_plot):

    # read the input excel sheet, only get the required run types
    # we extract one run at a time since each of them can have diff parameters
    cov_data = {}
    time_data = {}
    prog_data = {}
    max_run_time = 0
    max_prog_no = 0
    for run_type, sheet_details in tqdm(sheet_df.items(), total=sheet_df.shape[1], desc="[       ] ---- reading excel file"):
        if not run_type in runs_to_plot: continue # only get data fr runs required

        # get the data for this run as panda dataframe
        sheet_name = sheet_details['sheet_name'].substitute(core=core)
        ws = pd.read_excel(excel_file, sheet_name=sheet_name, header=0, engine='openpyxl')
        ws = ws.iloc[:,sheet_details["start_col"]-1:] # remove unwanted columns in beginning

        # seperate the data into prog, time, and cov
        prog_data[run_type], time_data[run_type], cov_data[run_type], max_prog_no_i, max_run_time_i\
                = parse_sheet_data(run_type, ws, max_progs_to_plot, max_time_to_plot\
                                 , no_col_per_exp, col_to_plot)

        max_run_time = max(max_run_time, max_run_time_i)
        max_prog_no = max(max_prog_no, max_prog_no_i)

    return prog_data, time_data, cov_data, max_prog_no, max_run_time


"""
Sets the configs for individual subplots
"""
def set_configs(ax, fsize, have_grid, spine_data\
        , x_step, x_min, x_max, x_first_tick\
        , y_step, y_min, y_max, y_first_tick\
        , x_label, y_label, fsize_labels\
        , x_tick_top, y_tick_right\
        , rot, ncl, legend, no_runs, x_tick):

    #print("axis details: ", x_min, x_max, x_step, y_min, y_max, y_step)

    # range to plot
    ax.set_xlim(x_min-1, x_max) # limit x axis range
                            # -1 to make sure it doesnt overlap with axis
    ax.set_ylim(y_min, y_max) # limit y axis range

    # labels on the axis
    if x_label: 
        ax.set_xlabel(x_label, fontsize=fsize_labels)
    if y_label: 
        ax.set_ylabel(y_label, fontsize=fsize_labels)

    # tick marks on the axis
    if x_tick_top:  # this is top graph, so ticks on top
        ax.xaxis.tick_top()
    ax.tick_params(length=fsize/4, labeltop=False) # length of ticks, no need of labels fr top ticks
    x_axis_ticks = [str(int(i/x_tick)) for i in range(x_first_tick, x_max, x_step)]
    ax.set_xticks(np.arange(x_first_tick, x_max, x_step)) # positions of x ticks
    ax.set_xticklabels(x_axis_ticks, fontsize=fsize) # labels fr each y-axis ticks
    if y_tick_right: # this is right graph, so, ticks on right
        ax.yaxis.tick_right()
    ax.tick_params(length=fsize/4, labelright=False) # no need of labels fr right ticks
    y_axis_ticks = [str(i) for i in range(y_first_tick, y_max, y_step)]
    ax.set_yticks(np.arange(y_first_tick, y_max, y_step)) # positions of y ticks
    ax.set_yticklabels(y_axis_ticks, fontsize=fsize) # labels fr each y-axis ticks

    # grid for the plot
    if have_grid: 
        ax.grid()
        #ax.grid(which='major', axis='y', color='r', linestyle=(0,(1,10)), linewidth='2') 
    
    # border lines for the plot
    ax.spines['top'].set_visible(spine_data["top"]) # set the boundary of the figure
    ax.spines['bottom'].set_visible(spine_data["bottom"])
    ax.spines['right'].set_visible(spine_data["right"])
    ax.spines['left'].set_visible(spine_data["left"])

    # legend related
    #ax.legend(fontsize=fsize, ncol=ncl, frameon=False, bbox_to_anchor=(xl, yl)) 
    if legend: # TODO: fix label size
        leg = ax.legend(fontsize=fsize_labels-10, ncol=ncl, frameon=False, loc='lower right', labelspacing=0.3) 
        for line in leg.get_lines():
            line.set_linewidth(3)
        
        for i in range(no_runs):
            leg.legendHandles[i]._legmarker.set_markersize(25)
    else:
        t = 1 #leg = ax.legend(fontsize=fsize_labels, ncol=ncl, frameon=False, loc='lower right', ) 

    # misc
    ax.margins(x=0)
    #set_box_color(bp1, '#D7191C')


"""
Sets the config for the one full subplot fr generic details like 
axis labels. Kind of like a dummy plot
"""
def set_configs_full(axs_full, x_label, y_label, fsize, fsize_labels): 
    axs_full.set_xlabel(x_label, fontsize=fsize_labels)
    axs_full.set_ylabel(y_label, fontsize=fsize_labels)
    axs_full.tick_params(labelcolor='w', top=False, bottom=False, left=False, right=False, length=fsize/4)
    axs_full.set_yticklabels([100], fontsize=fsize) # this is so that axes label leaves space for the 
                                                    # ticks of the subplots
    axs_full.set_xticklabels([100], fontsize=fsize)
    axs_full.spines['top'].set_color('none')
    axs_full.spines['bottom'].set_color('none')
    axs_full.spines['left'].set_color('none')
    axs_full.spines['right'].set_color('none')
    axs_full.grid(False)


"""
For each experiment in the run, converts the data that is mapped to prog num
to data per time_step
"""
def convert_per_prog_to_per_time_in_exp(cov_data, time_data, time_step):
    new_cov_data = []
    curr_time = 0 # time in minutes
    # assign data per prog according to minutes
    for time_i, cov_data_i in zip(time_data, cov_data): 
        # check to make sure that the data is valid
        if time_i == None: break
        # time will be converted to min and roofed bcz data covered in 2.4 min 
        # means it is covered in 3 min, not 2 min
        prog_time_step = math.ceil(time_i/time_step)
        if curr_time > prog_time_step: # we already have data fr this min
                                # overwrite with new data fr this min
            new_cov_data[prog_time_step] = cov_data_i 
        else: # use old data fr missing minutes
            while not (curr_time == prog_time_step): 
                if len(new_cov_data)>0: new_cov_data.append(new_cov_data[-1])
                else: new_cov_data.append(0) # we start with 0 coverage
                curr_time += 1
            new_cov_data.append(cov_data_i)
            curr_time += 1

    return np.array(new_cov_data)


"""
Converts the data converted in per prog to per time_step
"""
def convert_per_prog_to_per_time(cov_data, time_data, time_step): 
    new_cov_data = {}
    for run_type, run_cov_data in cov_data.items(): 
        new_cov_data[run_type] = [ convert_per_prog_to_per_time_in_exp(exp_cov_data, exp_time_data, time_step)\
            for exp_cov_data, exp_time_data in zip(run_cov_data, time_data[run_type]) ]

    max_run_time = max([len(exp_new_cov_data) for run_new_cov_data in new_cov_data.values()\
                                     for exp_new_cov_data in run_new_cov_data])

    return new_cov_data, max_run_time

"""
Diff exps can be having diff prog nos for corresponding data. This function rearranges the 
data so that each data entry is for one prog_step
"""
def convert_data_to_per_prog_in_exp(exp_cov_data, exp_prog_data, prog_step):

    # handle the case when no data is there
    if exp_cov_data.size == 0: return exp_cov_data

    no_progs_in_exp = exp_prog_data[-1] + 1 # + 1 bcz prog no starts with 0
    exp_cov_data_per_prog = np.empty(no_progs_in_exp, dtype='int') # first create empty array

    # fr each prog no, if cov data is there use that value, else use the past 
    # cov value
    for start_prog_no, end_prog_no, cov_data_i\
                    in zip(exp_prog_data[:-1], exp_prog_data[1:], exp_cov_data):
        exp_cov_data_per_prog[start_prog_no:end_prog_no] = cov_data_i
    
    exp_cov_data_per_prog[-1] = exp_cov_data[-1]

    # now create a new list with the step size needed
    exp_cov_data_per_step = exp_cov_data_per_prog[::prog_step]

    return exp_cov_data_per_step

"""
"""
def convert_data_to_per_prog(cov_data, prog_data, prog_step):
    # get the new data for all runs
    new_cov_data = { run_type: \
            np.array( [convert_data_to_per_prog_in_exp(exp_cov_data, exp_prog_data, prog_step)\
                for exp_cov_data, exp_prog_data in zip(run_cov_data, prog_data[run_type])] ) \
                    for run_type, run_cov_data in cov_data.items() \
            }
    
    return new_cov_data 


"""
Set the values for prog no 0 to 0 so that we get the (0,0) point in the graph
"""
def set_first_value(prog_data, time_data, cov_data):
    # we only change data if prog no 0 is there
    for run_type, prog_data_run in prog_data.items():
        for exp_i, prog_exp_data in enumerate(prog_data_run): 
            # handle the case when no data is there
            if prog_exp_data.size == 0: continue

            # we only need to check 1st row of each exp data as that is where prog
            # no 0 can be present
            if prog_exp_data[0] == 0: 
                if time_data[run_type][exp_i].size > 0:
                    time_data[run_type][exp_i][0] = 0 # set time to 0
                cov_data[run_type][exp_i][0] = 0 # set cov to 0

    return prog_data, time_data, cov_data


"""
Coverts the data into percentage using the total no of cov points as input
data format: 
    data = { "thehuzz": [ np list of data for exp1, np list of data for exp2, ... ],
             "random":  [ np list of data for exp1, np list of data for exp2, ... ]   }
"""
def convert_data_to_percentage(data, tot_data):
    for run_type, run_data in tqdm(data.items(), desc="[       ] ---- converting run type data to percentage"):

        data[run_type] = [(exp_data/tot_data)*100 for exp_data in run_data]
    return data


"""
Converts the data that is in the form of array of experiments to 
arrays of rows. 
Note that amount of data in each experiment may not be same
input data =  [ [list of data for exp1], [list of data for exp2], ... ]
output data = [ [list of cov values fr prog0 fr all exps], [list of cov values fr prog1 fr all exps], ... ] 
"""
def convert_data_to_row_data(run_data): 
    # transpose run_data and remove any elements with None value
    run_data_row = np.array([ np.array([cov_value for cov_value in prog_data if cov_value != None])\
                        for prog_data in itertools.zip_longest(*run_data, fillvalue=None) ])
    return run_data_row


"""
Gets the mean and variance data
"""
def get_statistical_data(data, prog_step, time_step, graph_time_prog):
    mean_data = {}
    mean_time = {}
    mean_prog = {}
    sd_data = {}
    for run_type, run_data in data.items():
        # note that the data is in form of arrays of experiments
        # need to convert this into array of rows first
        run_data_row = convert_data_to_row_data(run_data)
        for row_data in run_data_row:
            assert len(row_data) > 0, f"row data has no data {run_type}, {row_data}"
        mean_data[run_type] = np.array([ np.mean(row_data) for row_data in run_data_row ])
        sd_data[run_type] = np.array([ statistics.pstdev(row_data) for row_data in run_data_row ])

        # time/prog data will be time/prog step respectively
        mean_time[run_type] = np.arange(mean_data[run_type].size) * time_step
        mean_prog[run_type] = np.arange(mean_data[run_type].size) * prog_step
        mean_x = mean_time if graph_time_prog == 'time' else mean_prog

    return mean_data, sd_data, mean_x


"""
Generates the subplot data needed for a 2x2 broken plot
|------------------------------------------------------|
| 0,0: top left subplot    | 0,1: top right subplot    |
| 1,0: bottom left subplot | 1,1: bottom right subplot | 
|------------------------------------------------------|
"""
def get_subplot_data(**plot_xargs): 
    # spine data: this tells where to keep the boarders fr subplots
    spine_data_t = {pos: False for pos in ["top", "bottom", "left", "right"]}
    spine_data = [[copy.deepcopy(spine_data_t), copy.deepcopy(spine_data_t)]\
                  , [copy.deepcopy(spine_data_t), copy.deepcopy(spine_data_t)]]
 
    spine_data[0][0]["left"] = True # top left
    spine_data[1][0]["left"] = True # bottom left
    spine_data[0][0]["top"] = True # left top 
    spine_data[0][1]["top"] = True # right top 
    spine_data[0][1]["right"] = True # top right 
    spine_data[1][1]["right"] = True # bottom right 
    spine_data[1][0]["bottom"] = True # left bottom 
    spine_data[1][1]["bottom"] = True # right bottom 

    # x ranges
    x_min = [ [plot_xargs["x_ranges"][0], plot_xargs["x_ranges"][3]]\
            , [plot_xargs["x_ranges"][0], plot_xargs["x_ranges"][3]] ]
    x_max = [ [plot_xargs["x_ranges"][1], plot_xargs["x_ranges"][4]]\
            , [plot_xargs["x_ranges"][1], plot_xargs["x_ranges"][4]] ]
    x_step = [ [plot_xargs["x_ranges"][2], plot_xargs["x_ranges"][5]]\
            , [plot_xargs["x_ranges"][2], plot_xargs["x_ranges"][5]] ]
    x_first_tick = [ [plot_xargs["x_ranges"][0], plot_xargs["x_ranges"][6]]\
            , [plot_xargs["x_ranges"][0], plot_xargs["x_ranges"][6]] ]
    y_min = [ [plot_xargs["y_ranges"][3], plot_xargs["y_ranges"][3]]\
            , [plot_xargs["y_ranges"][0], plot_xargs["y_ranges"][0]] ]
    y_max = [ [plot_xargs["y_ranges"][4], plot_xargs["y_ranges"][4]]\
            , [plot_xargs["y_ranges"][1], plot_xargs["y_ranges"][1]] ]
    y_step = [ [plot_xargs["y_ranges"][5], plot_xargs["y_ranges"][5]]\
            , [plot_xargs["y_ranges"][2], plot_xargs["y_ranges"][2]] ]
    y_first_tick = [ [plot_xargs["y_ranges"][6], plot_xargs["y_ranges"][6]]\
            , [plot_xargs["y_ranges"][0], plot_xargs["y_ranges"][0]] ]

    # legend will be on bottom right subplot
    legend = [ [False, False]\
             , [False, plot_xargs["legend"]] ]

    # x ticks will be on top for top subplots, 
    # y ticks will be on right for right subplots
    x_tick_top = [[True, True], [False, False]]
    y_tick_right = [[False, True], [False, True]]

    # dash positions
    dash_pos = {}
    d = plot_xargs["slash_width"]
    # 0,0 subplot: at (0,0) & (1,1) 
    xd = plot_xargs["width_ratio"][1]
    yd = plot_xargs["height_ratio"][1]
    #print(d, xd, yd, d*xd, d*yd)
    dash_pos["0_0"] = [ [(0-d*xd, 0+d*xd), (0-d*yd, 0+d*yd)]\
                      , [(1-d*xd, 1+d*xd), (1-d*yd, 1+d*yd)] ]

    # 0,1 subplot: at (0,1) & (1,0) 
    xd = plot_xargs["width_ratio"][0]
    yd = plot_xargs["height_ratio"][1]
    dash_pos["0_1"] = [ [(0-d*xd, 0+d*xd), (1-d*yd, 1+d*yd)]\
                      , [(1-d*xd, 1+d*xd), (0-d*yd, 0+d*yd)] ]

    # 1,0 subplot: at (0,1) & (1,0) 
    xd = plot_xargs["width_ratio"][1]
    yd = plot_xargs["height_ratio"][0]
    dash_pos["1_0"] = [ [(0-d*xd, 0+d*xd), (1-d*yd, 1+d*yd)]\
                      , [(1-d*xd, 1+d*xd), (0-d*yd, 0+d*yd)] ]

    # 1,1 subplot: at (0,0) & (1,1) 
    xd = plot_xargs["width_ratio"][0]
    yd = plot_xargs["height_ratio"][0]
    dash_pos["1_1"] = [ [(0-d*xd, 0+d*xd), (0-d*yd, 0+d*yd)]\
                      , [(1-d*xd, 1+d*xd), (1-d*yd, 1+d*yd)] ]

    return spine_data, x_min, x_max, x_step, x_first_tick, x_tick_top\
            , y_min, y_max, y_step, y_first_tick, y_tick_right, legend, dash_pos

"""
Plots the data as a 4x graph
"""
def plot_time_vs_cov_plot_4x(sheet_df, mean_x, mean_cov_data\
                , sd_cov_data, graph_time_prog, x_tick, **plot_xargs):
    no_runs = len(mean_cov_data)
    g_fsize = plot_xargs["g_fsize"]
    g_fsize_labels = plot_xargs["g_fsize_labels"]

    # get all the parameters required to plot the subplots
    spine_data, x_min, x_max, x_step, x_first_tick, x_tick_top, y_min, y_max, y_step, y_first_tick, y_tick_right, legend, dash_pos\
                = get_subplot_data(**plot_xargs)

    # spec is to facilitate diff sized subplots
    spec = gridspec.GridSpec(ncols=2, nrows=2, \
            width_ratios=plot_xargs["width_ratio"], wspace=plot_xargs["wspace"]\
            , hspace=plot_xargs["hspace"], height_ratios=plot_xargs["height_ratio"])
    
    # create 1 full dummy plot and 4 subplots
    fig = plt.figure(figsize=(g_fsize/2,(g_fsize/2)*0.6))
    axs_full = fig.add_subplot(111) # 1 plot, 1 row,  1 col?
    axs = [[0,0], [0,0]]
    axs[0][0] = fig.add_subplot(spec[0])
    axs[0][1] = fig.add_subplot(spec[1])
    axs[1][0] = fig.add_subplot(spec[2])
    axs[1][1] = fig.add_subplot(spec[3])

    # plot same data on all 4 subplots
    # ax_i and ax_j will be the coordinates of the subplots
    for ax_i, ax_js in enumerate(axs):
        for ax_j, ax in enumerate(ax_js):
            # plot data on this subplot
            for run_type, run_mean_cov_data in mean_cov_data.items():
                sheet_details = sheet_df[run_type]
                
                # plotting the mean data
                ax.plot(mean_x[run_type], mean_cov_data[run_type], label=sheet_details['name_in_legend'] \
                    , color=sheet_details['line_color'], marker=sheet_details['marker'], markersize=sheet_details['marker_size']\
                    , markevery=sheet_details['marke'], linewidth=sheet_details['line_width'])
                # plotting the variance data: shade the plot from mean-variance to mean+variance
                ax.fill_between(mean_x[run_type], \
                                mean_cov_data[run_type] - sd_cov_data[run_type], \
                                mean_cov_data[run_type] + sd_cov_data[run_type], \
                                alpha=0.4,color=sheet_details['box_color'])  # range of shaded region = mean - variance to mean + variance
            # set the configuration for the sublpots
            set_configs(ax, g_fsize, plot_xargs["have_grid"], spine_data[ax_i][ax_j]\
                            , x_step[ax_i][ax_j], x_min[ax_i][ax_j], x_max[ax_i][ax_j], x_first_tick[ax_i][ax_j]\
                            , y_step[ax_i][ax_j], y_min[ax_i][ax_j], y_max[ax_i][ax_j], y_first_tick[ax_i][ax_j]\
                            , None, None, g_fsize_labels\
                            , x_tick_top[ax_i][ax_j], y_tick_right[ax_i][ax_j]\
                            , 0, plot_xargs["legend_ncol"], legend[ax_i][ax_j], no_runs, x_tick)

    # set configuration for the 1 dummy plot
    set_configs_full(axs_full, plot_xargs["x_label"], plot_xargs["y_label"], g_fsize, g_fsize_labels)

    # set the two dashes: 
    # we need 8 dashes, each subplot has 2 dashes
    kwargs = dict(transform=axs[0][0].transAxes, color='k', clip_on=False, linewidth=2.0)
    axs[0][0].plot(dash_pos["0_0"][0][0], dash_pos["0_0"][0][1], **kwargs)  
    axs[0][0].plot(dash_pos["0_0"][1][0], dash_pos["0_0"][1][1], **kwargs)

    kwargs.update(transform=axs[0][1].transAxes)
    axs[0][1].plot(dash_pos["0_1"][0][0], dash_pos["0_1"][0][1], **kwargs)  
    axs[0][1].plot(dash_pos["0_1"][1][0], dash_pos["0_1"][1][1], **kwargs)

    kwargs.update(transform=axs[1][0].transAxes)
    axs[1][0].plot(dash_pos["1_0"][0][0], dash_pos["1_0"][0][1], **kwargs)  
    axs[1][0].plot(dash_pos["1_0"][1][0], dash_pos["1_0"][1][1], **kwargs)

    kwargs.update(transform=axs[1][1].transAxes)
    axs[1][1].plot(dash_pos["1_1"][0][0], dash_pos["1_1"][0][1], **kwargs)  
    axs[1][1].plot(dash_pos["1_1"][1][0], dash_pos["1_1"][1][1], **kwargs)

    #fig.tight_layout()

    # set horizontal line for maximal value
    # max_thehuzz = 0
    # max_formal_huzz = 0
    # for run_type in sheet_dict:
    #     if run_type == 'thehuzz_cva6_mar_22':
    #         max_thehuzz = max(mean_data[run_type])
    #     max_cov = max(mean_data[run_type])
    #     if max_cov > max_formal_huzz:
    #         max_formal_huzz = max_cov

    # plt.axhline(y=max_thehuzz, color='r', linestyle='--', linewidth=2.0)
    # plt.axhline(y=max_formal_huzz, color='r', linestyle='--', linewidth=2.0)

    plt.savefig(plot_xargs["plot_file_name"],bbox_inches='tight')
    t=1


"""
Extracts the prog no, time, and cov data from the cov file generated by fuzzer
cov file is a jsonlines file with one program data per line as dict
"""
def get_exp_data_from_cov_file(cov_file):

    with jsonlines.open(cov_file, 'r') as fp: cov_data = list(fp)
    assert len(cov_data) > 0, f"No cov data found in {cov_file}"

    # get the prog no data
    prog_data = np.array([ i['id'] for i in cov_data ], dtype='int')

    # get the time data
    assert 'time' in cov_data[0].keys(), f"time data not found in cov data, {cov_data[0]},\n{cov_file}"
    time_data = np.array([ i['time'] for i in cov_data ])

    # get the cov_data

    #   create a nparray of cov_data
    cov_data_np = np.array([ list(i['tot'].values()) for i in cov_data ]).T

    cov_types_present = list(cov_data[0]['tot'].keys())
    cov_data = { cov_type: cov_data_np[i].astype('int') for i, cov_type in enumerate(cov_types_present) }

    #   add tot cov if not present
    if not 'total' in cov_types_present: 
        cov_data['total'] = np.sum(cov_data_np, axis=0)

    return prog_data, time_data, cov_data


"""
This function updates the excel sheet data with the exp data from cov log file
Excel sheet data is in the form of dicts & nparrays
"""
def update_excel_sheet_data_with_exp_data(excel_sheet_data, sheet_exp_name\
        , prog_data, time_data, cov_data, all_cov_types): 

    # update the prog data for the sheet/run
    excel_prog_data = excel_sheet_data['prog_no']
    common_size = min(excel_prog_data.size, prog_data.size)
    assert np.array_equal(excel_prog_data[:common_size], prog_data[:common_size])\
           , f"in {sheet_exp_name}, existing prog no not matching with new, {excel_prog_data}, {prog_data}" 

    if prog_data.size > excel_prog_data.size:
        excel_sheet_data['prog_no'] = prog_data # prog data doesnt need panda series as it has 
                                                # highest no of cols

    # update time data of exp, make it series with index, otherwise dataframe
    # complains if all cols dont have same size
    excel_sheet_data[f'{sheet_exp_name}_time'] = pd.Series(time_data, index=np.arange(time_data.size))

    # update cov data of exp
    for cov_type in all_cov_types: # Note: make sure to follow this order as it will be used when reading from excel
        if cov_type in cov_data.keys():
            excel_sheet_data[f'{sheet_exp_name}_{cov_type}'] \
                    = pd.Series(cov_data[cov_type], index=np.arange(cov_data[cov_type].size))
        else: 
            excel_sheet_data[f'{sheet_exp_name}_{cov_type}'] = pd.Series([], index=[])

    return excel_sheet_data


##################################################
##############  depreciated code  ################
##################################################
# if 0: 
#     # handle the case where there no data
#     if len(cov_file) == 0: 
#         print(f"WARNING: No data found in {cov_file}")
#         prog_data = np.array([], dtype='int')
#         time_data = np.array([], dtype='float')
#         cov_data = {}

#         return prog_data, time_data, cov_data



#     no_exps_in_sheet = int(  (len(excel_sheet_data)-1) / (1+len(all_cov_types))  )
#             # -1 to remove prog no col, +1 to include time col
#     exp_name_in_sheet = f"{sheet_exp_name}_{no_exps_in_sheet}"

#     cols_to_use = [i for i in range( sheet_details["start_col"]-1, sheet_details["end_col"]+1 )]
#             # -1 bcz we want prog no col, +1 to cover the last col


    #else: 
    #    data = np.array([]) # if no data, then it should be empty
    #non_nan_indices = np.nonzero(~np.isnan(data))[0] # get indices which are not nans
    #if non_nan_indices.size > 0: # there could be cases where there is no data 
    #    data = data[non_nan_indices[0]: non_nan_indices[-1]+1]
    #else: 
    #    data = np.array([]) # if no data, then it should be empty

    # check if there are any missing values
    nan_indices = np.nonzero(np.isnan(data))[0] # gets all the indices which are nans
    assert nan_indices.size == 0, f"{error_str} missing data cells, {nan_indices}, {data}"

    # unless it is time
    #if not data_name == 'time': 

    # TODO: handle this when time data is not there
    ## make sure that time and cov data have same no of rows fr each exp
    #assert not False in [timei.size == covi.size for timei, covi in zip(time_data, cov_data)]\
    #        , f"time and cov have diff no of rows in {run_type}, {[timei.size == covi.size for timei, covi in zip(time_data, cov_data)]}"

    # to ensure prog has same shape as time & cov, modify it
    # note that prog data is 2d array
    prog_data = np.array([ prog_data[0][:covi.size] for covi in cov_data ])

    # TODO deal with the case when max time to plot reduces cols compared to max
    # progs to plot
    # check that max run time to plot dint result in less rows than max progs to plot
    print(prog_data, time_data, cov_data)
    col_sizes = [i.size for i in np.append(prog_data, time_data, cov_data, axis=0)]
    assert [col_sizes[0]]*len(col_sizes) == col_sizes, f"col sizes are not matching {col_sizes} for {run_type}"

    cols_with_prog_data = [0]*int((ws.shape[1]-1)/no_col_per_exp) # use first col fr all prog data


    #    no_exps = len(run_cov_data)
    #    run_time_data = time_data[run_type]

    #    # get the new data fr all experiments in this run
    #    new_cov_data[run_type] = [[] for i in range(no_exps)] 
    #    for exp_i in range(no_exps): 
    #        # get the data for all time steps in this experiment
    #        new_cov_data[run_type][exp_i] = \
    #                convert_per_prog_to_per_min_in_exp(\
    #                    run_cov_data[exp_i], run_time_data[exp_i])
        #new_dict = {"step": cov_data}
        #thehuzz_utils.update_json_file('cov_data.json' , new_dict)


    #    new_dict = {"%": cov_data}
    #    thehuzz_utils.update_json_file( 'cov_data.json' , {f'{k}%':[di.tolist() for di in d] for k,d in cov_data.items()} )
        #new_dict = {f"{run_type}_row": run_data_row, f"{run_type}_col": run_data}
        #thehuzz_utils.update_json_file('cov_data.json' , new_dict)
    #new_dict = {"mean": mean_cov_data, "sd": sd_cov_data}
    #thehuzz_utils.update_json_file('cov_data.json' , new_dict)