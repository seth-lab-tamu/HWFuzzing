import os
from string import Template


#############
# VARIABLES #
#############

core_name       = ""
ready           = True
core_full_name  = ""
isa = "perif"
kernel = ""
input_format = "perif"
soc_name = 'opn'
opn_perifs = [f"{soc_name}_{i}" for i in ["aes0", "aes1", "aes2", "acct", "dbg", "dma", "hmac", "reglk", "rng", "rsa", "rst", "sha256"]]
soc_address_width = 12


# general
top_module = ""
top_instance_name = ""
top_instance = ""
tb_module = ""
bind_module = ""
bind_instance_name = ""
bind_instance = ""
soc_sanitizer_bind_module = ""
soc_sanitizer_base_path = ""
soc_sanitizer_signal_map = {}

input_format_info = []
fsm_init_value_info = {}
ignore_fsms = {}
params_info = {}

num_clocks_in_input = 1000
max_sim_cycles = num_clocks_in_input + 1000
clock_period = "2ns"
time_fr_1_cycle = 2000
tot_sim_time = max_sim_cycles * time_fr_1_cycle

pt = {}

clk_substrings = ['clk', 'clock']
rst_substrings = ['rst', 'reset']
tb_clk_signal = 'clk_i' 
tb_rst_signal = 'rst_ni' 
debug_enable_signal = ""
one_time_regs = []
one_time_output_interfaces = []

def refresh(core_name_i): 
    global core_name, bind_instance, top_instance, top_module\
     , tb_module, bind_module, bind_instance_name, top_instance_name\
         , input_format_info, fsm_init_value_info, params_info, pt\
         , ignore_fsms, debug_enable_signal, one_time_regs, one_time_output_interfaces\
         , soc_sanitizer_bind_module, soc_sanitizer_base_path, soc_sanitizer_signal_map
    
    core_name  = core_name_i
    tb_module = f"{core_name}_tb"
    bind_module = f"{core_name}_v_dut"
    bind_instance_name = "i_bind_dut"
    bind_instance = f"{tb_module}.{bind_instance_name}"
    if core_name in opn_perifs: top_module = f"{core_name[4:]}_wrapper"
    soc_prefix = "cmp_top.system.chipset.chipset_impl.i_riscv_peripherals"
    soc_sanitizer_bind_module = top_module
    soc_sanitizer_base_path = f"{soc_prefix}.i_{core_name[4:]}_wrapper"
    if core_name == "opn_dbg":
      soc_sanitizer_bind_module = "riscv_peripherals"
      soc_sanitizer_base_path = soc_prefix
    soc_sanitizer_signal_map = {
        f"{tb_module}.debug_mode_i": f"{soc_prefix}.debug_mode_i",
    }
    top_instance_name = "perif_u"
    top_instance = f"{tb_module}.{top_instance_name}"
    debug_enable_signal = f"!{top_instance}.i_dm_top.dmactive_o" if core_name == "opn_dbg" else f"{tb_module}.debug_mode_i"
    one_time_regs = []
    one_time_output_interfaces = []


    params_info = [{'name': 'AXI_ADDR_WIDTH', 'type': 'int unsigned', 'value': 64 }]
    params_info.append({'name': 'AXI_DATA_WIDTH', 'type': 'int unsigned', 'value': 64 })
    params_info.append({'name': 'AXI_ID_WIDTH', 'type': 'int unsigned', 'value': 1 })
    if core_name in "opn_rsa": params_info.append({'name': 'MAX_PRIME_WIDTH', 'type': 'int unsigned', 'value': 1024 })
    if core_name in "opn_rsa": params_info.append({'name': 'USER_PRIME_WIDTH', 'type': 'int unsigned', 'value': 32 })


    one_time_targets = {
        'opn_aes0': 'ct',
        'opn_aes1': 'core_result',
        'opn_aes2': 'ct',
        'opn_hmac': 'hash',
        'opn_rsa': 'msg_out',
        'opn_sha256': 'hash',
    }
    if core_name in one_time_targets:
        one_time_regs.append(f"{top_instance_name}.{one_time_targets[core_name]}")

    input_format_info = [{'name': 'clk_i', 'nbits': 1, 'type': 'clk'}]
    input_format_info.append({'name': 'rst_ni', 'nbits': 1, 'type': 'rst', 'edge': 'negedge'})
    input_format_info.append({'name': 'en_acct', 'nbits': 1, 'type': 'gen', 'soc_role': 'chip_select'})
    input_format_info.append({'name': 'we', 'nbits': 1, 'type': 'gen', 'soc_role': 'write_enable'})
    input_format_info.append({'name': 'address', 'nbits': 64, 'type': 'gen', 'soc_role': 'address'})
    input_format_info.append({'name': 'wdata', 'nbits': 64, 'type': 'gen', 'soc_role': 'write_data'})
    input_format_info.append({'name': 'rdata', 'nbits': 64, 'type': 'out'})

    if core_name in ["opn_acct", "opn_dma"]: input_format_info.append({'name':'we_flag', 'nbits':1, 'type': 'gen'})
    if core_name in ['opn_acct']: input_format_info.append({'name':'acc_ctrl_o', 'nbits':36, 'type': 'out', 'value': "1'b0"})
    if core_name in ["opn_dbg"]: input_format_info.append({'name':'slave_be_i', 'nbits':8, 'type': 'gen'})
    if core_name in ["opn_dbg"]: input_format_info.append({'name':'priv_lvl_i', 'nbits':4, 'type': 'gen'})
    if core_name in ["opn_dbg"]: 
      for s in ['jtag_hash_i','ikey_hash_i','okey_hash_i']: input_format_info.append({'name':s, 'nbits':256, 'type': 'gen'}) 
    if core_name in ["opn_dbg"]: 
      for s in ['we_flag_4_i', 'tck_i', 'tms_i', 'td_i']: input_format_info.append({'name':s, 'nbits':1, 'type': 'gen'}) 
      for s in ['trst_ni']: input_format_info.append({'name':s, 'nbits':1, 'type': 'gen', 'edge': 'negedge'}) 
    if core_name in ["opn_dbg"]: 
      for s in ['td_o', 'tdo_oe_o']: input_format_info.append({'name':s, 'nbits':1, 'type': 'out'}) 
    if core_name in ["opn_dma"]: input_format_info.append({'name':'pmp_data_allow_i', 'nbits':1, 'type': 'gen'})
    if core_name in ["opn_dma"]: 
      for s in ['pmp_addr_o']: input_format_info.append({'name':s, 'nbits':64, 'type': 'out'})
      for s in ['pmp_access_type_o']: input_format_info.append({'name':s, 'nbits':3, 'type': 'out'})
    if core_name in ["opn_reglk"]: input_format_info.append({'name':'jtag_unlock', 'nbits':1, 'type': 'gen'})
    if core_name in ["opn_reglk"]: input_format_info.append({'name':'reglk_ctrl_o', 'nbits':112, 'type': 'out'})

    cores_1 = ['opn_aes0', 'opn_aes1', 'opn_aes2', 'opn_hmac', 'opn_rng', 'opn_rsa', 'opn_rst']
    cores_2 = ['opn_acct','opn_dma','opn_reglk','opn_sha256']
    if core_name in cores_1+cores_2: input_format_info.append({'name':'reglk_ctrl_i', 'nbits':8, 'type': 'gen', 'value': "8'b0"})
    if core_name in cores_1+cores_2: input_format_info.append({'name':'acct_ctrl_i', 'nbits':1, 'type': 'gen', 'value': "1'b1"})
    if core_name in cores_1: input_format_info.append({'name':'debug_mode_i', 'nbits':1, 'type': 'gen', 'value': "1'b0"})
    if core_name in cores_2: input_format_info.append({'name':'debug_mode_i', 'nbits':1, 'type': 'gen', 'value': "1'b0"})
    rst_signal = {'opn_aes0': 'rst_1', 'opn_aes1': 'rst_2', 'opn_sha256': 'rst_3', 'opn_aes2': 'rst_11', 'opn_acct': 'rst_6', 'opn_dma': 'rst_8', 'opn_hmac': 'rst_4', 'opn_reglk': 'rst_9', 'opn_rng': 'rst_10', 'opn_rsa': 'rst_13'}
    if core_name in rst_signal.keys(): 
        input_format_info.append({'name': rst_signal[core_name], 'nbits':1, 'type': 'gen', 'value': "1'b0", 'edge': 'posedge'})
    if core_name in ["opn_rst"]: 
      for s in list(rst_signal.values())+['rst_5','rst_7']:input_format_info.append({'name':s, 'nbits':1, 'type': 'out'})

    one_time_output_interfaces.append({
        'port': 'rdata[31:0]',
        'valid': f'{tb_module}.en_acct && !{tb_module}.we',
    })

    ### fsm init value info
    # no need to provide this if pyverilog can get the init value
    for c in opn_perifs: fsm_init_value_info[c] = {}
    for c in opn_perifs: ignore_fsms[c] = []
    fsm_init_value_info['opn_dbg'] = {'opn_dbg_tb.perif_u.i_dmi_jtag.i_dmi_jtag_tap.tap_state_q': 'opn_dbg_tb.perif_u.i_dmi_jtag.i_dmi_jtag_tap.RunTestIdle'\
                                 , 'opn_dbg_tb.perif_u.i_dm_top.i_dm_csrs.cmderr_q':"3'h0"\
                                 , 'opn_dbg_tb.perif_u.i_dm_top.i_dm_mem.state_q': 'opn_dbg_tb.perif_u.i_dm_top.i_dm_mem.Idle'\
                                 , 'opn_dbg_tb.perif_u.i_dmi_jtag.state_q': 'opn_dbg_tb.perif_u.i_dmi_jtag.Idle' }
    fsm_init_value_info['opn_rsa'] = {'opn_rsa_tb.perif_u.rsa0.i.state': "3'd1"\
                                    , 'opn_rsa_tb.perif_u.rsa0.m.state': "2'd1"}

    ####inferred paths
    core_sim_path = os.path.join(os.environ['IPFUZZ_ROOT'], f'sim/{core_name}')
    pt["sim_dir_t"] = Template(f"{core_sim_path}/vcs_${{tno}}")
    pt["core_dram_path"] = "None"
    
    pt["fuzzer_input_format"]   = 'csv'
    pt["sim_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/RUN.log")
    pt["trace_out_path_t"] = None
    pt["cov_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/{core_name}/rel-0.1/simv.vdb")
    
    pt["vdb_test_dir"] = "snps/coverage/db/testdata/cm_data/"
    pt["vdb_ext_test_dir"] = "snps/coverage/db/testdata/test_ext/"

    pt["verilog_design_file_path"] =  Template(f"{pt['cov_out_path_t'].template}/snps/coverage/db/design/verilog.design.xml")
    pt["verilog_source_info_file_path"] =  Template(f"{pt['cov_out_path_t'].template}/snps/coverage/db/auxiliary/verilog.sourceinfo.xml")
    pt["fsm_verilog_shape_file_path"] =  Template(f"{pt['cov_out_path_t'].template}/snps/coverage/db/shape/fsm.verilog.shape.xml")
    pt["verilog_instance_parameters_file_path"] =  Template(f"{pt['cov_out_path_t'].template}/snps/coverage/db/auxiliary/verilog.instance_parameters.txt")

    pt["soc_dir"] = os.path.join(os.environ['IPFUZZ_ROOT'], f"benchmarks/opn")
    pt["perif_dir"] = os.path.join(os.environ['IPFUZZ_ROOT'], f"benchmarks/{core_name}")
    pt["perif_sim_dir"] = os.path.join(pt['perif_dir'], f"sim")
    pt["perif_jg_tcl_file"] = os.path.join(pt['perif_sim_dir'], f"jg.tcl")
    pt["perif_jg_tcl_log_file"] = os.path.join(pt['perif_sim_dir'], f"jg.txt")
    pt["sanitizers_sva_file_path"] = os.path.join(pt['perif_dir'], f"tb/sanitizers.sva")
    pt["soc_sanitizers_sva_file_path"] = os.path.join(
        os.environ['IPFUZZ_ROOT'], f"benchmarks/opnAsn/tb/sanitizers_{core_name}.sva")

    pt["tb_file_path"] = os.path.join(os.environ['IPFUZZ_ROOT'], f"benchmarks/{core_name}/tb/tb.sv")
    pt["tb_1_file_path"] = os.path.join(pt["soc_dir"], f"tb_1.sv")
    pt["tb_2_file_path"] = os.path.join(pt["soc_dir"], f"tb_2.sv")
    pt["tb_3_file_path"] = os.path.join(pt["soc_dir"], f"tb_3.sv")

