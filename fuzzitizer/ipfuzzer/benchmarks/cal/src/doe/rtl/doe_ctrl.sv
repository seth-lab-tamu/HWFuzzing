// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
//======================================================================
//
// doe_ctrl.sv
// --------
// DOE controller for the AHb_lite interface.
// DOE is the de-obfuscation engine, used to de-obfuscate the device secrets
//
//======================================================================
`include "caliptra_macros.svh"

module doe_ctrl 
    import doe_defines_pkg::*;
    import kv_defines_pkg::*;
    #(
    parameter AHB_DATA_WIDTH = 32,
    parameter AHB_ADDR_WIDTH = 32,
    localparam TOTAL_OBF_KEY_BITS = `CLP_OBF_KEY_DWORDS * 32
)
(
    // Clock and reset.
    input wire          clk,
    input wire          reset_n,
    input wire          cptra_pwrgood,

    input logic [TOTAL_OBF_KEY_BITS-1:0] cptra_obf_key,

    //Obfuscated UDS and FE
    input logic [`CLP_OBF_FE_DWORDS-1 :0][31:0] obf_field_entropy,
    input logic [`CLP_OBF_UDS_DWORDS-1:0][31:0] obf_uds_seed,


    output kv_write_t kv_write,
    input  kv_wr_resp_t kv_wr_resp,

    output logic clear_obf_secrets,

    // Interrupt
    output logic error_intr,
    output logic notif_intr,
    input  logic debugUnlock_or_scan_mode_switch,

    input logic cs,
    input logic we,
    input logic  [31:0] write_data,
    output logic [31:0] read_data,

    input logic [AHB_ADDR_WIDTH-1:0] address

);

    //----------------------------------------------------------------
    // doe
    //----------------------------------------------------------------
    logic doe_cs;
    logic doe_we;
    logic [AHB_ADDR_WIDTH-1:0] doe_address;
    logic [AHB_DATA_WIDTH-1:0] doe_write_data;
    logic [AHB_DATA_WIDTH-1:0] doe_read_data;

    doe_cbc #(
        .ADDR_WIDTH(AHB_ADDR_WIDTH),
        .DATA_WIDTH(32)
    ) doe_inst(
        .clk(clk),
        .reset_n(reset_n),
        .cptra_pwrgood(cptra_pwrgood),
        .cptra_obf_key(cptra_obf_key),
        .obf_uds_seed(obf_uds_seed),
        .obf_field_entropy(obf_field_entropy),
        .cs(doe_cs),
        .we(doe_we),
        .address(doe_address),
        .write_data(doe_write_data[31:0]),
        .read_data(doe_read_data[31:0]),
        .error_intr(error_intr),
        .notif_intr(notif_intr),
        .clear_obf_secrets(clear_obf_secrets),
        .kv_write(kv_write),
        .debugUnlock_or_scan_mode_switch(debugUnlock_or_scan_mode_switch)
    );







    assign doe_cs         = cs        ;
    assign doe_we         = we        ;
    assign doe_address    = address   ;
    assign doe_write_data[31:0] = write_data;
    assign     read_data  = doe_read_data[31:0] ;

endmodule
