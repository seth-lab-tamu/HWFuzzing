# -*- coding: utf-8 -*-
"""
@author: rahulkande
Notes: 
    - The script makes the following assumptions abt the structure of the excel
      sheet columns
      - 1st col of each experiment will be time
      - Time col will be followed by cov cols using titles same as ones in all_cov_types from
        config
      - All experiments should have same no of cols as mentioned in
        no_col_per_exp in config
      - one col before the range specified in sheet dict will have prog no col
      - program number should definitely be there for all runs
      - if time info is there, then cov info has to be there
      - if prog no is there, there should be atleast one exp data

TODOs: 
    - add option to pause and resume with json files
    - when converting data to per prog, it is assumed that prog no starts from
      0 --> make this generalized
    - Change data types to Int64 so that nan becomes <NA> when merging sheets??
"""

##################################################
###########  Imports  ############################
##################################################
import subprocess, os, re, pprint, json
import logging as lg # critical, error, warning, info, debug
from string import Template
from tqdm import tqdm
import numpy as np
import pandas as pd

import config
from configManager import getCONFIG
import thehuzz_utils, plot_graphs_utils as PU


##################################################
###########  Global variables  ###################
##################################################
sheet_indices = [\
         "sheet_name"      # name of the sheet for the run in the excel file
       , "start_col"       # column number from which the data started
       , "end_col"         # end column number till which the data is present (not used)
       , "line_color"      # line color in the plot
       , "line_width"      # line width in the plot
       , "marker"          # marker type in the plot
       , "marker_size"     # size of the marker in the plot
       , "marke"           # how frequently should we put the marker in the plot
       , "name_in_legend"  # name for the run the plot
       , "box_color"       # color of the variance box
   ]
sheet_dict = {
    'thehuzz': [Template("thehuzz_$core"),      1, 29, '#e41a1c', 2.0, '>', 25, 50, 'TheHuzz', "#e41a1c"]\
  , 'random' : [Template("random_$core"),       1, 29, '#377eb8', 2.0, '<', 25, 50, 'Random Regression',  "#377eb8"]\
}
sheet_df = pd.DataFrame(sheet_dict, index=sheet_indices) # pandas dataframe with sheet information

    
##################################################
################# Functions ######################
##################################################


"""
Generates the time vs coverage % graph
"""
def gen_prog_vs_cov_plot(excel_xargs, cov_type_to_plot\
                          , all_cov_types, prog_step, time_step\
                          , ref_cov_dict_file, graph_time_prog\
                          , in_percent, graph_prog_tick, graph_time_tick, plot_xargs):

    col_to_plot = all_cov_types.index(cov_type_to_plot) + 1 # +1 bcz col 0 is time data

    prog_data, time_data, cov_data, max_prog_no, max_run_time = \
                PU.get_data_from_excel(sheet_df, col_to_plot, *excel_xargs)
  
    print(f"[       ] ---- max_run_time={max_run_time}, max_prog_no={max_prog_no}")
    #print(prog_data, '\n\n', time_data, '\n\n', cov_data); exit()

    # get the data after every minute/prog based on if we want prog graph or time graph
    if graph_time_prog == 'time': 
        cov_data, max_run_time = PU.convert_per_prog_to_per_time(cov_data, time_data, time_step)
        print(f"[       ] ---- syncing data from all the runs and exps with common time done, max time = {max_run_time}")
    elif graph_time_prog == 'prog':  # this step syncs data from all runs with common progs
        print(f"-- syncing data from all the runs and exps with common prog")
        cov_data = PU.convert_data_to_per_prog(cov_data, prog_data, prog_step)
        print(f"-- syncing data from all the runs and exps with common prog done")


    ## do any preprocessing if needed TODO: this needs to be done only for prog data and before converting to time data
    ## set values of 0 prog to 0 so that the plot starts at 0,0
    #print("-- setting the prog 0 value to 0")
    #prog_data, time_data, cov_data = PU.set_first_value(prog_data, time_data, cov_data)
    #print("-- setting the prog 0 value to 0 done")

    # convert data to percent if needed
    if in_percent: 
        print(f"[       ] ---- converting data to percentage")
        # get the no of points of the cov type we want to plot
        with open(ref_cov_dict_file, 'r') as fp: ref_cov_data = json.load(fp)
        if cov_type_to_plot == 'total':  # add no of cov points of all types
            no_cov_points = sum([len(cov_type_list) for cov_type_list in ref_cov_data.values()])
        else: 
            no_cov_points = len(ref_cov_data[cov_type_to_plot])
        print(f"[       ] ---- total no of '{cov_type_to_plot}' type cov points = {no_cov_points}")

        cov_data = PU.convert_data_to_percentage(cov_data, no_cov_points)

    # get the statistical data
    print("[       ] ---- computing the statistical data")
    mean_cov_data, sd_cov_data, mean_x\
            = PU.get_statistical_data(cov_data, prog_step, time_step, graph_time_prog)

    # plot the data
    print("[       ] ---- plotting the graph")
    x_tick = graph_prog_tick if graph_time_prog == 'prog' else graph_time_tick
    PU.plot_time_vs_cov_plot_4x(sheet_df, mean_x, mean_cov_data\
                , sd_cov_data, graph_time_prog, x_tick, **plot_xargs)


"""
All the data will be saved as dicts & nparrays first, and then merged with excel data 
in the form of pandas dataframes so that we can write to excel sheet
"""
def update_excel_file(cov_files, all_cov_types, excel_file): 

    # parse the cov files one by one to a dict. each cov file is basically from one experiment
    excel_data = {}
    for sheet_exp_name, cov_file_details in tqdm(cov_files.items(), desc="[       ] ---- parsing cov files"): 

        prog_data, time_data, cov_data = PU.get_exp_data_from_cov_file(cov_file_details['filename'])
        #print(prog_data, time_data), print('-'*80); print(cov_data); exit()

        # update the local dict with this exp data
        sheet_name = cov_file_details['sheet_name']
        if not sheet_name in excel_data.keys():
            excel_data[sheet_name] = {'prog_no':np.array([], dtype='int')} 

        excel_data[sheet_name] = PU.update_excel_sheet_data_with_exp_data(\
                            excel_data[sheet_name], sheet_exp_name\
                          , prog_data, time_data, cov_data, all_cov_types)
        #print(excel_data[sheet_name]); exit()


    # get the data from excel sheet and merge the new data into it
    if os.path.exists(excel_file):
        subprocess.call([ 'cp', excel_file, f"{excel_file}_copy"] )
        wb = pd.read_excel(excel_file, sheet_name=None, header=0, index_col=0, engine='openpyxl')
    else: 
        wb = {}

    for sheet_name, new_sheet_data in tqdm(excel_data.items(), desc="[       ] ---- updating excel sheets"):

        sheet_data_df = pd.DataFrame(new_sheet_data)  # convert sheet_data to df
        sheet_data_df = sheet_data_df.set_index('prog_no') # set 
                            # index after creating dataframe as random will have
                            # diff index for prog no and cov data

        if not sheet_name in wb.keys(): # create a new sheet
            wb[sheet_name] = sheet_data_df

        else: # need to merge if sheet is there
            ws = wb[sheet_name] # this is dataframe

            # check if the prog no col is same
            n = min(sheet_data_df.index.size, ws.index.size)
            assert np.array_equal(sheet_data_df.index[:n], ws.index[:n])\
                , f"in {sheet_name}, existing prog no not matching with new, {sheet_data_df.index}, {ws.index}" 

            # delete cols in excel that are also in new data
            delete_cols = set(ws.keys()) & set(sheet_data_df.keys())
            ws = ws if delete_cols == set() else ws.drop(columns=delete_cols)

            # merge sheet
            if sheet_data_df.index.size < ws.index.size: 
                wb[sheet_name] = ws.join(sheet_data_df)
            else: 
                wb[sheet_name] = sheet_data_df.join(ws)

    # update excel sheet
    with pd.ExcelWriter(excel_file, engine='openpyxl', mode='w') as ep:
        for sheet_name, sheet_data in wb.items(): sheet_data.to_excel(ep, sheet_name) 


"""
Main function to call the functions in the flow
"""
def main(prog_time): 

    # set debug level
    debug_level = lg.DEBUG if CONFIG.debug_print else lg.INFO 
    lg.basicConfig(filename="my.log", filemode='w', level=debug_level)

    ##################################################
    ######## Gen prog vs coverage % 4x plot  #########
    ##################################################

    cov_files_dict = {
        #'bb_nick_0': ["bb_nick_0.txt", "bb_nick"]
        'bb_nick_1': ["bb_nick_1.txt", "bb_nick"]
            }
    cov_files_df = pd.DataFrame(cov_files_dict, index=['filename', 'sheet_name'])

    x_ranges = [0, 1201, 1000, 5000, 30001, 10000, 10000]  # no progs
                        # start of range1, stop of range1, step range1, start
                        # range2, stop range2, step range2, first tick for 2
    y_ranges = [0, 62, 20, 62, 71, 5, 65] # this y value is in percentage
                        # start of range1, stop of range1, step range1, start
                        # range2, stop range2, step range2, first tick for 2
    y_label = "% H/W points covered"
    x_label = "# programs (xK)"

    # g_fsize is used for font in plot
    # g_fsize_labels is font size for labels
    # width ratio and height ratio are subplot sizes
    # slash width will depend on width ratio and height ratio (the ones that connect breaks)
    #               --> need to set this manually to have correct slope for slashes
    # legend ncol is no of columns in which legend data should be
    plot_xargs = dict(legend=True, x_ranges=x_ranges\
                    , y_ranges=y_ranges, x_label=x_label\
                    , y_label=y_label, plot_file_name=CONFIG.pt['graph_plot_file']\
                    , g_fsize=50, g_fsize_labels=60, width_ratio=[1,2], height_ratio=[2,1]\
                    , wspace=0.05, hspace=0.05, slash_width=0.02\
                    , have_grid=True, legend_ncol=1)

    excel_xargs = dict(excel_file=CONFIG.pt['graph_excel_file']\
                     , runs_to_plot=CONFIG.runs_to_plot\
                     , no_col_per_exp=CONFIG.no_col_per_exp\
                     , max_progs_to_plot=CONFIG.graph_max_progs_to_plot\
                     , max_time_to_plot=CONFIG.graph_max_time_to_plot\
                     , skip_rows=CONFIG.graph_skip_rows)

    if CONFIG.graph_4x_plot: 
        print("Generating the 4x prog vs cov plot") 
        gen_prog_vs_cov_4x_plot(excel_xargs, CONFIG.cov_type_to_plot\
                    , CONFIG.all_cov_types, CONFIG.graph_prog_step\
                    , CONFIG.pt['graph_ref_cov_dict_file'], CONFIG.graph_time_prog\
                    , CONFIG.graph_in_percent, CONFIG.graph_prog_tick\
                    , CONFIG.graph_time_tick, plot_xargs)
        print("Generating the 4x prog vs cov plot done") 

    ##################################################
    ############## Update the excel sheet ############
    ##################################################

    if CONFIG.graph_update_excel_file: 
        print("Updating the excel file with cov data")
        update_excel_file(cov_files_df\
                        , CONFIG.pt['graph_cov_files_dir']\
                        , CONFIG.all_cov_types\
                        , CONFIG.pt['graph_excel_file'])
        print("Updating the excel file with cov data done")



if __name__ == '__main__':

    # custom time object
    prog_time = thehuzz_utils.Mytime()

    # get variables from config file or dict, and update any present in args
    CONFIG = getCONFIG(config, configType='file')
    
    #main(prog_time)



##################################################
##############  depreciated code  ################
##################################################


    #thehuzz_utils.update_json_file( 'cov_data.json' , {k:[di.tolist() for di in d] for k,d in cov_data.items()} )

#        with pd.ExcelWriter(excel_file, engine='openpyxl', mode='w') as ep: # create excel sheet
#            pd.DataFrame({}).to_excel(ep)
