module dbg_wrapper #(
    parameter int unsigned AXI_ADDR_WIDTH = 64,
    parameter int unsigned AXI_DATA_WIDTH = 64,
    parameter int unsigned AXI_ID_WIDTH   = 10,
    parameter int unsigned NumHarts        =  1,
    parameter int unsigned AxiDataWidth  = 64
)(
           clk_i,
           rst_ni,
           address, 
           en_acct, 
           we, 
           wdata, 
           rdata,
           slave_be_i,
        
           priv_lvl_i,
           we_flag_4_i, 
           jtag_hash_i,
           ikey_hash_i,
           okey_hash_i,

           tck_i,
           tms_i,
           trst_ni,
           td_i,
           td_o,
           tdo_oe_o
           );
 
    input  logic                    clk_i;
    input  logic                    rst_ni;
    input  logic [AXI_ADDR_WIDTH-1:0] address;
    input  logic                      en_acct;
    input  logic                      we;
    input  logic [63:0] wdata;
    output logic [63:0] rdata;
    input  logic [AxiDataWidth/8-1:0] slave_be_i;


    input logic [`NUM_TILES*2-1:0]      priv_lvl_i;
    input  logic                         we_flag_4_i; 
    input  logic [255:0]  jtag_hash_i, ikey_hash_i, okey_hash_i;

    input  logic                        tck_i;
    input  logic                        tms_i;
    input  logic                        trst_ni;
    input  logic                        td_i;
    output logic                        td_o;
    output logic                        tdo_oe_o;


  //----------------------------------------------------------------
  // core instantiation.
  //----------------------------------------------------------------
  logic          debug_req_valid;
  logic          debug_req_ready;
  logic          debug_resp_valid;
  logic          debug_resp_ready;
  dm::dmi_req_t  debug_req;
  dm::dmi_resp_t debug_resp;
  logic        tck, tms, trst_n, tdi, tdo, tdo_oe;

  dmi_jtag i_dmi_jtag (
    .clk_i            ( clk_i            ),
    .rst_ni           ( rst_ni           ),
    .testmode_i       ( '0               ),
    .priv_lvl_i       ( priv_lvl_i       ),
    .we_flag          ( we_flag_4_i      ),
    .jtag_hash_i      ( jtag_hash_i      ),
    .okey_hash_i      ( okey_hash_i      ),
    .ikey_hash_i      ( ikey_hash_i      ),
    .jtag_unlock_o    (                  ),
    .dmi_req_o        ( debug_req        ),
    .dmi_req_valid_o  ( debug_req_valid  ),
    .dmi_req_ready_i  ( debug_req_ready  ),
    .dmi_resp_i       ( debug_resp       ),
    .dmi_resp_ready_o ( debug_resp_ready ),
    .dmi_resp_valid_i ( debug_resp_valid ),
    .dmi_rst_no       (                  ), // not connected
    .tck_i            ( tck              ),
    .tms_i            ( tms              ),
    .trst_ni          ( trst_n           ),
    .td_i             ( tdi              ),
    .td_o             ( tdo              ),
    .tdo_oe_o         ( tdo_oe           )
  );

  assign tck      = tck_i   ;
  assign tms      = tms_i   ;
  assign trst_n   = trst_ni ;
  assign tdi      = td_i    ;
  assign td_o     = tdo     ;
  assign tdo_oe_o = tdo_oe  ;


  // debug module
  dm_top #(
    .NrHarts              ( NumHarts             ),
    .BusWidth             ( AxiDataWidth         ),
    .SelectableHarts      ( {NumHarts{1'b1}}     )
  ) i_dm_top (
    .clk_i                ( clk_i                ),
    .rst_ni               ( rst_ni               ), // PoR
    .testmode_i           ( '0                   ),
    .ndmreset_o           (                      ),
    .dmactive_o           (                      ), // active debug session
    .debug_req_o          (                      ),
    .unavailable_i        ( '0                   ),
    .hartinfo_i           ( {NumHarts{ariane_pkg::DebugHartInfo}} ),
    .slave_req_i          ( en_acct          ),
    .slave_we_i           ( we           ),
    .slave_addr_i         ( address         ),
    .slave_be_i           ( slave_be_i           ),
    .slave_wdata_i        ( wdata        ),
    .slave_rdata_o        ( rdata        ),
    .master_req_o         (                      ),
    .master_add_o         (                      ),
    .master_we_o          (                      ),
    .master_wdata_o       (                      ),
    .master_be_o          (                      ),
    .master_gnt_i         ( '0                   ),
    .master_r_valid_i     ( '0                   ),
    .master_r_rdata_i     ( '0                   ),
    .dmi_rst_ni           ( rst_ni               ),
    .dmi_req_valid_i      ( debug_req_valid      ),
    .dmi_req_ready_o      ( debug_req_ready      ),
    .dmi_req_i            ( debug_req            ),
    .dmi_resp_valid_o     ( debug_resp_valid     ),
    .dmi_resp_ready_i     ( debug_resp_ready     ),
    .dmi_resp_o           ( debug_resp           )
  );


endmodule // dbg


//======================================================================
// EOF aes.v
//======================================================================
