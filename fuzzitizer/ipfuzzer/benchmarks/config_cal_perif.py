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
soc_name = 'cal'
cal_perifs = ["cal_csrng", "cal_doe", "cal_dv", "cal_ecc", "cal_entropy_src", "cal_hmac", "cal_kv", "cal_pv", "cal_spi_host", "cal_sha256", "cal_sha512", "cal_uart"]

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
soc_sanitizer_bind_signal_map = {}

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
soc_address_width = 0

def refresh(core_name_i): 
    global core_name, bind_instance, top_instance, top_module\
     , tb_module, bind_module, bind_instance_name, top_instance_name\
         , input_format_info, fsm_init_value_info, params_info, pt\
         , ignore_fsms, debug_enable_signal, one_time_regs, one_time_output_interfaces
    global soc_address_width, soc_sanitizer_bind_module, soc_sanitizer_base_path
    global soc_sanitizer_signal_map, soc_sanitizer_bind_signal_map
    
    core_name  = core_name_i
    tb_module = f"{core_name}_tb"
    bind_module = f"{core_name}_v_dut"
    bind_instance_name = "i_bind_dut"
    bind_instance = f"{tb_module}.{bind_instance_name}"
    if   core_name in ["cal_sha512","cal_sha256", "cal_doe", "cal_hmac"]: top_module = f"{core_name[4:]}_ctrl"
    elif core_name in ["cal_ecc"]: top_module = f"{core_name[4:]}_top"
    elif core_name in ["cal_kv", "cal_pv", "cal_dv", "cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"]: top_module = f"{core_name[4:]}"
    else:  assert False, f"unknown core {core_name} found"

    soc_prefix = "caliptra_top_tb.caliptra_top_dut"
    soc_instances = {
        "cal_csrng": "csrng",
        "cal_doe": "doe",
        "cal_dv": "data_vault1",
        "cal_ecc": "ecc_top1",
        "cal_entropy_src": "entropy_src",
        "cal_hmac": "hmac",
        "cal_kv": "key_vault1",
        "cal_pv": "pcr_vault1",
        "cal_spi_host": "spi_host",
        "cal_sha256": "sha256",
        "cal_sha512": "sha512",
        "cal_uart": "uart",
    }
    soc_reset_ports = {
        "cal_csrng": "rst_ni",
        "cal_doe": "reset_n",
        "cal_dv": "rst_b",
        "cal_ecc": "reset_n",
        "cal_entropy_src": "rst_ni",
        "cal_hmac": "reset_n",
        "cal_kv": "rst_b",
        "cal_pv": "rst_b",
        "cal_spi_host": "rst_ni",
        "cal_sha256": "reset_n",
        "cal_sha512": "reset_n",
        "cal_uart": "rst_ni",
    }
    soc_sanitizer_bind_module = top_module
    soc_sanitizer_base_path = f"{soc_prefix}.{soc_instances[core_name]}"
    soc_reset_port = soc_reset_ports[core_name]
    soc_clock_port = "clk_i" if core_name in [
        "cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"
    ] else "clk"
    soc_sanitizer_bind_signal_map = {"rst_ni": soc_reset_port}
    soc_sanitizer_signal_map = {
        f"{tb_module}.rst_ni": f"`BASE_PATH.{soc_reset_port}",
        f"{tb_module}.clk_i": f"`BASE_PATH.{soc_clock_port}",
        f"{tb_module}.cs": "`BASE_PATH.hsel_i",
        f"{tb_module}.we": "`BASE_PATH.hwrite_i",
        f"{tb_module}.read_data": "`BASE_PATH.hrdata_o",
        f"{tb_module}.kv_write": "`BASE_PATH.kv_write",
        f"{tb_module}.debugUnlock_or_scan_mode_switch":
            "`BASE_PATH.debugUnlock_or_scan_mode_switch",
        f"{tb_module}.lc_hw_debug_en_i": "`BASE_PATH.lc_hw_debug_en_i",
        f"{tb_module}.debug_mode_i":
            f"{soc_prefix}.debug_lock_or_scan_mode_switch",
    }
    top_instance_name = "perif_u"
    top_instance = f"{tb_module}.{top_instance_name}"
    one_time_regs = []
    one_time_output_interfaces = []

    if core_name in ["cal_doe", "cal_ecc", "cal_hmac", "cal_kv", "cal_sha256", "cal_sha512"]:
        debug_enable_signal = f"{tb_module}.debugUnlock_or_scan_mode_switch"
    elif core_name == "cal_csrng":
        debug_enable_signal = f"lc_ctrl_pkg::lc_tx_test_true_strict({tb_module}.lc_hw_debug_en_i)"
    else:
        debug_enable_signal = f"{tb_module}.debug_mode_i"


    params_info = []
    if core_name in ["cal_sha512","cal_sha256", "cal_doe", "cal_ecc"]: ahb_addr_width = 15
    if core_name in ["cal_hmac", "cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"]: ahb_addr_width = 12
    if core_name in ["cal_kv", "cal_pv", "cal_dv"]: ahb_addr_width = 13
    ahb_data_width = 64
    client_data_width = 32

    if core_name in ["cal_sha512","cal_sha256", "cal_doe", "cal_hmac", "cal_ecc", "cal_kv", "cal_pv", "cal_dv"]: params_info.append({'name': 'AHB_ADDR_WIDTH', 'type': 'int unsigned', 'value': ahb_addr_width })
    if core_name in ["cal_sha512","cal_sha256", "cal_doe", "cal_hmac", "cal_ecc", "cal_kv", "cal_pv", "cal_dv"]: params_info.append({'name': 'AHB_DATA_WIDTH', 'type': 'int unsigned', 'value': ahb_data_width })
    if core_name in ["cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"]: params_info.append({'name': 'AHBAddrWidth', 'type': 'int unsigned', 'value': ahb_addr_width })
    if core_name in ["cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"]: params_info.append({'name': 'AHBDataWidth', 'type': 'int unsigned', 'value': ahb_data_width })
    soc_address_width = ahb_addr_width

    one_time_targets = {
        'cal_doe': ['doe_inst.kv_result_reg'],
        'cal_ecc': [
            'ecc_dsa_ctrl_i.pubkeyx_reg',
            'ecc_dsa_ctrl_i.pubkeyy_reg',
            'ecc_dsa_ctrl_i.r_reg',
            'ecc_dsa_ctrl_i.s_reg',
        ],
        'cal_hmac': ['hmac_inst.tag_reg'],
        'cal_sha256': ['sha256_inst.digest_reg'],
        'cal_sha512': ['sha512_inst.digest_reg'],
    }
    one_time_regs = [
        f"{top_instance_name}.{target}"
        for target in one_time_targets.get(core_name, [])
    ]

    if core_name in ["cal_doe", "cal_dv", "cal_ecc", "cal_hmac", "cal_kv", "cal_pv", "cal_sha256", "cal_sha512"]: input_format_info = [{'name': 'clk', 'nbits': 1, 'type': 'clk'}]
    if core_name in ["cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"]: input_format_info = [{'name': 'clk_i', 'nbits': 1, 'type': 'clk'}]
    if core_name in ["cal_doe", "cal_ecc", "cal_hmac", "cal_sha256", "cal_sha512"]: input_format_info.append({'name': 'reset_n', 'nbits': 1, 'type': 'rst', 'edge': 'negedge'})
    if core_name in ["cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"]: input_format_info.append({'name': 'rst_ni', 'nbits': 1, 'type': 'rst', 'edge': 'negedge'})
    if core_name in ["cal_kv", "cal_pv", "cal_dv"]: input_format_info.append({'name': 'rst_b', 'nbits': 1, 'type': 'rst', 'edge': 'negedge'})

    if core_name in cal_perifs: input_format_info.append({'name':'cs', 'nbits':1, 'type': 'gen', 'soc_role': 'chip_select'})
    if core_name in cal_perifs: input_format_info.append({'name':'we', 'nbits':1, 'type': 'gen', 'soc_role': 'write_enable'})
    if core_name in cal_perifs: input_format_info.append({'name':'address', 'nbits':ahb_addr_width, 'type': 'gen', 'soc_role': 'address'})
    if core_name in cal_perifs: input_format_info.append({'name':'write_data', 'nbits':client_data_width, 'type': 'gen', 'soc_role': 'write_data'})
    if core_name in cal_perifs: input_format_info.append({'name':'read_data', 'nbits':client_data_width, 'type': 'out'})

    if core_name in ["cal_doe", "cal_dv", "cal_ecc", "cal_hmac", "cal_kv", "cal_pv", "cal_sha256", "cal_sha512"]: input_format_info.append({'name':'cptra_pwrgood', 'nbits':1, 'type': 'gen', 'value': "1'b1"})

    if core_name in ["cal_ecc","cal_hmac"]: input_format_info.append({'name':'kv_read', 'nbits':18, 'type': 'out', 'value': "'0"})
    if core_name in ["cal_sha512"]: input_format_info.append({'name':'kv_read', 'nbits':9, 'type': 'out', 'value': "'0"})
    if core_name in ["cal_doe","cal_sha512", "cal_hmac","cal_ecc"]: input_format_info.append({'name':'kv_write', 'nbits':47, 'type': 'out'})
    if core_name in ["cal_kv"]: input_format_info.append({'name':'kv_read', 'nbits':45, 'type': 'gen', 'value': "'0"})
    if core_name in ["cal_kv"]: input_format_info.append({'name':'kv_write', 'nbits':188, 'type': 'gen'})
    if core_name in ["cal_hmac","cal_ecc"]: input_format_info.append({'name':'kv_rd_resp', 'nbits':68, 'type': 'gen' , 'value': "'0"})
    if core_name in ["cal_sha512"]: input_format_info.append({'name':'kv_rd_resp', 'nbits':34, 'type': 'gen' , 'value': "'0"})
    if core_name in ["cal_doe","cal_sha512","cal_hmac","cal_ecc"]: input_format_info.append({'name':'kv_wr_resp', 'nbits':1, 'type': 'gen' , 'value': "'0"})
    if core_name in ["cal_kv"]: input_format_info.append({'name':'kv_rd_resp', 'nbits':170, 'type': 'out' , 'value': "'0"})
    if core_name in ["cal_kv"]: input_format_info.append({'name':'kv_wr_resp', 'nbits':4, 'type': 'out' , 'value': "'0"})

    if core_name in ["cal_pv"]: input_format_info.append({'name':'pv_read', 'nbits':9, 'type': 'gen', 'value': "'0"})
    if core_name in ["cal_pv"]: input_format_info.append({'name':'pv_write', 'nbits':42, 'type': 'gen'})
    if core_name in ["cal_sha512"]: input_format_info.append({'name':'pv_read', 'nbits':9, 'type': 'out' , 'value': "'0"})
    if core_name in ["cal_sha512"]: input_format_info.append({'name':'pv_write', 'nbits':42, 'type': 'out' , 'value': "'0"})
    if core_name in ["cal_pv"]: input_format_info.append({'name':'pv_rd_resp', 'nbits':34, 'type': 'out' , 'value': "'0"})
    if core_name in ["cal_pv"]: input_format_info.append({'name':'pv_wr_resp', 'nbits':1, 'type': 'out' , 'value': "'0"})
    if core_name in ["cal_sha512"]: input_format_info.append({'name':'pv_rd_resp', 'nbits':34, 'type': 'gen' , 'value': "'0"})
    if core_name in ["cal_sha512"]: input_format_info.append({'name':'pv_wr_resp', 'nbits':1, 'type': 'gen' , 'value': "'0"})

    if core_name in ["cal_doe", "cal_ecc", "cal_hmac", "cal_sha256", "cal_sha512"]: input_format_info.append({'name':'error_intr', 'nbits':1, 'type': 'out' , 'value': ""})
    if core_name in ["cal_doe", "cal_ecc", "cal_hmac", "cal_sha256", "cal_sha512"]: input_format_info.append({'name':'notif_intr', 'nbits':1, 'type': 'out' , 'value': ""})
    if core_name in ["cal_doe", "cal_ecc", "cal_hmac", "cal_sha256", "cal_sha512", "cal_kv"]: input_format_info.append({'name':'debugUnlock_or_scan_mode_switch', 'nbits':1, 'type': 'gen'})
    if core_name in ["cal_dv", "cal_entropy_src", "cal_pv", "cal_spi_host", "cal_uart"]: input_format_info.append({'name':'debug_mode_i', 'nbits':1, 'type': 'gen'})

    if core_name in ["cal_ecc", "cal_kv", "cal_pv", "cal_dv", "cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"]: input_format_info.append({'name':'err', 'nbits':1, 'type': 'out'})
    if core_name in ["cal_kv", "cal_pv", "cal_dv", "cal_csrng", "cal_entropy_src", "cal_spi_host", "cal_uart"]: input_format_info.append({'name':'hold', 'nbits':1, 'type': 'out'})

    if core_name in ["cal_csrng"]: input_format_info.append({'name':'otp_en_csrng_sw_app_read_i', 'nbits':8, 'type': 'gen', 'varType': 'caliptra_prim_mubi_pkg::mubi8_t'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'lc_hw_debug_en_i', 'nbits':4, 'type': 'gen', 'varType': 'lc_ctrl_pkg::lc_tx_t'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'entropy_src_hw_if_o', 'nbits':1, 'type': 'out'})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'entropy_src_hw_if_o', 'nbits':386, 'type': 'out'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'entropy_src_hw_if_i', 'nbits':386, 'type': 'gen'})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'entropy_src_hw_if_i', 'nbits':1, 'type': 'gen'})
    if core_name in ["cal_csrng", "cal_entropy_src"]: input_format_info.append({'name':'cs_aes_halt_i', 'nbits':1, 'type': 'gen'})
    if core_name in ["cal_csrng", "cal_entropy_src"]: input_format_info.append({'name':'cs_aes_halt_o', 'nbits':1, 'type': 'out'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'csrng_cmd_i', 'nbits':68, 'type': 'gen'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'csrng_cmd_o', 'nbits':266, 'type': 'out'})
    if core_name in ["cal_spi_host","cal_uart"]: input_format_info.append({'name':'alert_tx_o', 'nbits':2, 'type': 'out'})
    if core_name in ["cal_entropy_src","cal_csrng"]: input_format_info.append({'name':'alert_tx_o', 'nbits':4, 'type': 'out'})
    if core_name in ["cal_spi_host","cal_uart"]: input_format_info.append({'name':'alert_rx_i', 'nbits':4, 'type': 'gen'})
    if core_name in ["cal_entropy_src","cal_csrng"]: input_format_info.append({'name':'alert_rx_i', 'nbits':8, 'type': 'gen'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'intr_cs_cmd_req_done_o', 'nbits':1, 'type': 'out'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'intr_cs_entropy_req_o',  'nbits':1, 'type': 'out'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'intr_cs_hw_inst_exc_o',  'nbits':1, 'type': 'out'})
    if core_name in ["cal_csrng"]: input_format_info.append({'name':'intr_cs_fatal_err_o',    'nbits':1, 'type': 'out'})

    if core_name in ["cal_doe"]: input_format_info.append({'name':'cptra_obf_key', 'nbits':256, 'type': 'gen'})
    if core_name in ["cal_doe"]: input_format_info.append({'name':'obf_uds_seed', 'nbits':32*12, 'type': 'gen'})
    if core_name in ["cal_doe"]: input_format_info.append({'name':'obf_field_entropy', 'nbits':32*8, 'type': 'gen'})
    if core_name in ["cal_doe"]: input_format_info.append({'name':'clear_obf_secrets', 'nbits':1, 'type': 'out'})

    if core_name in ["cal_dv","cal_pv","cal_kv"]: input_format_info.append({'name':'core_only_rst_b', 'nbits': 1, 'type': 'gen', 'edge': 'negedge'})
    if core_name in ["cal_ecc"]: input_format_info.append({'name':'pcr_signing_data', 'nbits':768, 'type': 'gen' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'otp_en_entropy_src_fw_read_i', 'nbits':8, 'type': 'gen' , 'value': "", 'varType': 'caliptra_prim_mubi_pkg::mubi8_t'})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'otp_en_entropy_src_fw_over_i', 'nbits':8, 'type': 'gen' , 'value': "", 'varType': 'caliptra_prim_mubi_pkg::mubi8_t'})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'entropy_src_rng_o', 'nbits':1, 'type': 'out' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'entropy_src_rng_i', 'nbits':5, 'type': 'gen' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'entropy_src_xht_o', 'nbits':57, 'type': 'out' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'entropy_src_xht_i', 'nbits':35, 'type': 'gen' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'intr_es_entropy_valid_o', 'nbits':1, 'type': 'out' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'intr_es_health_test_failed_o', 'nbits':1, 'type': 'out' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'intr_es_observe_fifo_ready_o', 'nbits':1, 'type': 'out' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'intr_es_fatal_err_o', 'nbits':1, 'type': 'out' , 'value': ""})
    if core_name in ["cal_entropy_src"]: input_format_info.append({'name':'rng_fips_o', 'nbits':1, 'type': 'out' , 'value': ""})

    if core_name in ["cal_pv","cal_kv"]: input_format_info.append({'name':'fw_update_rst_window', 'nbits': 1, 'type': 'gen', 'edge': 'negedge'})
    if core_name in ["cal_kv"]: input_format_info.append({'name': 'cptra_in_debug_scan_mode', 'nbits': 1, 'type': 'gen'})
    if core_name in ["cal_kv"]: input_format_info.append({'name': 'pcr_signing_key', 'nbits': 384, 'type': 'out'})

    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'cio_sck_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'cio_sck_en_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'cio_csb_o', 'nbits': 2, 'type': 'out'})
    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'cio_csb_en_o', 'nbits': 2, 'type': 'out'})
    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'cio_sd_o', 'nbits': 4, 'type': 'out'})
    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'cio_sd_en_o', 'nbits': 4, 'type':'out' })
    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'cio_sd_i', 'nbits': 4, 'type': 'gen'})
    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'intr_error_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_spi_host"]: input_format_info.append({'name': 'intr_spi_event_o', 'nbits': 1, 'type': 'out'})

    if core_name in ["cal_sha512"]: input_format_info.append({'name':'pcr_signing_hash', 'nbits':384, 'type': 'out' , 'value': ""})

    if core_name in ["cal_uart"]: input_format_info.append({'name': 'cio_rx_i', 'nbits': 1, 'type': 'gen'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'cio_tx_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'cio_tx_en_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'intr_tx_watermark_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'intr_rx_watermark_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'intr_tx_empty_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'intr_rx_overflow_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'intr_rx_frame_err_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'intr_rx_break_err_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'intr_rx_timeout_o', 'nbits': 1, 'type': 'out'})
    if core_name in ["cal_uart"]: input_format_info.append({'name': 'intr_rx_parity_err_o', 'nbits': 1, 'type': 'out'})

    one_time_output_interfaces.append({
        'port': 'read_data[31:0]',
        'valid': f'{tb_module}.cs && !{tb_module}.we',
    })
    if any(signal['name'] == 'kv_write' for signal in input_format_info):
        one_time_output_interfaces.append({
            'port': 'kv_write[36:5]',
            'valid': f'{tb_module}.kv_write[46]',
        })


    ### fsm init value info
    # no need to provide this if pyverilog can get the init value
    for c in cal_perifs: fsm_init_value_info[c] = {}
    for c in cal_perifs: ignore_fsms[c] = []
    fsm_init_value_info['cal_csrng'] = {'cal_csrng_tb.perif_u.u_csrng_core.u_csrng_state_db.reg_rd_ptr_q': "1'd0"\
                                      , 'cal_csrng_tb.perif_u.gen_alert_tx[0].u_caliptra_prim_alert_sender.u_decode_ping.gen_async.state_q': '0'\
                                      , 'cal_csrng_tb.perif_u.gen_alert_tx[0].u_caliptra_prim_alert_sender.u_decode_ack.gen_async.state_q':  '0'\
                                      , 'cal_csrng_tb.perif_u.gen_alert_tx[1].u_caliptra_prim_alert_sender.u_decode_ping.gen_async.state_q': '0'\
                                      , 'cal_csrng_tb.perif_u.gen_alert_tx[1].u_caliptra_prim_alert_sender.u_decode_ack.gen_async.state_q':  '0'}
    fsm_init_value_info['cal_doe'] = {'cal_doe_tb.perif_u.doe_inst.doe_fsm1.dest_write_offset': '0'\
                                     , 'cal_doe_tb.perif_u.doe_inst.doe_fsm1.kv_doe_fsm_ps': 'cal_doe_tb.perif_u.doe_inst.doe_fsm1.DOE_IDLE' }
    fsm_init_value_info['cal_ecc'] = {'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_hmac_drbg_interface_i.hmac_drbg_i.drbg_st_reg': 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_hmac_drbg_interface_i.hmac_drbg_i.IDLE_ST'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.prog_cntr': 'ecc_dsa_uop_pkg::DSA_RESET'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_hmac_drbg_interface_i.hmac_drbg_i.HMAC_K.u_sha512_core_h1.sha512_ctrl_reg': 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_hmac_drbg_interface_i.hmac_drbg_i.HMAC_K.u_sha512_core_h1.CTRL_IDLE'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_hmac_drbg_interface_i.hmac_drbg_i.HMAC_K.u_sha512_core_h2.sha512_ctrl_reg': 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_hmac_drbg_interface_i.hmac_drbg_i.HMAC_K.u_sha512_core_h2.CTRL_IDLE'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_arith_unit_i.ecc_pm_ctrl_i.prog_cntr': '0'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_hmac_drbg_interface_i.state_reg': 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_hmac_drbg_interface_i.IDLE_ST'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_privkey_kv_read.kv_read_fsm.kv_fsm_ps': 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_privkey_kv_read.kv_read_fsm.KV_IDLE'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_seed_kv_read.kv_read_fsm.kv_fsm_ps': 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_seed_kv_read.kv_read_fsm.KV_IDLE'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_privkey_kv_write.kv_dest_write_fsm.kv_fsm_ps': 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_privkey_kv_write.kv_dest_write_fsm.KV_IDLE'\
                                     , 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_privkey_kv_write.kv_dest_write_fsm.kv_fsm_ps': 'cal_ecc_tb.perif_u.ecc_dsa_ctrl_i.ecc_privkey_kv_write.kv_dest_write_fsm.KV_IDLE'}
    fsm_init_value_info['cal_entropy_src'] = {'cal_entropy_src_tb.perif_u.gen_alert_tx[0].u_caliptra_prim_alert_sender.u_decode_ping.gen_async.state_q': '0'\
        , 'cal_entropy_src_tb.perif_u.gen_alert_tx[0].u_caliptra_prim_alert_sender.u_decode_ack.gen_async.state_q':  '0'\
        , 'cal_entropy_src_tb.perif_u.gen_alert_tx[1].u_caliptra_prim_alert_sender.u_decode_ping.gen_async.state_q': '0'\
        , 'cal_entropy_src_tb.perif_u.gen_alert_tx[1].u_caliptra_prim_alert_sender.u_decode_ack.gen_async.state_q':  '0'
        }
    fsm_init_value_info['cal_hmac'] = {'cal_hmac_tb.perif_u.hmac_inst.core.u_sha512_core_h1.sha512_ctrl_reg': 'cal_hmac_tb.perif_u.hmac_inst.core.u_sha512_core_h1.CTRL_IDLE'\
                                     , 'cal_hmac_tb.perif_u.hmac_inst.core.u_sha512_core_h2.sha512_ctrl_reg': 'cal_hmac_tb.perif_u.hmac_inst.core.u_sha512_core_h2.CTRL_IDLE'\
                                     , 'cal_hmac_tb.perif_u.hmac_inst.hmac_block_kv_read.kv_read_fsm.kv_fsm_ps': 'cal_hmac_tb.perif_u.hmac_inst.hmac_block_kv_read.kv_read_fsm.KV_IDLE'  }
    fsm_init_value_info['cal_spi_host'] = {'cal_spi_host_tb.perif_u.gen_alert_tx[0].u_caliptra_prim_alert_sender.u_decode_ping.gen_async.state_q': '0'\
        , 'cal_spi_host_tb.perif_u.gen_alert_tx[0].u_caliptra_prim_alert_sender.u_decode_ack.gen_async.state_q': '0'}
    fsm_init_value_info['cal_sha512'] = {'cal_sha512_tb.perif_u.sha512_inst.pv_gen_hash1.gen_hash_fsm_ps': 'cal_sha512_tb.perif_u.sha512_inst.pv_gen_hash1.GEN_HASH_IDLE'\
                                      , 'cal_sha512_tb.perif_u.sha512_inst.pv_gen_hash1.block_offset_i': '0'\
                                      , 'cal_sha512_tb.perif_u.sha512_inst.pv_gen_hash1.read_entry': '0'\
                                      , 'cal_sha512_tb.perif_u.sha512_inst.pv_gen_hash1.read_offset': '0'\
                                      , 'cal_sha512_tb.perif_u.sha512_inst.sha512_result_kv_write.kv_dest_write_fsm.kv_fsm_ps': 'cal_sha512_tb.perif_u.sha512_inst.sha512_result_kv_write.kv_dest_write_fsm.KV_IDLE'  }
    fsm_init_value_info['cal_uart'] = {'cal_uart_tb.perif_u.gen_alert_tx[0].u_caliptra_prim_alert_sender.u_decode_ping.gen_async.state_q': '0'\
        , 'cal_uart_tb.perif_u.gen_alert_tx[0].u_caliptra_prim_alert_sender.u_decode_ack.gen_async.state_q': '0'\
        , 'cal_uart_tb.perif_u.uart_core.break_st_q': 'cal_uart_tb.perif_u.uart_core.BRK_CHK'}

    ignore_fsms['cal_csrng'].append('cal_csrng_tb.perif_u.u_csrng_core.packer_adata_depth') # fsm reg not defined in this module, so cannot get its clock signal with japergold
    ignore_fsms['cal_entropy_src'].append('cal_entropy_src_tb.perif_u.u_entropy_src_core.u_entropy_src_bucket_ht.u_caliptra_prim_max_tree_bin_cntr_max.vld_tree') # Not a register; no clock is available for FSM analysis.

    ####inferred paths
    core_sim_path = os.path.join(os.environ['IPFUZZ_ROOT'], f'sim/{core_name}')
    pt["sim_dir_t"] = Template(f"{core_sim_path}/vcs_${{tno}}")
    pt["core_dram_path"] = "None"
    
    pt["fuzzer_input_format"]   = 'csv'
    pt["sim_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/vcs.log")
    pt["trace_out_path_t"] = None
    pt["cov_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/simv.{core_name}.vdb")
    
    pt["vdb_test_dir"] = "snps/coverage/db/testdata/test/"
    pt["vdb_ext_test_dir"] = "snps/coverage/db/testdata/test_ext/"

    pt["verilog_design_file_path"] =  Template(f"{pt['cov_out_path_t'].template}/snps/coverage/db/design/verilog.design.xml")
    pt["verilog_source_info_file_path"] =  Template(f"{pt['cov_out_path_t'].template}/snps/coverage/db/auxiliary/verilog.sourceinfo.xml")
    pt["fsm_verilog_shape_file_path"] =  Template(f"{pt['cov_out_path_t'].template}/snps/coverage/db/shape/fsm.verilog.shape.xml")
    pt["verilog_instance_parameters_file_path"] =  Template(f"{pt['cov_out_path_t'].template}/snps/coverage/db/auxiliary/verilog.instance_parameters.txt")

    pt["soc_dir"] = os.path.join(os.environ['IPFUZZ_ROOT'], "benchmarks/opn")
    pt["perif_dir"] = os.path.join(os.environ['IPFUZZ_ROOT'], f"benchmarks/{core_name}")
    pt["perif_sim_dir"] = os.path.join(pt['perif_dir'], f"sim")
    pt["perif_jg_tcl_file"] = os.path.join(pt['perif_sim_dir'], f"jg.tcl")
    pt["perif_jg_tcl_log_file"] = os.path.join(pt['perif_sim_dir'], f"jg.txt")
    pt["sanitizers_sva_file_path"] = os.path.join(pt['perif_dir'], f"tb/sanitizers.sva")
    pt["soc_sanitizers_sva_file_path"] = os.path.join(
        os.environ['IPFUZZ_ROOT'],
        f"benchmarks/calAsn/tb/sanitizers_{core_name}.sva")

    pt["tb_file_path"] = os.path.join(os.environ['IPFUZZ_ROOT'], f"benchmarks/{core_name}/tb/tb.sv")
    pt["tb_1_file_path"] = os.path.join(pt["soc_dir"], f"tb_1.sv")
    pt["tb_2_file_path"] = os.path.join(pt["soc_dir"], f"tb_2.sv")
    pt["tb_3_file_path"] = os.path.join(pt["soc_dir"], f"tb_3.sv")

