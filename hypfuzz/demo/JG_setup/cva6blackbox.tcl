set ROOT_PATH $env(JG_ROOT_PATH)

##blackbox soc peripheral
analyze -sv \
$ROOT_PATH/CVA6CoreBlackbox.sv

#0: missing modules are errors
#1: missing modules are automatically black boxed
#elaborate -bbox 0 -top ariane -enable_sv_type_properties
#-bbox_a 4096
elaborate -bbox 0 -bbox_m SyncSpRamBeNx64 -top CVA6CoreBlackbox

clock clk_i
# this reset method leave only 128/24511 design flops non asynchronous reset for cva6.
reset -sequence -vcd test.vcd -time_scale ps -time 2263500 \
-hier_path TestDriver.testHarness.chiptop.system.tile_prci_domain.tile_reset_domain.cva6_tile.core

assume -name const_top_inputs {boot_addr_i == 64'h0000_0000_0001_0040 \
							   && hart_id_i == 64'h0 \
							   && irq_i == 2'h0 \
							   && ipi_i == 1'b0 \
							   && time_irq_i == 1'b1 \
							   && debug_req_i == 1'b1 \
							   && axi_req_o_aw_bits_len == 8'h0 \
							   && axi_req_o_aw_bits_burst == 2'h0 \
							   && axi_req_o_aw_bits_lock == 1'b0 \
							   && axi_req_o_aw_bits_cache == 4'h0 \
							   && axi_req_o_aw_bits_prot == 3'h0 \
							   && axi_req_o_aw_bits_qos == 4'h0 \
							   && axi_req_o_aw_bits_region == 4'h0 \
							   && axi_req_o_aw_bits_atop == 6'h0 \
							   && axi_req_o_aw_bits_user == 1'b0 \
							   && axi_resp_i_w_ready == 1'b1 \
							   && axi_req_o_w_bits_last == 1'b1 \
							   && axi_req_o_w_bits_user == 1'b0 \
							   && axi_resp_i_ar_ready == 1'b1 \
							   && axi_req_o_ar_bits_lock == 1'b0 \
							   && axi_req_o_ar_bits_cache == 4'h0 \
							   && axi_req_o_ar_bits_prot == 3'h0 \
							   && axi_req_o_ar_bits_qos == 4'h0 \
							   && axi_req_o_ar_bits_region == 4'h0 \
							   && axi_req_o_ar_bits_user == 1'b0 \
							   && axi_resp_i_b_bits_resp == 2'h0 \
							   && axi_resp_i_b_bits_user == 1'b0 \
							   && axi_resp_i_r_bits_resp == 2'h0 \
							   && axi_resp_i_r_bits_user == 1'b0
							   }

# check constraint and make sure there is no conflict
check_assumptions

# example of properties using new reset and constraint
# note: we must use full path of each signal
cover -name 136_364 {(~i_ariane.id_stage_i.decoder_i.ex_i.valid) && (i_ariane.id_stage_i.decoder_i.irq_ctrl_i.mie[riscv::S_SW_INTERRUPT[5:0]] && i_ariane.id_stage_i.decoder_i.irq_ctrl_i.mip[riscv::S_SW_INTERRUPT[5:0]])}
cover -name 136_366 {(~i_ariane.id_stage_i.decoder_i.ex_i.valid) && (i_ariane.id_stage_i.decoder_i.irq_ctrl_i.mie[riscv::S_EXT_INTERRUPT[5:0]] && (i_ariane.id_stage_i.decoder_i.irq_ctrl_i.mip[riscv::S_EXT_INTERRUPT[5:0]] | i_ariane.id_stage_i.decoder_i.irq_i[ariane_pkg::SupervisorIrq]))}
