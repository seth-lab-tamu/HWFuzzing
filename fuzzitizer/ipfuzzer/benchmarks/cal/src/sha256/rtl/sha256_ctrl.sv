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
// sha256_ctrl.sv
// --------
// SHA256 controller for the AHb_lite interface.
//
//
//======================================================================

module sha256_ctrl #(
    parameter AHB_DATA_WIDTH = 32,
    parameter AHB_ADDR_WIDTH = 32
)
(
    // Clock and reset.
    input wire           clk,
    input wire           reset_n,
    input wire           cptra_pwrgood,



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
    // sha256
    //----------------------------------------------------------------
    reg           sha256_cs;
    reg           sha256_we;
    reg  [AHB_ADDR_WIDTH-1 : 0] sha256_address;
    reg  [31 : 0] sha256_write_data;
    reg  [31 : 0] sha256_read_data;
    reg           sha256_err;

    sha256 #(
        .ADDR_WIDTH(AHB_ADDR_WIDTH),
        .DATA_WIDTH(32)
        ) sha256_inst(
        .clk(clk),
        .reset_n(reset_n),
        .cptra_pwrgood(cptra_pwrgood),
        .cs(sha256_cs),
        .we(sha256_we),
        .address(sha256_address),
        .write_data(sha256_write_data),
        .read_data(sha256_read_data),
        .err(sha256_err),
        .error_intr(error_intr),
        .notif_intr(notif_intr),
        .debugUnlock_or_scan_mode_switch(debugUnlock_or_scan_mode_switch)
    );


    //----------------------------------------------------------------
    // AHB Slave node
    //----------------------------------------------------------------
        
    //instantiate ahb lite module




    assign sha256_cs         = cs        ;
    assign sha256_we         = we        ;
    assign sha256_address    = address   ;
    assign sha256_write_data = write_data;
    assign read_data  = sha256_read_data ;

endmodule //sha256_ctrl

//======================================================================
// EOF sha256_ctrl.sv
//======================================================================
